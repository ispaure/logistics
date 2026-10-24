#import <UIKit/UIKit.h>

@interface IncomingSender : UIViewController <UIDocumentInteractionControllerDelegate>
@property(nonatomic, strong) UIDocumentInteractionController *document;
@end
@implementation IncomingSender
- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.systemBackgroundColor;
    UIButton *share = [UIButton buttonWithType:UIButtonTypeSystem];
    [share setTitle:@"Share fixture files" forState:UIControlStateNormal];
    [share addTarget:self action:@selector(share:) forControlEvents:UIControlEventTouchUpInside];
    UIButton *open = [UIButton buttonWithType:UIButtonTypeSystem];
    [open setTitle:@"Open fixture in app" forState:UIControlStateNormal];
    [open addTarget:self action:@selector(open:) forControlEvents:UIControlEventTouchUpInside];
    UIStackView *stack = [[UIStackView alloc] initWithArrangedSubviews:@[share, open]];
    stack.axis = UILayoutConstraintAxisVertical; stack.spacing = 24;
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[
        [stack.centerYAnchor constraintEqualToAnchor:self.view.centerYAnchor],
        [stack.centerXAnchor constraintEqualToAnchor:self.view.centerXAnchor]]];
}
- (NSArray<NSURL *> *)fixtures {
    NSMutableArray *urls = [NSMutableArray array];
    for (NSString *name in @[@"Native Inbox one.txt", @"Native Inbox two.txt"]) {
        NSURL *url = [[NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject URLByAppendingPathComponent:name];
        [name writeToURL:url atomically:YES encoding:NSUTF8StringEncoding error:nil];
        [urls addObject:url];
    }
    return urls;
}
- (void)share:(UIButton *)button {
    UIActivityViewController *sheet = [[UIActivityViewController alloc] initWithActivityItems:self.fixtures applicationActivities:nil];
    sheet.popoverPresentationController.sourceView = button;
    sheet.popoverPresentationController.sourceRect = button.bounds;
    [self presentViewController:sheet animated:YES completion:nil];
}
- (void)open:(UIButton *)button {
    self.document = [UIDocumentInteractionController interactionControllerWithURL:self.fixtures.firstObject];
    self.document.delegate = self;
    [self.document presentOpenInMenuFromRect:button.bounds inView:button animated:YES];
}
@end
@interface SenderScene : UIResponder <UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@end
@implementation SenderScene
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    self.window.rootViewController = [[IncomingSender alloc] init];
    [self.window makeKeyAndVisible];
}
@end
@interface SenderDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation SenderDelegate
- (UISceneConfiguration *)application:(UIApplication *)app configurationForConnectingSceneSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    UISceneConfiguration *configuration = [[UISceneConfiguration alloc] initWithName:@"Sender" sessionRole:session.role];
    configuration.delegateClass = SenderScene.class;
    return configuration;
}
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, @"SenderDelegate"); }
}
