#import <UIKit/UIKit.h>
#import <AVFoundation/AVFoundation.h>

@interface LogisticsReaderCoverDisplay : NSObject
@property (atomic, copy) NSString *lastStatus;
+ (BOOL)supported;
+ (BOOL)ownsSceneRole:(UISceneSessionRole)role;
+ (instancetype)sharedDisplay;
- (void)showCover:(UIImage *)cover fromController:(UIViewController *)controller;
- (void)clearCover;
- (UIWindow *)connectScene:(UIWindowScene *)scene token:(id)token;
- (void)disconnectScene:(UIWindowScene *)scene;
@end

#if __has_include(<UIKit/UIHingeInteraction.h>)
@interface LogisticsReaderCoverDisplay () <AVCaptureVideoDataOutputSampleBufferDelegate>
@property (nonatomic, weak) UIViewController *readerController;
@property (nonatomic, strong) UIImage *cover;
@property (nonatomic) BOOL requestingPermission;
@property (nonatomic, strong) id registration;
@property (atomic, strong) NSString *captureToken;
@property (nonatomic, strong) dispatch_queue_t captureQueue;
@property (nonatomic, strong) dispatch_queue_t frameQueue;
@property (nonatomic, strong) AVCaptureSession *session;  // Capture queue only.
@property (nonatomic, strong) UIWindow *coverWindow;
@end
#endif

@implementation LogisticsReaderCoverDisplay
+ (BOOL)supported {
#if __has_include(<UIKit/UIHingeInteraction.h>)
    if (@available(iOS 27.1, *)) {
        return UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPhone;
    }
#endif
    return NO;
}

+ (BOOL)ownsSceneRole:(UISceneSessionRole)role {
#if __has_include(<UIKit/UIHingeInteraction.h>)
    if (@available(iOS 27.1, *)) {
        return [role isEqualToString:UIWindowSceneSessionRoleCameraCaptureAccessory];
    }
#endif
    return NO;
}

+ (instancetype)sharedDisplay {
    static LogisticsReaderCoverDisplay *display;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ display = [self new]; });
    return display;
}

#if __has_include(<UIKit/UIHingeInteraction.h>)
- (instancetype)init {
    self = [super init];
    if (self) {
        _captureQueue = dispatch_queue_create("io.github.ispaure.reader-cover-camera", DISPATCH_QUEUE_SERIAL);
        _frameQueue = dispatch_queue_create("io.github.ispaure.reader-cover-frames", DISPATCH_QUEUE_SERIAL);
    }
    return self;
}

- (void)stopPresentation {
    ((UIImageView *)self.coverWindow.rootViewController.view).image = nil;
    self.coverWindow.hidden = YES;
    self.coverWindow = nil;
    if (@available(iOS 27.1, *)) {
        if (self.registration) {
            [self.readerController unregisterSceneAccessory:self.registration];
            self.registration = nil;
        }
    }
    if (self.captureToken) {
        self.captureToken = nil;
        dispatch_async(self.captureQueue, ^{
            [self.session stopRunning];
            self.session = nil;
        });
    }
}

