#import <CommonCrypto/CommonDigest.h>
#import <UIKit/UIKit.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#import <notify.h>

static NSArray<NSDictionary<NSString *, NSString *> *> *FixtureDefinitions(void) {
    return @[
        @{@"id": @"open-in", @"name": @"Open In café 漢字.txt", @"marker": @"Open In source receipt"},
        @{@"id": @"share", @"name": @"Share café 漢字.txt", @"marker": @"Share source receipt"},
        @{@"id": @"share-two", @"name": @"Share two café 漢字.txt", @"marker": @"Second share source receipt"},
        @{@"id": @"files-open", @"name": @"Files Open With café 漢字.txt", @"marker": @"Files Open With source receipt"},
        @{@"id": @"warm", @"name": @"Warm café 漢字.txt", @"marker": @"Warm source receipt"},
        @{@"id": @"resume", @"name": @"Resume café 漢字.txt", @"marker": @"Resume source receipt"},
        @{@"id": @"duplicate-one", @"name": @"Duplicate café 漢字.txt", @"marker": @"First duplicate source receipt"},
        @{@"id": @"duplicate-two", @"name": @"Duplicate café 漢字.txt", @"marker": @"Second duplicate source receipt"},
        @{@"id": @"cancel-first", @"name": @"Cancel completed café 漢字.txt", @"marker": @"Completed before cancel receipt"},
        @{@"id": @"cancel-second", @"name": @"Cancel held café 漢字.txt", @"marker": @"Held for cancel receipt"},
        @{@"id": @"failure-first", @"name": @"Failure completed café 漢字.txt", @"marker": @"Completed before failure receipt"},
        @{@"id": @"failure-second", @"name": @"Failure held café 漢字.txt", @"marker": @"Held for failure receipt"},
    ];
}

static NSString *SHA256(NSData *data) {
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
    NSMutableString *hex = [NSMutableString stringWithCapacity:CC_SHA256_DIGEST_LENGTH * 2];
    for (NSUInteger index = 0; index < sizeof(digest); index++) {
        [hex appendFormat:@"%02x", digest[index]];
    }
    return hex;
}

