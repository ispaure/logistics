// Included by the generated launcher. Source of truth remains in the images owner.
#import <AVFoundation/AVFoundation.h>
#import <Photos/Photos.h>
#import <math.h>

@interface LGBurstCameraController : UIViewController <AVCapturePhotoCaptureDelegate>
@property(nonatomic, strong) AVCaptureSession *session;
@property(nonatomic, strong) AVCapturePhotoOutput *output;
@property(nonatomic, strong) AVCaptureVideoPreviewLayer *preview;
@property(nonatomic, strong) dispatch_queue_t cameraQueue;
@property(nonatomic, strong) dispatch_source_t timer;
@property(nonatomic, strong) UILabel *status;
@property(nonatomic, strong) UIButton *shutter;
@property(nonatomic, strong) UIButton *cameraChoice;
@property(nonatomic, strong) UIButton *rateChoice;
@property(nonatomic, copy) BOOL (^savePreferences)(NSString *, double);
@property(nonatomic) BOOL changingPreferences;
@property(nonatomic, strong) NSMutableDictionary<NSNumber *, id> *captures;
@property(nonatomic, copy) NSString *cameraKey;
@property(nonatomic, copy) NSString *cameraLabel;
@property(nonatomic) double framesPerSecond;
@property(nonatomic) BOOL holding;
@property(nonatomic) BOOL closing;
@property(nonatomic) NSUInteger saved;
@property(nonatomic) NSUInteger pending;
@property(nonatomic) NSUInteger failures;
@end

