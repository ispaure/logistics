// Compiled with the production video controller in a disposable UIKit app.
@interface LGVideoChromeChecks : UIResponder <UIApplicationDelegate, UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) LGVideoController *video;
@property(nonatomic, strong) NSMutableArray *samples;
@property(nonatomic, strong) NSTimer *sampler;
@property(nonatomic) NSTimeInterval started;
@property(nonatomic) BOOL completed;
@property(nonatomic) int64_t firstVideoClock;
@property(nonatomic) float initialTimeline;
@property(nonatomic) BOOL initialTimelineHidden;
@end
@implementation LGVideoChromeChecks
- (NSString *)outputPath:(NSString *)name {
    NSString *folder = [NSBundle.mainBundle objectForInfoDictionaryKey:@"QAOutputDirectory"] ?: @"Documents";
    NSString *root = [NSHomeDirectory() stringByAppendingPathComponent:folder];
    [NSFileManager.defaultManager createDirectoryAtPath:root withIntermediateDirectories:YES attributes:nil error:nil];
    return [root stringByAppendingPathComponent:name];
}
- (AVSampleBufferDisplayLayer *)videoLayer:(CALayer *)layer {
    if ([layer isKindOfClass:AVSampleBufferDisplayLayer.class]) return (AVSampleBufferDisplayLayer *)layer;
    for (CALayer *child in layer.sublayers) {
        AVSampleBufferDisplayLayer *found = [self videoLayer:child];
        if (found) return found;
    }
    return nil;
}
- (void)finish:(NSString *)error {
    if (self.completed) return;
    self.completed = YES;
    int64_t duration = [[NSBundle.mainBundle objectForInfoDictionaryKey:@"QADuration"] longLongValue] ?: 30000;
    int64_t resume = [[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAResume"] longLongValue];
    if (!error && resume > 0 && ((![[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAUnknownDuration"] boolValue] && fabs(self.initialTimeline - resume / (double)duration) > .01) || self.initialTimelineHidden || self.firstVideoClock < resume - 1500
            || llabs(self.video.player.media.length.value.longLongValue - duration) > 100))
        error = @"Resume timeline or first decoded timestamp started before the saved position";
    AVSampleBufferDisplayLayer *layer = [self videoLayer:self.video.movie.layer];
    BOOL hdrEnabled = NO;
    BOOL ready = NO;
    if (@available(iOS 17.4, *)) ready = layer.readyForDisplay;
    NSMutableDictionary *pixelEvidence = [NSMutableDictionary dictionary];
    if (@available(iOS 17.4, *)) {
        CVPixelBufferRef pixels = [layer.sampleBufferRenderer copyDisplayedPixelBuffer];
        if (pixels) {
            pixelEvidence[@"format"] = @(CVPixelBufferGetPixelFormatType(pixels));
            for (NSString *key in @[(__bridge NSString *)kCVImageBufferTransferFunctionKey,
                                     (__bridge NSString *)kCVImageBufferColorPrimariesKey]) {
                CFTypeRef value = CVBufferGetAttachment(pixels, (__bridge CFStringRef)key, NULL);
                if (value) pixelEvidence[key] = (__bridge id)value;
            }
            CVPixelBufferRelease(pixels);
        }
    }
    if (@available(iOS 26.0, *)) hdrEnabled = [layer.preferredDynamicRange isEqualToString:CADynamicRangeHigh];
    else if (@available(iOS 17.0, *)) hdrEnabled = layer.wantsExtendedDynamicRangeContent;
    if (!error && [[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAHDR"] boolValue] &&
        (!ready || !hdrEnabled || self.video.player.time.intValue < 1000))
        error = @"HDR fixture did not reach an EDR-enabled sample-buffer display";
    [self.sampler invalidate];
    NSDictionary *report = @{@"success": @(!error), @"error": error ?: @"", @"samples": self.samples ?: @[],
        @"scope": [[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAHDRProbe"] boolValue]
            ? @"Physical device; real UIKit controller and VLC; synthetic local HDR movie"
            : ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAStreamProbe"] boolValue]
                ? @"Real UIKit/VLC and retained rclone range transport; delayed synthetic MKV; simulator"
                : @"Real UIKit controller and VLC; synthetic local movie; simulator only")};
    NSMutableDictionary *details = [report mutableCopy];
    details[@"bounds"] = NSStringFromCGRect(self.window.bounds);
    details[@"orientation"] = @(self.window.windowScene.interfaceOrientation);
    details[@"idiom"] = @(self.video.traitCollection.userInterfaceIdiom);
    details[@"hdrLayerEnabled"] = @(hdrEnabled);
    details[@"videoReadyForDisplay"] = @(ready);
    details[@"displayedPixelBuffer"] = pixelEvidence;
    details[@"hdrActiveObserved"] = @(ready && hdrEnabled && self.window.screen.currentEDRHeadroom > 1
        && [pixelEvidence[(__bridge NSString *)kCVImageBufferTransferFunctionKey] isEqual:(__bridge NSString *)kCVImageBufferTransferFunction_SMPTE_ST_2084_PQ]
        && [pixelEvidence[@"format"] unsignedIntValue] == kCVPixelFormatType_420YpCbCr10BiPlanarVideoRange);
    details[@"currentEDRHeadroom"] = @(self.window.screen.currentEDRHeadroom);
    details[@"potentialEDRHeadroom"] = @(self.window.screen.potentialEDRHeadroom);
    details[@"initialTimelineHidden"] = @(self.initialTimelineHidden);
    details[@"initialTimeline"] = @(self.initialTimeline);
    details[@"firstVideoClock"] = @(self.firstVideoClock);
    report = details;
    NSString *path = [self outputPath:@"result.json"];
    [[NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:nil] writeToFile:path atomically:YES];
    if ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAHDRProbe"] boolValue]) {
        NSData *encoded = [NSJSONSerialization dataWithJSONObject:report options:0 error:nil];
        printf("LOGISTICS_HDR_RESULT=%s\n", [[NSString alloc] initWithData:encoded encoding:NSUTF8StringEncoding].UTF8String);
        fflush(stdout);
        exit(0);
    }
}
- (BOOL)application:(UIApplication *)app didFinishLaunchingWithOptions:(NSDictionary *)options { return YES; }
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    self.samples = [NSMutableArray array];
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
#ifdef LG_VIDEO_FOLD_QA
    self.video = [LGVideoPoseQAController new];
#else
    self.video = [LGVideoController new];
#endif
    NSString *remoteURL = [NSBundle.mainBundle objectForInfoDictionaryKey:@"QAURL"];
    self.video.videoURL = remoteURL.length ? remoteURL : [[NSBundle.mainBundle URLForResource:@"fixture" withExtension:@"mp4"] absoluteString];
    self.video.startMilliseconds = [[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAResume"] longLongValue];
    self.video.knownDuration = [[NSBundle.mainBundle objectForInfoDictionaryKey:@"QADuration"] longLongValue] ?: 30000;
    if ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAUnknownDuration"] boolValue]) self.video.knownDuration = 0;
    self.video.subtitleJSON = @"[]";
    self.video.queueJSON = @"[]";
    self.video.optionsJSON = @"{\"video_title\":\"A long video filename for title alignment.mp4\",\"source_label\":\"Cloud file\",\"source_remote\":true}";
    self.video.allowed = ^BOOL(BOOL external) { return YES; };
    self.video.requestPlay = ^BOOL { return YES; };
    self.window.rootViewController = [[LGVideoNavigationController alloc] initWithRootViewController:self.video];
    [self.window makeKeyAndVisible];
    [self.video tick:nil];
    self.initialTimeline = self.video.seek.value;
    self.initialTimelineHidden = self.video.seek.hidden;
    if ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAOrientation"] isEqualToString:@"landscape"]) {
        UIWindowSceneGeometryPreferencesIOS *geometry = [[UIWindowSceneGeometryPreferencesIOS alloc]
            initWithInterfaceOrientations:UIInterfaceOrientationMaskLandscapeLeft];
        [(UIWindowScene *)scene requestGeometryUpdateWithPreferences:geometry errorHandler:^(NSError *error) {
            [self finish:error.localizedDescription];
        }];
    }
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, .5 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        self.video.player.audio.muted = YES;
        if ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAStreamProbe"] boolValue]) [self.video setNetworkWaiting:YES];
        [self.video startByUser];
        self.started = NSProcessInfo.processInfo.systemUptime;
        if ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAHDRProbe"] boolValue]) {
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 12 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
                [self.video.player pause];
                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, .4 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{ [self finish:nil]; });
            });
            return;
        }
        self.sampler = [NSTimer scheduledTimerWithTimeInterval:1.0/60 target:self selector:@selector(sample:) userInfo:nil repeats:YES];
    });
}
- (void)sample:(NSTimer *)timer {
    LGVideoController *v = self.video;
    if (!self.firstVideoClock && v.player.media.statistics.displayedPictures > 0 && v.player.time.value.longLongValue > 0)
        self.firstVideoClock = v.player.time.value.longLongValue;
    CGFloat opacity = ((CALayer *)v.controlsScroll.layer.presentationLayer).opacity;
    CGFloat barOpacity = ((CALayer *)v.navigationController.navigationBar.layer.presentationLayer).opacity;
    CGRect headerFrame = [v.videoHeader convertRect:v.videoHeader.bounds toView:self.window];
    [self.samples addObject:@{@"time": @(NSProcessInfo.processInfo.systemUptime-self.started),
        @"opacity": @(opacity), @"barOpacity": @(barOpacity), @"visible": @(v.controlsVisible),
        @"systemHidden": @(v.systemChromeHidden), @"headerY": @(CGRectGetMinY(headerFrame)),
        @"statusHidden": @(self.window.windowScene.statusBarManager.statusBarHidden),
        @"playing": @(v.player.isPlaying), @"decoderClock": v.player.time.value ?: @(-1),
        @"shownClock": @([v positionMilliseconds]), @"timelineHidden": @(v.seek.hidden), @"spinner": @(v.bufferSpinner.isAnimating), @"nativeDuration": v.player.media.length.value ?: @(-1), @"nativePosition": @(v.player.position), @"slider": @(v.seek.value)}];
    if ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAStreamProbe"] boolValue]) {
        if (self.firstVideoClock > 0) [v setNetworkWaiting:NO];
        int64_t target = [[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAResume"] longLongValue];
        if (self.firstVideoClock > 0 && v.player.time.value.longLongValue >= target + 1000) [self finish:nil];
        else if (NSProcessInfo.processInfo.systemUptime-self.started > 80) [self finish:@"Remote resume did not produce frames within 80 seconds"];
        return;
    }
    if (NSProcessInfo.processInfo.systemUptime-self.started > 15) { [self finish:@"Initial playback did not auto-hide controls"]; return; }
    if (!v.controlsScroll.hidden) return;
    [timer invalidate];
    BOOL faded = NO;
    NSNumber *fadeY = nil;
    for (NSDictionary *row in self.samples) {
        float alpha = [row[@"opacity"] floatValue];
        if (alpha > .01 && alpha < .99) {
            faded = YES;
            if (fabs([row[@"barOpacity"] doubleValue] - alpha) > .1) {
                [self finish:@"Navigation and timeline fades are out of sync"]; return;
            }
            // UIKit normally omits the phone status bar in landscape. Only
            // reject a disappearance relative to the initial visible state.
            BOOL statusDisappeared = ![self.samples.firstObject[@"statusHidden"] boolValue]
                && [row[@"statusHidden"] boolValue];
            if ([row[@"systemHidden"] boolValue] || statusDisappeared) {
                [self finish:@"System chrome disappeared before the control fade completed"]; return;
            }
            if (!fadeY) fadeY = row[@"headerY"];
            else if (fabs([fadeY doubleValue]-[row[@"headerY"] doubleValue]) > 1) {
                [self finish:@"Visible header moved during fade"]; return;
            }
        }
    }
    if (!faded && !UIAccessibilityIsReduceMotionEnabled()) { [self finish:@"Controls disappeared without intermediate opacity"]; return; }
    if (!v.fullscreen || !v.systemChromeHidden) { [self finish:@"Initial fullscreen chrome did not commit"]; return; }
#ifdef LG_VIDEO_FOLD_QA
    [(LGVideoPoseQAController *)v applyTestFold:YES];
#endif
    [v setControlsShown:YES];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, .4 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{ [self menus:0]; });
}
- (void)menus:(NSUInteger)index {
    if (index == 0) {
        LGVideoController *v = self.video;
        CGRect track = [v.seek trackRectForBounds:v.seek.bounds];
        CGRect strip = v.cacheStrip.frame;
        if (fabs(CGRectGetMinX(track) - CGRectGetMinX(strip)) > .5 ||
            fabs(CGRectGetMaxX(track) - CGRectGetMaxX(strip)) > .5) {
            [self finish:@"Cached ranges do not align with the native seek track"]; return;
        }
        CGFloat expectedGap = .6 * (CGRectGetHeight(v.seek.bounds) - CGRectGetMaxY(track) + 4);
        if (fabs(CGRectGetMinY(strip) - CGRectGetMaxY(track) - expectedGap) > .5) {
            [self finish:@"Cached ranges did not move 40 percent closer"]; return;
        }
        if ((v.navigationItem.titleView != v.videoHeader && v.videoHeader.superview != v.view && v.videoHeader.superview != v.controls) || !v.videoHeader.window ||
            v.videoHeader.bounds.size.width < 44 || v.videoTitle.textAlignment != NSTextAlignmentCenter) {
            [self finish:@"Video identity is not centered in the native title area"]; return;
        }
        [v showCachedRanges:@"{\"ranges\":[[0,0.3],[0.5,0.65],[0.8,1]]}"];
        CGRect title = [v.videoHeader convertRect:v.videoHeader.bounds toView:self.window];
        if (v.tabletop) {
            CGRect deck = [v.controlsScroll convertRect:v.controlsScroll.bounds toView:self.window];
            CGRect movie = [v.movie convertRect:v.movie.bounds toView:self.window];
            if (!CGRectContainsRect(deck, title) || CGRectGetMinY(title) < CGRectGetMaxY(movie) ||
                fabs(CGRectGetMidX(title) - CGRectGetMidX(deck)) > 1) {
                [self finish:@"Laptop title is not centered inside the lower control deck"]; return;
            }
        }
        CGRect filename = [v.videoTitle convertRect:v.videoTitle.bounds toView:self.window];
        UIView *source = v.sourceLabel.superview;
        CGRect details = [source convertRect:source.bounds toView:self.window];
        if (fabs(CGRectGetMidX(filename) - CGRectGetMidX(details)) > .5) {
            [self finish:@"Storage details are not centered beneath the filename"]; return;
        }
        [self.samples addObject:@{@"titleFrame": NSStringFromCGRect(title),
            @"trackFrame": NSStringFromCGRect(track), @"cacheFrame": NSStringFromCGRect(strip)}];
        UIGraphicsImageRenderer *renderer = [[UIGraphicsImageRenderer alloc] initWithBounds:self.window.bounds];
        UIImage *image = [renderer imageWithActions:^(UIGraphicsImageRendererContext *context) {
            [self.window drawViewHierarchyInRect:self.window.bounds afterScreenUpdates:YES];
        }];
        [UIImagePNGRepresentation(image) writeToFile:[self outputPath:@"controls.png"] atomically:YES];
    }
    NSString *progress = [self outputPath:@"progress.json"];
    [[NSJSONSerialization dataWithJSONObject:@{@"fadePassed": @YES, @"menuIndex": @(index)} options:0 error:nil]
        writeToFile:progress atomically:YES];
    NSArray *selectors = @[@"playbackTools:", @"speedOptions:", @"pictureOptions:", @"subtitleOptions:", @"queueVideos:"];
    if (index >= selectors.count) { [self finish:nil]; return; }
    @try {
        UIBarButtonItem *sender = nil;
        for (UIBarButtonItem *item in self.video.mediaItems)
            if ([item.accessibilityLabel isEqualToString:@"More playback options"]) sender = item;
        SEL selector = NSSelectorFromString(selectors[index]);
        void (*invoke)(id,SEL,id) = (void (*)(id,SEL,id))[self.video methodForSelector:selector];
        invoke(self.video, selector, sender);
        UIAlertController *menu = (UIAlertController *)self.video.presentedViewController;
        if (!menu) { [self finish:@"Playback menu did not present"]; return; }
        NSUInteger cancel = 0;
        for (UIAlertAction *action in menu.actions) if (action.style == UIAlertActionStyleCancel) cancel++;
        if (cancel != 1) { [self finish:@"Playback menu must have exactly one Cancel action"]; return; }
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, .4 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            [menu dismissViewControllerAnimated:NO completion:^{ [self menus:index+1]; }];
        });
    } @catch (NSException *exception) { [self finish:exception.reason]; }
}
@end
int main(int argc, char **argv) {
    if (argc > 1 && strcmp(argv[1], "--cleanup-video-qa") == 0) {
        @autoreleasepool {
            NSString *folder = [NSBundle.mainBundle objectForInfoDictionaryKey:@"QAOutputDirectory"];
            if ([folder hasPrefix:@"Library/Caches/LogisticsVideoQA-"])
                [NSFileManager.defaultManager removeItemAtPath:[NSHomeDirectory() stringByAppendingPathComponent:folder] error:nil];
            return 0;
        }
    }
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(LGVideoChromeChecks.class)); }
}