static NSURL *Documents(void) {
    return [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
}

static NSString *ProviderSignal(NSString *mode, NSString *event) {
    return [NSString stringWithFormat:@"io.github.ispaure.logisticsincomingsender.%@.%@", mode, event];
}

static void NameAttachment(NSItemProvider *provider, NSURL *url) {
    provider.suggestedName = url.lastPathComponent;
    provider.preferredPresentationStyle = UIPreferredPresentationStyleAttachment;
}

static NSString *FirstDataType(NSItemProvider *provider) {
    for (NSString *identifier in provider.registeredTypeIdentifiers) {
        if ([[UTType typeWithIdentifier:identifier] conformsToType:UTTypeData]) {
            return identifier;
        }
    }
    return @"";
}

static NSDictionary *ProviderInventory(NSItemProvider *provider) {
    return @{
        @"registered_types": provider.registeredTypeIdentifiers ?: @[],
        @"open_in_place_types": [provider registeredTypeIdentifiersWithFileOptions:NSItemProviderFileOptionOpenInPlace] ?: @[],
        @"file_url_conformance": @([provider hasItemConformingToTypeIdentifier:UTTypeFileURL.identifier]),
        @"first_data_type": FirstDataType(provider),
    };
}

@interface HeldShareEvidence : NSObject
@property(nonatomic, copy) NSString *mode;
@property(nonatomic, strong) NSURL *file;
@property(nonatomic, strong) NSURL *checkpointFile;
@property(nonatomic, copy) NSArray<NSDictionary *> *inventory;
@property(nonatomic, strong) NSMutableArray<NSDictionary *> *events;
@property(nonatomic) BOOL armed;
@property(nonatomic, strong) NSNumber *requestedUptime;
@property(nonatomic) BOOL earlyLoad;
@property(nonatomic) int armToken;
- (instancetype)initWithMode:(NSString *)mode;
- (BOOL)record:(NSString *)event;
- (BOOL)observeArm;
- (BOOL)beginRequest;
- (BOOL)readCheckpointBefore:(NSTimeInterval)deadline;
@end

@implementation HeldShareEvidence
- (instancetype)initWithMode:(NSString *)mode {
    self = [super init];
    if (self) {
        _mode = [mode copy];
        NSURL *directory = [Documents() URLByAppendingPathComponent:@"ProviderEvidence" isDirectory:YES];
        _file = [directory URLByAppendingPathComponent:[mode stringByAppendingPathExtension:@"json"]];
        _checkpointFile = [directory URLByAppendingPathComponent:[mode stringByAppendingString:@"-checkpoint.json"]];
        _events = [NSMutableArray array];
        _armToken = -1;
    }
    return self;
}

- (void)dealloc {
    if (_armToken >= 0) {
        notify_cancel(_armToken);
    }
}

- (BOOL)record:(NSString *)event {
    @synchronized (self) {
        NSDictionary *entry = @{@"event": event, @"uptime": @(NSProcessInfo.processInfo.systemUptime)};
        [self.events addObject:entry];
        NSError *error = nil;
        BOOL directoryReady = [NSFileManager.defaultManager createDirectoryAtURL:[self.file URLByDeletingLastPathComponent]
            withIntermediateDirectories:YES attributes:nil error:&error];
        NSData *data = directoryReady ? [NSJSONSerialization dataWithJSONObject:@{
            @"schema": @1, @"mode": self.mode, @"items": self.inventory, @"events": self.events,
        } options:NSJSONWritingSortedKeys error:&error] : nil;
        BOOL saved = data && [data writeToURL:self.file options:NSDataWritingAtomic error:&error];
        NSLog(@"IncomingSender provider %@ %@ at %@%@", self.mode, event, entry[@"uptime"],
              saved ? @"" : [@" evidence write failed: " stringByAppendingString:(error.localizedDescription ?: @"unknown error")]);
        return saved;
    }
}

- (BOOL)observeArm {
    __weak HeldShareEvidence *weakSelf = self;
    int token;
    uint32_t status = notify_register_dispatch(ProviderSignal(self.mode, @"arm").UTF8String, &token,
        dispatch_get_main_queue(), ^(int unused) {
            HeldShareEvidence *evidence = weakSelf;
            if (!evidence) return;
            @synchronized (evidence) {
                if (evidence.armed || evidence.earlyLoad) return;
                evidence.armed = [evidence record:@"armed"];
                if (evidence.armed) {
                    notify_post(ProviderSignal(evidence.mode, @"armed").UTF8String);
                }
            }
        });
    if (status != NOTIFY_STATUS_OK) return NO;
    self.armToken = token;
    return YES;
}

- (BOOL)beginRequest {
    @synchronized (self) {
        if (!self.armed) {
            self.earlyLoad = YES;
            [self record:@"early-load"];
            return NO;
        }
        if (self.requestedUptime) {
            [self record:@"duplicate-request"];
            return NO;
        }
        if (![self record:@"requested"]) {
            return NO;
        }
        self.requestedUptime = self.events.lastObject[@"uptime"];
        return YES;
    }
}

- (BOOL)readCheckpointBefore:(NSTimeInterval)deadline {
    NSData *data = [NSData dataWithContentsOfURL:self.checkpointFile];
    id payload = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
    if (![payload isKindOfClass:NSDictionary.class]) {
        return NO;
    }
    NSDictionary *checkpoint = payload;
    id schema = checkpoint[@"schema"];
    id uptime = checkpoint[@"requested_uptime"];
    if (![schema isKindOfClass:NSNumber.class] || CFGetTypeID((__bridge CFTypeRef)schema) == CFBooleanGetTypeID()
            || ![schema isEqualToNumber:@1] || ![self.mode isEqual:checkpoint[@"mode"]]
            || ![uptime isKindOfClass:NSNumber.class] || CFGetTypeID((__bridge CFTypeRef)uptime) == CFBooleanGetTypeID()
            || ![self.requestedUptime isEqualToNumber:uptime]
            || NSProcessInfo.processInfo.systemUptime >= deadline) {
        return NO;
    }
    return YES;
}
@end

static NSError *HeldFileError(void) {
    return [NSError errorWithDomain:@"IncomingSender.Provider" code:1 userInfo:@{
        NSLocalizedDescriptionKey: @"Fixture source withheld the second file representation",
    }];
}

static NSItemProvider *HeldProvider(NSURL *url, UTType *type, HeldShareEvidence *evidence) {
    NSItemProvider *provider = [[NSItemProvider alloc] init];
    NameAttachment(provider, url);
    // The receiver asks for the first registered type that conforms to data.
    [provider registerFileRepresentationForTypeIdentifier:type.identifier fileOptions:0
        visibility:NSItemProviderRepresentationVisibilityAll
        loadHandler:^NSProgress *(void (^completion)(NSURL *, BOOL, NSError *)) {
            if (!evidence) {
                completion(url, NO, nil); // The previous sender, for inventory only.
                return nil;
            }
            int token;
            NSString *signal = ProviderSignal(evidence.mode, @"release");
            if (notify_register_check(signal.UTF8String, &token) != NOTIFY_STATUS_OK) {
                [evidence record:@"release-observer-failed"];
                completion(nil, NO, HeldFileError());
                return nil;
            }
            int changed = 0;
            BOOL observing = notify_check(token, &changed) == NOTIFY_STATUS_OK;
            if (!observing || ![evidence beginRequest]) {
                if (!observing) [evidence record:@"release-observer-failed"];
                notify_cancel(token);
                completion(nil, NO, HeldFileError());
                return nil;
            }
            NSProgress *progress = [NSProgress progressWithTotalUnitCount:1];
            notify_post(ProviderSignal(evidence.mode, @"requested").UTF8String);
            dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
                NSTimeInterval deadline = evidence.requestedUptime.doubleValue + 40;
                BOOL checkpointObserved = NO;
                NSString *end = @"timed-out";
                while (NSProcessInfo.processInfo.systemUptime < deadline) {
                    int released = 0;
                    if (notify_check(token, &released) != NOTIFY_STATUS_OK) {
                        end = @"release-observer-failed";
                        break;
                    }
                    if (released) {
                        end = @"released";
                        break;
                    }
                    if (progress.cancelled) {
                        end = @"cancelled";
                        break;
                    }
                    if (!checkpointObserved && [evidence readCheckpointBefore:deadline]) {
                        checkpointObserved = YES;
                        if ([evidence record:@"checkpoint-observed"] && NSProcessInfo.processInfo.systemUptime < deadline) {
                            notify_post(ProviderSignal(evidence.mode, @"checkpoint-observed").UTF8String);
                        }
                    }
                    [NSThread sleepForTimeInterval:0.2];
                }
                notify_cancel(token);
                [evidence record:end];
                completion(nil, NO, HeldFileError());
                progress.completedUnitCount = 1;
            });
            return progress;
        }];
    return provider;
}