@implementation LGBurstCameraController
- (instancetype)init {
    if ((self = [super init])) {
        self.cameraKey = @"rear_wide";
        self.framesPerSecond = 8;
    }
    return self;
}
+ (AVCaptureDevice *)cameraForKey:(NSString *)key {
    AVCaptureDeviceType type = AVCaptureDeviceTypeBuiltInWideAngleCamera;
    AVCaptureDevicePosition position = AVCaptureDevicePositionBack;
    if ([key isEqualToString:@"rear_ultra_wide"]) type = AVCaptureDeviceTypeBuiltInUltraWideCamera;
    else if ([key isEqualToString:@"rear_telephoto"]) type = AVCaptureDeviceTypeBuiltInTelephotoCamera;
    else if ([key isEqualToString:@"front"]) position = AVCaptureDevicePositionFront;
    else if (![key isEqualToString:@"rear_wide"]) return nil;
    return [AVCaptureDevice defaultDeviceWithDeviceType:type mediaType:AVMediaTypeVideo position:position];
}
+ (NSArray<NSString *> *)availableCameraKeys {
    NSMutableArray *keys = NSMutableArray.new;
    for (NSString *key in @[@"rear_wide", @"rear_ultra_wide", @"rear_telephoto", @"front"]) {
        if ([self cameraForKey:key]) [keys addObject:key];
    }
    return keys;
}
- (double)captureInterval {
    double rate = self.framesPerSecond;
    if (!isfinite(rate) || rate < 1 || rate > 30) rate = 8;
    return 1.0 / rate;
}
+ (NSString *)titleForCameraKey:(NSString *)key {
    return @{@"rear_wide": @"Rear main (1×)", @"rear_ultra_wide": @"Rear ultra wide (0.5×)",
             @"rear_telephoto": @"Rear telephoto", @"front": @"Front"}[key] ?: @"Camera";
}
- (void)refreshChoiceMenus {
    __weak typeof(self) weakSelf = self;
    NSMutableArray *cameras = NSMutableArray.new;
    NSArray *keys = [LGBurstCameraController availableCameraKeys];
    for (NSString *key in keys) {
        UIAction *action = [UIAction actionWithTitle:[LGBurstCameraController titleForCameraKey:key] image:nil identifier:nil handler:^(UIAction *action) {
            [weakSelf selectCameraKey:key rate:weakSelf.framesPerSecond];
        }];
        action.state = [key isEqualToString:self.cameraKey] ? UIMenuElementStateOn : UIMenuElementStateOff;
        [cameras addObject:action];
    }
    if (![keys containsObject:self.cameraKey]) {
        UIAction *unavailable = [UIAction actionWithTitle:[[LGBurstCameraController titleForCameraKey:self.cameraKey] stringByAppendingString:@" (unavailable)"] image:nil identifier:nil handler:^(UIAction *action) {}];
        unavailable.attributes = UIMenuElementAttributesDisabled;
        [cameras addObject:unavailable];
    }
    self.cameraChoice.menu = [UIMenu menuWithTitle:@"Camera" children:cameras];
    [self.cameraChoice setTitle:[[LGBurstCameraController titleForCameraKey:self.cameraKey] stringByAppendingString:@" ▾"] forState:UIControlStateNormal];
    NSMutableArray *rates = NSMutableArray.new;
    for (NSInteger rate = 1; rate <= 30; rate++) {
        UIAction *action = [UIAction actionWithTitle:[NSString stringWithFormat:@"%ld pictures/s", (long)rate] image:nil identifier:nil handler:^(UIAction *action) {
            [weakSelf selectCameraKey:weakSelf.cameraKey rate:rate];
        }];
        action.state = rate == (NSInteger)self.framesPerSecond ? UIMenuElementStateOn : UIMenuElementStateOff;
        [rates addObject:action];
    }
    self.rateChoice.menu = [UIMenu menuWithTitle:@"Pictures per second" children:rates];
    [self.rateChoice setTitle:[NSString stringWithFormat:@"%.0f pictures/s ▾", self.framesPerSecond] forState:UIControlStateNormal];
}
- (void)enableChoicesIfIdle {
    BOOL enabled = !self.holding && !self.captures.count && !self.closing && !self.changingPreferences;
    dispatch_async(dispatch_get_main_queue(), ^{
        self.cameraChoice.enabled = enabled;
        self.rateChoice.enabled = enabled;
    });
}
- (void)selectCameraKey:(NSString *)key rate:(double)rate {
    if (self.changingPreferences || self.closing || !isfinite(rate) || rate < 1 || rate > 30 || floor(rate) != rate) return;
    if (![@[@"rear_wide", @"rear_ultra_wide", @"rear_telephoto", @"front"] containsObject:key]) return;
    self.changingPreferences = YES;
    self.cameraChoice.enabled = self.rateChoice.enabled = NO;
    self.shutter.enabled = NO;
    dispatch_async(self.cameraQueue, ^{
        BOOL busy = self.holding || self.captures.count > 0;
        dispatch_async(dispatch_get_main_queue(), ^{
            if (self.closing) { self.changingPreferences = NO; return; }
            if (busy || !self.savePreferences || !self.savePreferences(key, rate)) {
                self.status.text = busy ? @"Release the shutter and wait for capture to finish." : @"Could not save preferences. Check Settings → Camera.";
                self.changingPreferences = NO;
                self.shutter.enabled = self.session.isRunning;
                dispatch_async(self.cameraQueue, ^{ [self enableChoicesIfIdle]; });
                return;
            }
            BOOL switchCamera = ![self.cameraKey isEqualToString:key];
            self.cameraKey = key;
            self.framesPerSecond = rate;
            [self refreshChoiceMenus];
            if (switchCamera) [self configureCamera];
            else {
                self.changingPreferences = NO;
                self.shutter.enabled = self.session.isRunning;
                self.status.text = [NSString stringWithFormat:@"%.0f pictures/s requested · Saves to Photos", rate];
                dispatch_async(self.cameraQueue, ^{ [self enableChoicesIfIdle]; });
            }
        });
    });
}
- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.blackColor;
    self.cameraQueue = dispatch_queue_create("logistics.burst-camera", DISPATCH_QUEUE_SERIAL);
    self.captures = NSMutableDictionary.new;
    self.session = AVCaptureSession.new;
    self.output = AVCapturePhotoOutput.new;
    self.preview = [AVCaptureVideoPreviewLayer layerWithSession:self.session];
    self.preview.videoGravity = AVLayerVideoGravityResizeAspect;
    [self.view.layer addSublayer:self.preview];
    self.status = UILabel.new;
    self.status.text = @"Allow Camera and Photos access to begin.";
    self.status.textColor = UIColor.whiteColor;
    self.status.numberOfLines = 0;
    self.status.textAlignment = NSTextAlignmentCenter;
    self.status.accessibilityIdentifier = @"burst-camera-status";
    UIButton *done = [UIButton buttonWithType:UIButtonTypeSystem];
    [done setTitle:@"Done" forState:UIControlStateNormal];
    [done addTarget:self action:@selector(finish) forControlEvents:UIControlEventTouchUpInside];
    done.accessibilityIdentifier = @"burst-camera-done";
    self.cameraChoice = [UIButton buttonWithType:UIButtonTypeSystem];
    self.rateChoice = [UIButton buttonWithType:UIButtonTypeSystem];
    self.cameraChoice.accessibilityIdentifier = @"burst-camera-lens";
    self.rateChoice.accessibilityIdentifier = @"burst-camera-rate";
    for (UIButton *choice in @[self.cameraChoice, self.rateChoice]) {
        choice.showsMenuAsPrimaryAction = YES;
        choice.backgroundColor = [UIColor colorWithWhite:0 alpha:0.75];
        [choice setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
        choice.layer.cornerRadius = 10;
        choice.titleLabel.adjustsFontSizeToFitWidth = YES;
    }
    [self refreshChoiceMenus];
    self.shutter = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.shutter setTitle:@"Hold for burst" forState:UIControlStateNormal];
    self.shutter.accessibilityIdentifier = @"burst-camera-shutter";
    self.shutter.backgroundColor = UIColor.whiteColor;
    self.shutter.layer.cornerRadius = 32;
    self.shutter.enabled = NO;
    [self.shutter addTarget:self action:@selector(beginBurst) forControlEvents:UIControlEventTouchDown];
    [self.shutter addTarget:self action:@selector(endBurst) forControlEvents:(UIControlEventTouchUpInside | UIControlEventTouchUpOutside | UIControlEventTouchCancel | UIControlEventTouchDragExit)];
    [self.shutter addTarget:self action:@selector(accessibleShot) forControlEvents:UIControlEventPrimaryActionTriggered];
    for (UIView *view in @[done, self.cameraChoice, self.rateChoice, self.status, self.shutter]) {
        view.translatesAutoresizingMaskIntoConstraints = NO;
        [self.view addSubview:view];
    }
    UILayoutGuide *safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [done.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:20],
        [done.topAnchor constraintEqualToAnchor:safe.topAnchor constant:8],
        [done.heightAnchor constraintEqualToConstant:44],
        [self.cameraChoice.topAnchor constraintEqualToAnchor:done.bottomAnchor constant:8],
        [self.cameraChoice.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:16],
        [self.cameraChoice.heightAnchor constraintEqualToConstant:44],
        [self.rateChoice.topAnchor constraintEqualToAnchor:self.cameraChoice.topAnchor],
        [self.rateChoice.leadingAnchor constraintEqualToAnchor:self.cameraChoice.trailingAnchor constant:8],
        [self.rateChoice.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-16],
        [self.rateChoice.widthAnchor constraintEqualToAnchor:self.cameraChoice.widthAnchor],
        [self.rateChoice.heightAnchor constraintEqualToConstant:44],
        [self.shutter.centerXAnchor constraintEqualToAnchor:safe.centerXAnchor],
        [self.shutter.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor constant:-16],
        [self.shutter.widthAnchor constraintEqualToConstant:200],
        [self.shutter.heightAnchor constraintEqualToConstant:64],
        [self.status.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:16],
        [self.status.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-16],
        [self.status.bottomAnchor constraintEqualToAnchor:self.shutter.topAnchor constant:-12]
    ]];
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(suspend) name:UIApplicationWillResignActiveNotification object:nil];
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(resume) name:UIApplicationDidBecomeActiveNotification object:nil];
    [AVCaptureDevice requestAccessForMediaType:AVMediaTypeVideo completionHandler:^(BOOL granted) {
        dispatch_async(dispatch_get_main_queue(), ^{
            if (!granted) { self.status.text = @"Camera access denied. Enable Camera in Settings → Logistics."; return; }
            [PHPhotoLibrary requestAuthorizationForAccessLevel:PHAccessLevelAddOnly handler:^(PHAuthorizationStatus status) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    if (status != PHAuthorizationStatusAuthorized && status != PHAuthorizationStatusLimited) {
                        self.status.text = @"Photos access denied. Enable Add Photos in Settings → Logistics.";
                        return;
                    }
                    if (!self.closing) [self configureCamera];
                });
            }];
        });
    }];
}
- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    self.preview.frame = self.view.bounds;
    AVCaptureVideoOrientation orientation = (AVCaptureVideoOrientation)self.view.window.windowScene.interfaceOrientation;
    if (self.preview.connection.isVideoOrientationSupported) self.preview.connection.videoOrientation = orientation;
}
- (void)configureCamera {
    dispatch_async(self.cameraQueue, ^{
        NSError *error = nil;
        AVCaptureDevice *device = [LGBurstCameraController cameraForKey:self.cameraKey];
        BOOL fallback = device == nil;
        if (!device) device = [LGBurstCameraController cameraForKey:@"rear_wide"];
        self.cameraLabel = [device.localizedName stringByAppendingString:fallback ? @" (saved camera unavailable)" : @""];
        AVCaptureDeviceInput *input = device ? [AVCaptureDeviceInput deviceInputWithDevice:device error:&error] : nil;
        [self.session beginConfiguration];
        self.session.sessionPreset = AVCaptureSessionPresetPhoto;
        NSArray *previous = self.session.inputs.copy;
        for (AVCaptureInput *old in previous) [self.session removeInput:old];
        BOOL hasOutput = [self.session.outputs containsObject:self.output];
        if (!input || ![self.session canAddInput:input] || (!hasOutput && ![self.session canAddOutput:self.output])) {
            for (AVCaptureInput *old in previous) if ([self.session canAddInput:old]) [self.session addInput:old];
            [self.session commitConfiguration];
            dispatch_async(dispatch_get_main_queue(), ^{
                self.changingPreferences = NO;
                self.shutter.enabled = self.session.isRunning && !self.closing;
                self.status.text = error.localizedDescription ?: @"No camera available.";
                dispatch_async(self.cameraQueue, ^{ [self enableChoicesIfIdle]; });
            });
            return;
        }
        [self.session addInput:input];
        if (!hasOutput) [self.session addOutput:self.output];
        self.output.maxPhotoQualityPrioritization = AVCapturePhotoQualityPrioritizationBalanced;
        if (@available(iOS 17.0, *)) {
            if (self.output.isZeroShutterLagSupported) self.output.zeroShutterLagEnabled = YES;
            if (self.output.isResponsiveCaptureSupported) self.output.responsiveCaptureEnabled = YES;
        }
        [self.session commitConfiguration];
        if (!self.closing) [self.session startRunning];
        dispatch_async(dispatch_get_main_queue(), ^{
            self.changingPreferences = NO;
            self.shutter.enabled = self.session.isRunning && !self.closing;
            dispatch_async(self.cameraQueue, ^{ [self enableChoicesIfIdle]; });
            self.status.text = [NSString stringWithFormat:@"%@ · %.0f pictures/s requested · Saves to Photos", self.cameraLabel, 1.0 / [self captureInterval]];
        });
    });
}
- (void)beginBurst {
    AVCaptureVideoOrientation orientation = (AVCaptureVideoOrientation)self.view.window.windowScene.interfaceOrientation;
    dispatch_async(self.cameraQueue, ^{
        if (self.holding || self.closing || self.changingPreferences || !self.session.isRunning) return;
        dispatch_async(dispatch_get_main_queue(), ^{ self.cameraChoice.enabled = self.rateChoice.enabled = NO; });
        self.holding = YES;
        AVCaptureConnection *connection = [self.output connectionWithMediaType:AVMediaTypeVideo];
        if (connection.isVideoOrientationSupported) connection.videoOrientation = orientation;
        [self captureNext];
        self.timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, self.cameraQueue);
        uint64_t interval = (uint64_t)llround([self captureInterval] * NSEC_PER_SEC);
        dispatch_source_set_timer(self.timer, dispatch_time(DISPATCH_TIME_NOW, interval), interval, MIN(interval / 20, 10 * NSEC_PER_MSEC));
        __weak typeof(self) weakSelf = self;
        dispatch_source_set_event_handler(self.timer, ^{ [weakSelf captureNext]; });
        dispatch_resume(self.timer);
    });
}
- (void)captureNext {
    if (!self.holding || self.closing || !self.session.isRunning || self.captures.count >= 3 || self.pending >= 8) return;
    if (@available(iOS 17.0, *)) {
        if (self.output.captureReadiness != AVCapturePhotoOutputCaptureReadinessReady) return;
    }
    NSDictionary *format = [self.output.availablePhotoCodecTypes containsObject:AVVideoCodecTypeHEVC] ? @{AVVideoCodecKey:AVVideoCodecTypeHEVC} : @{AVVideoCodecKey:AVVideoCodecTypeJPEG};
    AVCapturePhotoSettings *settings = [AVCapturePhotoSettings photoSettingsWithFormat:format];
    settings.photoQualityPrioritization = AVCapturePhotoQualityPrioritizationBalanced;
    settings.flashMode = AVCaptureFlashModeOff;
    self.captures[@(settings.uniqueID)] = self; // retain delegate until terminal callback
    [self.output capturePhotoWithSettings:settings delegate:self];
}
- (void)endBurst {
    dispatch_async(self.cameraQueue, ^{
        self.holding = NO;
        if (self.timer) { dispatch_source_cancel(self.timer); self.timer = nil; }
        [self enableChoicesIfIdle];
    });
}
- (void)accessibleShot { if (UIAccessibilityIsVoiceOverRunning()) { [self beginBurst]; [self endBurst]; } }
- (void)updateStatus {
    NSString *text = [NSString stringWithFormat:@"%lu saved to Photos · %lu saving%@", (unsigned long)self.saved, (unsigned long)self.pending, self.failures ? @" · Save failed: originals kept in Files → Logistics → Local → Camera Pending" : @""];
    dispatch_async(dispatch_get_main_queue(), ^{ self.status.text = text; });
}
- (void)captureOutput:(AVCapturePhotoOutput *)output didFinishProcessingPhoto:(AVCapturePhoto *)photo error:(NSError *)error {
    NSData *data = error ? nil : photo.fileDataRepresentation;
    dispatch_async(self.cameraQueue, ^{
        if (!data) { self.failures++; [self updateStatus]; return; }
        NSURL *documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
        NSURL *folder = [documents URLByAppendingPathComponent:@"Local/Camera Pending" isDirectory:YES];
        NSError *writeError = nil;
        [NSFileManager.defaultManager createDirectoryAtURL:folder withIntermediateDirectories:YES attributes:nil error:&writeError];
        NSString *extension = [output.availablePhotoCodecTypes containsObject:AVVideoCodecTypeHEVC] ? @"heic" : @"jpg";
        NSURL *file = [folder URLByAppendingPathComponent:[NSUUID.UUID.UUIDString stringByAppendingPathExtension:extension]];
        if (![data writeToURL:file options:NSDataWritingAtomic error:&writeError]) {
            self.failures++;
            dispatch_async(dispatch_get_main_queue(), ^{ self.status.text = [@"Could not retain photo: " stringByAppendingString:writeError.localizedDescription]; });
            [self endBurst];
            return;
        }
        self.pending++;
        [self updateStatus];
        [PHPhotoLibrary.sharedPhotoLibrary performChanges:^{
            PHAssetCreationRequest *request = PHAssetCreationRequest.creationRequestForAsset;
            [request addResourceWithType:PHAssetResourceTypePhoto fileURL:file options:nil];
        } completionHandler:^(BOOL success, NSError *saveError) {
            dispatch_async(self.cameraQueue, ^{
                self.pending--;
                if (success) { self.saved++; [NSFileManager.defaultManager removeItemAtURL:file error:nil]; }
                else { self.failures++; [self endBurst]; }
                [self updateStatus];
            });
        }];
    });
}
- (void)captureOutput:(AVCapturePhotoOutput *)output didFinishCaptureForResolvedSettings:(AVCaptureResolvedPhotoSettings *)resolved error:(NSError *)error {
    dispatch_async(self.cameraQueue, ^{
        [self.captures removeObjectForKey:@(resolved.uniqueID)];
        [self enableChoicesIfIdle];
        if (error) { self.failures++; [self updateStatus]; }
    });
}
- (void)suspend { [self endBurst]; dispatch_async(self.cameraQueue, ^{ [self.session stopRunning]; }); }
- (void)resume { dispatch_async(self.cameraQueue, ^{ if (!self.closing && self.session.inputs.count) [self.session startRunning]; }); }
- (void)finish {
    self.closing = YES;
    self.shutter.enabled = NO;
    [self suspend];
    [self dismissViewControllerAnimated:YES completion:nil];
}
- (void)dealloc { [[NSNotificationCenter defaultCenter] removeObserver:self]; }
@end