- (void)updatePresentation API_AVAILABLE(ios(27.1)) {
    UIWindow *window = self.readerController.viewIfLoaded.window;
    if (!self.cover || !window ||
        window.windowScene.activationState != UISceneActivationStateForegroundActive) {
        self.lastStatus = @"The iOS window is not in the foreground.";
        [self stopPresentation];
        return;
    }

    AVAuthorizationStatus authorization = [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeVideo];
    if (authorization == AVAuthorizationStatusNotDetermined && !self.requestingPermission) {
        self.requestingPermission = YES;
        self.lastStatus = @"Waiting for camera permission.";
        [AVCaptureDevice requestAccessForMediaType:AVMediaTypeVideo completionHandler:^(BOOL granted) {
            dispatch_async(dispatch_get_main_queue(), ^{
                self.requestingPermission = NO;
                if (granted && self.cover) [self updatePresentation];
                if (!granted) self.lastStatus = @"Camera access is denied.";
            });
        }];
    }
    if (authorization == AVAuthorizationStatusDenied || authorization == AVAuthorizationStatusRestricted) {
        self.lastStatus = @"Camera access is denied or restricted.";
    }
    if (authorization != AVAuthorizationStatusAuthorized || self.captureToken) return;

    self.lastStatus = @"Starting the rear camera.";
    NSString *token = NSUUID.UUID.UUIDString;
    UISceneConfiguration *configuration = [[UISceneConfiguration alloc]
        initWithName:@"Logistics reader cover" sessionRole:UIWindowSceneSessionRoleCameraCaptureAccessory];
    configuration.sceneClass = UIWindowScene.class;
    configuration.delegateClass = NSClassFromString(@"LogisticsSceneDelegate");
    self.captureToken = token;
    self.registration = [self.readerController registerSceneAccessory:
        [UISceneAccessory cameraCaptureSceneAccessoryWithConfiguration:configuration userInfo:token]];

    dispatch_async(self.captureQueue, ^{
        if (![self.captureToken isEqualToString:token]) return;
        AVCaptureDevice *camera = [AVCaptureDevice defaultDeviceWithDeviceType:AVCaptureDeviceTypeBuiltInWideAngleCamera
            mediaType:AVMediaTypeVideo position:AVCaptureDevicePositionBack];
        AVCaptureDeviceInput *input = camera ? [AVCaptureDeviceInput deviceInputWithDevice:camera error:NULL] : nil;
        AVCaptureSession *session = [AVCaptureSession new];
        AVCaptureVideoDataOutput *output = [AVCaptureVideoDataOutput new];
        // Keep a live video pipeline while discarding every frame.
        if (!input || ![session canAddInput:input]) {
            if ([self.captureToken isEqualToString:token]) self.lastStatus = @"The rear camera input is unavailable.";
            return;
        }
        [session addInput:input];
        if (![session canAddOutput:output]) {
            if ([self.captureToken isEqualToString:token]) self.lastStatus = @"The camera could not provide video frames.";
            return;
        }
        [session addOutput:output];
        output.alwaysDiscardsLateVideoFrames = YES;
        [output setSampleBufferDelegate:self queue:self.frameQueue];
        if ([session canSetSessionPreset:AVCaptureSessionPresetLow]) session.sessionPreset = AVCaptureSessionPresetLow;
        if (![self.captureToken isEqualToString:token]) return;
        self.session = session;
        [session startRunning];
        BOOL running = session.isRunning;
        dispatch_async(dispatch_get_main_queue(), ^{
            if ([self.captureToken isEqualToString:token] && !self.coverWindow) {
                self.lastStatus = running ? @"Camera running. Waiting for iOS to present the cover."
                                          : @"The camera session did not start.";
            }
        });
    });
}

- (void)captureOutput:(AVCaptureOutput *)output
    didOutputSampleBuffer:(CMSampleBufferRef)sampleBuffer
    fromConnection:(AVCaptureConnection *)connection {
    // No preview, processing or recording.
}
#endif

- (void)showCover:(UIImage *)cover fromController:(UIViewController *)controller {
#if __has_include(<UIKit/UIHingeInteraction.h>)
    if (@available(iOS 27.1, *)) {
        if (![LogisticsReaderCoverDisplay supported]) return;
        if (self.readerController != controller) [self clearCover];
        self.cover = cover;
        self.readerController = controller;
        [self updatePresentation];
    }
#endif
}

- (void)clearCover {
#if __has_include(<UIKit/UIHingeInteraction.h>)
    [self stopPresentation];
    self.readerController = nil;
    self.cover = nil;
#endif
}

- (UIWindow *)connectScene:(UIWindowScene *)scene token:(id)token {
#if __has_include(<UIKit/UIHingeInteraction.h>)
    if (!self.captureToken || ![self.captureToken isEqual:token] || !self.cover) return nil;
    UIWindow *window = [[UIWindow alloc] initWithWindowScene:scene];
    UIImageView *image = [[UIImageView alloc] initWithImage:self.cover];
    image.contentMode = UIViewContentModeScaleAspectFit;
    image.backgroundColor = UIColor.blackColor;
    image.accessibilityLabel = @"Current reading cover";
    UIViewController *controller = [UIViewController new];
    controller.view = image;
    window.rootViewController = controller;
    self.coverWindow = window;
    self.lastStatus = @"iOS connected the outer-display cover scene.";
    window.hidden = NO;
    return window;
#else
    return nil;
#endif
}

- (void)disconnectScene:(UIWindowScene *)scene {
#if __has_include(<UIKit/UIHingeInteraction.h>)
    if (self.coverWindow.windowScene == scene) {
        ((UIImageView *)self.coverWindow.rootViewController.view).image = nil;
        self.coverWindow = nil;
    }
#endif
}
@end