static NSDictionary *AttachmentInventory(NSURL *url, UTType *type, NSItemProvider *fromContents,
                                         NSItemProvider *candidate) {
    NSItemProvider *previous = HeldProvider(url, UTTypeData, nil);
    return @{
        @"filename": url.lastPathComponent,
        @"content_type": type.identifier,
        @"url_writable_types": url.writableTypeIdentifiersForItemProvider ?: @[],
        @"from_contents": ProviderInventory(fromContents),
        @"previous_custom": ProviderInventory(previous),
        @"candidate": ProviderInventory(candidate),
    };
}

static BOOL ExportFixtures(NSError **error) {
    NSFileManager *files = NSFileManager.defaultManager;
    NSURL *root = [Documents() URLByAppendingPathComponent:@"Export" isDirectory:YES];
    NSMutableArray *manifest = [NSMutableArray array];
    for (NSDictionary<NSString *, NSString *> *fixture in FixtureDefinitions()) {
        NSURL *folder = [root URLByAppendingPathComponent:fixture[@"id"] isDirectory:YES];
        if (![files createDirectoryAtURL:folder withIntermediateDirectories:YES attributes:nil error:error]) {
            return NO;
        }
        NSURL *url = [folder URLByAppendingPathComponent:fixture[@"name"]];
        NSString *text = [NSString stringWithFormat:@"%@\r\nUTF-8 café 漢字 🌿\r\nTrailing spaces  \t\r\n\r\n", fixture[@"marker"]];
        NSData *data = [text dataUsingEncoding:NSUTF8StringEncoding];
        if ([files fileExistsAtPath:url.path]) {
            NSData *existing = [NSData dataWithContentsOfURL:url options:0 error:error];
            if (!existing) {
                return NO;
            }
            if (![existing isEqualToData:data]) {
                *error = [NSError errorWithDomain:@"IncomingSender" code:1 userInfo:@{
                    NSLocalizedDescriptionKey: [@"Existing export differs: " stringByAppendingString:fixture[@"id"]],
                }];
                return NO;
            }
        } else if (![data writeToURL:url options:NSDataWritingAtomic error:error]) {
            return NO;
        }
        NSMutableDictionary *entry = [fixture mutableCopy];
        entry[@"length"] = @(data.length);
        entry[@"sha256"] = SHA256(data);
        [manifest addObject:entry];
    }
    NSData *index = [NSJSONSerialization dataWithJSONObject:@{@"version": @1, @"fixtures": manifest}
                                                    options:NSJSONWritingSortedKeys error:error];
    return index && [index writeToURL:[root URLByAppendingPathComponent:@"manifest.json"]
                              options:NSDataWritingAtomic error:error];
}

