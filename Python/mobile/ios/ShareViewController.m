#import <UIKit/UIKit.h>
#import "IncomingFiles.m"

@interface LogisticsShareViewController : UIViewController
@property(atomic) BOOL cancelled;
@property(nonatomic, strong) UILabel *status;
@property(nonatomic, strong) UIButton *doneButton;
@end

@implementation LogisticsShareViewController
- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.systemBackgroundColor;
    self.status = [[UILabel alloc] init];
    self.status.numberOfLines = 0;
    self.status.textAlignment = NSTextAlignmentCenter;
    self.status.text = @"Receiving files into Inbox…";
    self.doneButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.doneButton setTitle:@"Cancel remaining files" forState:UIControlStateNormal];
    [self.doneButton addTarget:self action:@selector(done) forControlEvents:UIControlEventTouchUpInside];
    UIStackView *stack = [[UIStackView alloc] initWithArrangedSubviews:@[self.status, self.doneButton]];
    stack.axis = UILayoutConstraintAxisVertical; stack.spacing = 24;
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[
        [stack.centerYAnchor constraintEqualToAnchor:self.view.centerYAnchor],
        [stack.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor constant:24],
        [stack.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor constant:-24]]];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{ [self receive]; });
}
- (void)done {
    self.cancelled = YES;
    [self.extensionContext completeRequestReturningItems:@[] completionHandler:nil];
}
- (void)receive {
    NSString *queue = LogisticsIncomingFiles.sharedQueue;
    NSMutableArray<NSItemProvider *> *providers = [NSMutableArray array];
    for (NSExtensionItem *item in self.extensionContext.inputItems) [providers addObjectsFromArray:item.attachments ?: @[]];
    NSUInteger saved = 0, failed = 0;
    if (!queue || providers.count == 0 || providers.count > 100) failed++;
    else for (NSItemProvider *provider in providers) {
        if (self.cancelled) break;
        NSString *type = nil;
        for (NSString *identifier in provider.registeredTypeIdentifiers) {
            UTType *candidate = [UTType typeWithIdentifier:identifier];
            if ([candidate conformsToType:UTTypeData]) { type = identifier; break; }
        }
        if (!type) { failed++; continue; }
        dispatch_semaphore_t semaphore = dispatch_semaphore_create(0);
        __block BOOL success = NO;
        [provider loadFileRepresentationForTypeIdentifier:type completionHandler:^(NSURL *url, NSError *error) {
            // The representation URL is valid only during this callback.
            if (url && !error && !self.cancelled) {
                NSString *name = provider.suggestedName ?: url.lastPathComponent;
                if (!name.pathExtension.length && url.pathExtension.length)
                    name = [name stringByAppendingPathExtension:url.pathExtension];
                success = [LogisticsIncomingFiles stageURL:url queue:queue name:name cancelled:^BOOL { return self.cancelled; }];
            }
            dispatch_semaphore_signal(semaphore);
        }];
        dispatch_semaphore_wait(semaphore, DISPATCH_TIME_FOREVER);
        if (success) saved++; else failed++;
    }
    dispatch_async(dispatch_get_main_queue(), ^{
        self.status.text = [NSString stringWithFormat:@"%lu file(s) received. Open Logisticks to find them in Inbox.%@", (unsigned long)saved,
            failed ? @" Some files could not be received; share them again." : @""];
        [self.doneButton setTitle:@"Done" forState:UIControlStateNormal];
    });
}
@end