@interface IncomingSender : UIViewController <UIDocumentInteractionControllerDelegate>
@property(nonatomic, strong) UIDocumentInteractionController *document;
@property(nonatomic, strong) UILabel *status;
@property(nonatomic, copy) NSDictionary<NSString *, NSURL *> *fixtures;
@end

@implementation IncomingSender
- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.systemBackgroundColor;
    self.status = [[UILabel alloc] init];
    self.status.accessibilityIdentifier = @"fixture-status";
    self.status.numberOfLines = 0;
    self.status.textAlignment = NSTextAlignmentCenter;

    BOOL exporter = [NSProcessInfo.processInfo.arguments containsObject:@"--export-fixtures"];
    NSArray *controls = @[self.status];
    if (exporter) {
        NSError *error = nil;
        self.status.text = ExportFixtures(&error) ? @"Fixtures exported" : error.localizedDescription;
    } else {
        self.fixtures = [self verifiedIntake];
        self.status.text = self.fixtures ? @"Intake verified" : @"Intake manifest or fixture differs";
        if (self.fixtures) {
            UIButton *share = [self button:@"Share fixture files" action:@selector(share:)];
            UIButton *open = [self button:@"Open fixture in app" action:@selector(open:)];
            UIButton *cancel = [self button:@"Share with held second file" action:@selector(shareWithHold:)];
            UIButton *failure = [self button:@"Share with failing second file" action:@selector(shareWithHold:)];
            UIButton *duplicateOne = [self button:@"Share original duplicate name" action:@selector(shareOne:)];
            UIButton *duplicateTwo = [self button:@"Share different bytes under the same name" action:@selector(shareOne:)];
            UIButton *retry = [self button:@"Retry failed source file" action:@selector(shareOne:)];
            cancel.accessibilityIdentifier = @"cancel";
            failure.accessibilityIdentifier = @"failure";
            duplicateOne.accessibilityIdentifier = @"duplicate-one";
            duplicateTwo.accessibilityIdentifier = @"duplicate-two";
            retry.accessibilityIdentifier = @"failure-second";
            controls = @[self.status, share, open, duplicateOne, duplicateTwo, cancel, failure, retry];
        }
    }
    UIStackView *stack = [[UIStackView alloc] initWithArrangedSubviews:controls];
    stack.axis = UILayoutConstraintAxisVertical;
    stack.spacing = 24;
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[
        [stack.centerYAnchor constraintEqualToAnchor:self.view.centerYAnchor],
        [stack.centerXAnchor constraintEqualToAnchor:self.view.centerXAnchor],
        [stack.widthAnchor constraintLessThanOrEqualToAnchor:self.view.safeAreaLayoutGuide.widthAnchor constant:-24],
    ]];
}

- (UIButton *)button:(NSString *)title action:(SEL)action {
    UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
    [button setTitle:title forState:UIControlStateNormal];
    [button addTarget:self action:action forControlEvents:UIControlEventTouchUpInside];
    return button;
}

- (NSDictionary<NSString *, NSURL *> *)verifiedIntake {
    NSURL *root = [Documents() URLByAppendingPathComponent:@"Intake" isDirectory:YES];
    NSData *index = [NSData dataWithContentsOfURL:[root URLByAppendingPathComponent:@"manifest.json"]];
    if (!index) {
        return nil;
    }
    NSDictionary *manifest = [NSJSONSerialization JSONObjectWithData:index options:0 error:nil];
    NSArray *entries = manifest[@"fixtures"];
    NSArray *definitions = FixtureDefinitions();
    if (![manifest[@"version"] isEqual:@1] || entries.count != definitions.count) {
        return nil;
    }
    NSMutableDictionary *urls = [NSMutableDictionary dictionary];
    for (NSUInteger row = 0; row < definitions.count; row++) {
        NSDictionary *definition = definitions[row];
        NSDictionary *entry = entries[row];
        NSString *identifier = definition[@"id"];
        NSString *name = definition[@"name"];
        if (![identifier isEqual:entry[@"id"]] || ![name isEqual:entry[@"name"]]) {
            return nil;
        }
        NSURL *folder = [root URLByAppendingPathComponent:identifier isDirectory:YES];
        NSURL *url = [folder URLByAppendingPathComponent:name];
        NSData *data = [NSData dataWithContentsOfURL:url];
        if (!data || ![@(data.length) isEqual:entry[@"length"]] || ![SHA256(data) isEqual:entry[@"sha256"]]) {
            return nil;
        }
        urls[identifier] = url;
    }
    return urls;
}

- (void)share:(UIButton *)button {
    UIActivityViewController *sheet = [[UIActivityViewController alloc]
        initWithActivityItems:@[self.fixtures[@"share"], self.fixtures[@"share-two"]]
        applicationActivities:nil];
    [self presentSheet:sheet from:button];
}

- (void)shareWithHold:(UIButton *)button {
    NSString *mode = button.accessibilityIdentifier;
    NSURL *first = self.fixtures[[mode stringByAppendingString:@"-first"]];
    NSURL *second = self.fixtures[[mode stringByAppendingString:@"-second"]];
    UTType *firstType = [first resourceValuesForKeys:@[NSURLContentTypeKey] error:nil][NSURLContentTypeKey];
    UTType *secondType = [second resourceValuesForKeys:@[NSURLContentTypeKey] error:nil][NSURLContentTypeKey];
    NSItemProvider *firstContents = [[NSItemProvider alloc] initWithContentsOfURL:first];
    NSItemProvider *secondContents = [[NSItemProvider alloc] initWithContentsOfURL:second];
    NSItemProvider *completed = [[NSItemProvider alloc] initWithContentsOfURL:first];
    if (!firstType || !secondType || !firstContents || !secondContents || !completed) {
        self.status.text = @"Unable to identify both fixture files and content types";
        return;
    }

    HeldShareEvidence *evidence = [[HeldShareEvidence alloc] initWithMode:mode];
    NSItemProvider *held = HeldProvider(second, secondType, evidence);
    NameAttachment(completed, first);
    [completed registerObject:first visibility:NSItemProviderRepresentationVisibilityAll];
    [held registerObject:second visibility:NSItemProviderRepresentationVisibilityAll];
    evidence.inventory = @[AttachmentInventory(first, firstType, firstContents, completed),
                           AttachmentInventory(second, secondType, secondContents, held)];
    if (![evidence record:@"prepared"]) {
        self.status.text = @"Unable to save provider inventory";
        return;
    }
    if (![FirstDataType(completed) isEqualToString:firstType.identifier]
            || ![FirstDataType(held) isEqualToString:secondType.identifier]
            || ![completed hasItemConformingToTypeIdentifier:UTTypeFileURL.identifier]
            || ![held hasItemConformingToTypeIdentifier:UTTypeFileURL.identifier]) {
        [evidence record:@"registration-mismatch"];
        self.status.text = @"Expected the file content type before the file URL representation";
        return;
    }
    if (![evidence observeArm]) {
        [evidence record:@"arm-observer-failed"];
        self.status.text = @"Unable to observe held-provider arm signal";
        return;
    }
    UIImage *preview = [UIImage systemImageNamed:@"doc"];
    if (!preview) {
        [evidence record:@"preview-unavailable"];
        self.status.text = @"Unable to prepare an independent document preview";
        return;
    }
    UIActivityItemsConfiguration *configuration =
        [[UIActivityItemsConfiguration alloc] initWithItemProviders:@[completed, held]];
    NSArray<NSURL *> *urls = @[first, second];
    configuration.perItemMetadataProvider = ^id(NSInteger index, UIActivityItemsConfigurationMetadataKey key) {
        if (index >= 0 && (NSUInteger)index < urls.count && [key isEqual:UIActivityItemsConfigurationMetadataKeyTitle]) {
            return urls[index].lastPathComponent;
        }
        return nil;
    };
    configuration.previewProvider = ^NSItemProvider *(NSInteger index, UIActivityItemsConfigurationPreviewIntent intent,
                                                       CGSize suggestedSize) {
        return [[NSItemProvider alloc] initWithObject:preview];
    };
    UIActivityViewController *sheet = [[UIActivityViewController alloc]
        initWithActivityItemsConfiguration:configuration];
    [self presentSheet:sheet from:button];
}

- (void)shareOne:(UIButton *)button {
    UIActivityViewController *sheet = [[UIActivityViewController alloc]
        initWithActivityItems:@[self.fixtures[button.accessibilityIdentifier]] applicationActivities:nil];
    [self presentSheet:sheet from:button];
}

- (void)presentSheet:(UIActivityViewController *)sheet from:(UIButton *)button {
    sheet.popoverPresentationController.sourceView = button;
    sheet.popoverPresentationController.sourceRect = button.bounds;
    [self presentViewController:sheet animated:YES completion:nil];
}

- (void)open:(UIButton *)button {
    self.document = [UIDocumentInteractionController interactionControllerWithURL:self.fixtures[@"open-in"]];
    self.document.delegate = self;
    if (![self.document presentOpenInMenuFromRect:button.bounds inView:button animated:YES]) {
        self.status.text = @"iOS did not offer an Open In menu";
    }
}

- (void)documentInteractionController:(UIDocumentInteractionController *)controller
                       willBeginSendingToApplication:(NSString *)application {
    NSLog(@"IncomingSender Open In will send %@ to %@", controller.URL.lastPathComponent, application);
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
    @autoreleasepool {
        return UIApplicationMain(argc, argv, nil, @"SenderDelegate");
    }
}
