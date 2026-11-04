// Compiled with the production video controller in a disposable UIKit app.
// Supply locations to the real gesture delegate without private event injection.
@interface LGVideoMenuTouch : UITouch
@property(nonatomic, strong) UIView *coordinateView;
@property(nonatomic) CGPoint point;
@end
@implementation LGVideoMenuTouch
- (CGPoint)locationInView:(UIView *)view { return [self.coordinateView convertPoint:self.point toView:view]; }
@end
@interface LGVideoChromeChecks : UIResponder <UIApplicationDelegate, UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) LGVideoController *video;
@property(nonatomic, strong) NSMutableArray *samples;
@property(nonatomic, strong) NSTimer *sampler;
@property(nonatomic) NSTimeInterval started;
@property(nonatomic) BOOL completed;
@property(nonatomic, copy) NSString *deckCommand;
@property(nonatomic) BOOL pauseChecksStarted;
@property(nonatomic, strong) NSMutableArray *hdrTransitions;
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
- (NSString *)presentationError:(NSDictionary *)state maximum:(BOOL)maximum {
    if (![state[@"ready"] boolValue] || [state[@"status"] integerValue] != AVQueuedSampleBufferRenderingStatusRendering ||
        [state[@"snapshotOverlay"] boolValue] || !state[@"pixelFormat"])
        return @"Native video is not ready or is covered by a snapshot";
    if (@available(iOS 26.0, *)) {
        if (![state[@"dynamicRange"] isEqual:maximum ? CADynamicRangeHigh : CADynamicRangeAutomatic])
            return @"Requested HDR mode was not applied to the video layer";
    } else if (![state[@"extendedRange"] boolValue]) return @"Extended range is disabled";
    if ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAHDR"] boolValue]) {
        NSDictionary *metadata = state[@"pixelAttachments"];
        if (![metadata[(__bridge NSString *)kCVImageBufferColorPrimariesKey] isEqual:(__bridge NSString *)kCVImageBufferColorPrimaries_ITU_R_2020] ||
            ![metadata[(__bridge NSString *)kCVImageBufferTransferFunctionKey] isEqual:(__bridge NSString *)kCVImageBufferTransferFunction_SMPTE_ST_2084_PQ] ||
            ![metadata[(__bridge NSString *)kCVImageBufferYCbCrMatrixKey] isEqual:(__bridge NSString *)kCVImageBufferYCbCrMatrix_ITU_R_2020])
            return @"PQ fixture lost required BT.2020/PQ/matrix attachments";
    }
    if ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAHDRProbe"] boolValue] &&
        (![state[@"pixelFormat"] isEqual:@"x420"] || [state[@"currentEDRHeadroom"] doubleValue] <= 1))
        return @"Physical HDR fixture lacks 10-bit video-range output or active EDR headroom";
    return nil;
}
- (void)checkPauseMode:(BOOL)maximum {
    [self.video setForcedMaximumHDRForSession:maximum];
    [self.video startByUser];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        NSDictionary *playing = [self.video hdrPresentationState];
        [self.hdrTransitions addObject:@{@"event": @"playing", @"presentation": playing}];
        NSString *error = [self presentationError:playing maximum:maximum];
        if (error || !self.video.player.isPlaying) { [self finish:error ?: @"Playback did not start"]; return; }
        [self.video pause]; // Exercise the production action, including pause presentation.
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            NSDictionary *paused = [self.video hdrPresentationState];
            [self.hdrTransitions addObject:@{@"event": @"paused", @"presentation": paused}];
            NSString *error = [self presentationError:paused maximum:maximum];
            if (error) { [self finish:error]; return; }
            if (self.video.pauseSnapshot || self.video.player.state != VLCMediaPlayerStatePaused ||
                ![playing[@"sampleBufferLayer"] isEqual:paused[@"sampleBufferLayer"]] ||
                !playing[@"pixelFormat"] || ![playing[@"pixelFormat"] isEqual:paused[@"pixelFormat"]] ||
                ![playing[@"pixelAttachments"] isEqual:paused[@"pixelAttachments"]] ||
                ![(playing[@"dynamicRange"] ?: playing[@"extendedRange"]) isEqual:(paused[@"dynamicRange"] ?: paused[@"extendedRange"])]) {
                [self finish:@"Pause replaced the native presentation, lost color metadata, or was not acknowledged"]; return;
            }
            [self.video startByUser];
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), dispatch_get_main_queue(), ^{
                NSDictionary *resumed = [self.video hdrPresentationState];
                [self.hdrTransitions addObject:@{@"event": @"resumed", @"presentation": resumed}];
                NSString *error = [self presentationError:resumed maximum:maximum];
                if (error) { [self finish:error]; return; }
                if ([resumed[@"clock"] longLongValue] <= [paused[@"clock"] longLongValue]) {
                    [self finish:@"Resume did not advance the media clock"]; return;
                }
                if (!self.video.player.isPlaying || self.video.pauseSnapshot ||
                    ![paused[@"sampleBufferLayer"] isEqual:resumed[@"sampleBufferLayer"]] ||
                    ![paused[@"pixelFormat"] isEqual:resumed[@"pixelFormat"]] ||
                    ![paused[@"pixelAttachments"] isEqual:resumed[@"pixelAttachments"]] ||
                    ![(paused[@"dynamicRange"] ?: paused[@"extendedRange"]) isEqual:(resumed[@"dynamicRange"] ?: resumed[@"extendedRange"])]) {
                    [self finish:@"Resume changed the native presentation or color metadata"]; return;
                }
                if (!maximum) [self checkPauseMode:YES];
                else { [self.video setForcedMaximumHDRForSession:NO]; [self finish:nil]; }
            });
        });
    });
}
- (void)finish:(NSString *)error {
    if (self.completed) return;
    if (!error && !self.pauseChecksStarted &&
        ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAPauseTransitions"] boolValue] ||
         [[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAHDRProbe"] boolValue]) &&
        [self videoLayer:self.video.movie.layer]) {
        self.pauseChecksStarted = YES;
        [self.sampler invalidate];
        self.hdrTransitions = [NSMutableArray array];
        [self checkPauseMode:NO];
        return;
    }
    self.completed = YES;
    if (error && self.window) {
        UIGraphicsImageRenderer *renderer = [[UIGraphicsImageRenderer alloc] initWithBounds:self.window.bounds];
        UIImage *image = [renderer imageWithActions:^(UIGraphicsImageRendererContext *context) {
            [self.window drawViewHierarchyInRect:self.window.bounds afterScreenUpdates:YES];
        }];
        [UIImagePNGRepresentation(image) writeToFile:[self outputPath:@"failure.png"] atomically:YES];
    }
    if (!error && ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAPauseTransitions"] boolValue] ||
        [[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAHDRProbe"] boolValue]) && self.hdrTransitions.count != 6)
        error = @"No sample-buffer layer available for transition checks";
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
    if (@available(iOS 26.0, *)) hdrEnabled = [layer.preferredDynamicRange isEqualToString:CADynamicRangeHigh] ||
        [layer.preferredDynamicRange isEqualToString:CADynamicRangeAutomatic];
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
    details[@"hdrTransitions"] = self.hdrTransitions ?: @[];
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
- (void)checkPipControls {
    [self.video pause];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        __block int calls = 0;
        int64_t before = [self.video positionMilliseconds];
        [self.video seekBy:10000 completion:^{ calls++; }];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            int64_t forward = [self.video positionMilliseconds];
            if (calls != 1 || llabs(forward - before - 10000) > 500) { [self finish:@"PiP forward seek or completion failed"]; return; }
            [self.video seekBy:-10000 completion:^{ calls++; }];
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), dispatch_get_main_queue(), ^{
                if (calls != 2 || llabs([self.video positionMilliseconds] - before) > 500) { [self finish:@"PiP backward seek or completion failed"]; return; }
                [self.video seekBy:-60000 completion:^{ calls++; }];
                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), dispatch_get_main_queue(), ^{
                    if (calls != 3 || [self.video positionMilliseconds] != 0) { [self finish:@"PiP start boundary was not clamped"]; return; }
                    [self.video seekBy:-10000 completion:^{ calls++; }];
                    dispatch_async(dispatch_get_main_queue(), ^{
                        if (calls != 4) { [self finish:@"PiP no-op seek did not complete"]; return; }
                        self.video.controlsLocked = YES;
                        if ([self.video isMediaSeekable]) { [self finish:@"PiP ignored control lock"]; return; }
                        for (UIView *view in self.video.controls.arrangedSubviews)
                            if ([view isKindOfClass:UIButton.class] && [[(UIButton *)view currentTitle] isEqualToString:@"Undo seek"]) {
                                [self finish:@"Mobile exposed Undo seek"]; return;
                            }
                        [self.samples addObject:@{@"pipDelegateForwardBackwardBoundaryAndLock": @YES, @"completionCalls": @(calls)}];
                        [self finish:nil];
                    });
                });
            });
        });
    });
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
        self.sampler = [NSTimer scheduledTimerWithTimeInterval:1.0/60 target:self selector:@selector(sample:) userInfo:nil repeats:YES];
        if ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAPipControls"] boolValue]) {
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 3 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{ [self checkPipControls]; });
            return;
        }
        if ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAHDRProbe"] boolValue] ||
            [[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAPauseTransitions"] boolValue]) {
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 3 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
                [self finish:nil];
            });
            return;
        }
    });
}
- (void)sample:(NSTimer *)timer {
    LGVideoController *v = self.video;
    if (!self.firstVideoClock && v.player.media.statistics.displayedPictures > 0 && v.player.time.value.longLongValue > 0)
        self.firstVideoClock = v.player.time.value.longLongValue;
    if ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAPauseTransitions"] boolValue] ||
        [[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAPipControls"] boolValue] ||
        [[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAHDRProbe"] boolValue]) return;
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
    LGVideoController *v = self.video;
    if (index == 0) {
        UIBarButtonItem *picture = nil;
        for (UIBarButtonItemGroup *group in v.navigationItem.trailingItemGroups)
            for (UIBarButtonItem *item in group.barButtonItems)
                {
                    if (item.action == NSSelectorFromString(@"toggleFullscreen:")) {
                        [self finish:@"Toolbar still has the redundant fullscreen button"]; return;
                    }
                    if (item.action == NSSelectorFromString(@"togglePictureSize:")) picture = item;
                }
        if (!picture.image || ![picture.accessibilityLabel isEqualToString:@"Fill view"]) {
            [self finish:@"Normal toolbar is missing the default Fit/Fill toggle"]; return;
        }
        [v applyPictureSize];
        AVSampleBufferDisplayLayer *initialLayer = [v sampleBufferLayer:v.movie.layer];
        if (![initialLayer.videoGravity isEqualToString:AVLayerVideoGravityResizeAspect] || v.player.scaleFactor != 0.f) {
            [self finish:@"Picture did not default to Fit"]; return;
        }
        [v togglePictureSize:picture];
        if (v.presentedViewController || ![picture.accessibilityLabel isEqualToString:@"Fit view"]) {
            [self finish:@"Fit/Fill toggle opened a menu or failed to update"]; return;
        }
        [v.view layoutIfNeeded];
        AVSampleBufferDisplayLayer *layer = [v sampleBufferLayer:v.movie.layer];
        if (!layer || ![layer.videoGravity isEqualToString:AVLayerVideoGravityResizeAspectFill]) {
            [self finish:@"Fill did not reach the native video output"]; return;
        }
        CGSize filledSize = v.movie.bounds.size;
        [v togglePictureSize:picture];
        [v.view layoutIfNeeded];
        if (![picture.accessibilityLabel isEqualToString:@"Fill view"] ||
            ![layer.videoGravity isEqualToString:AVLayerVideoGravityResizeAspect] ||
            (v.movie.bounds.size.height >= filledSize.height && v.movie.bounds.size.width >= filledSize.width)) {
            [self finish:@"Fit/Fill did not update the drawable geometry"]; return;
        }
        [v setting:@"aspect" value:@"original"];
        if (v.player.scaleFactor != 0.f || ![layer.videoGravity isEqualToString:AVLayerVideoGravityResizeAspect]) {
            [self finish:@"Legacy Original preference did not fall back to Fit"]; return;
        }
        [v setting:@"aspect" value:@"fit"];
        CGRect track = [v.seek trackRectForBounds:v.seek.bounds];
        CGRect strip = v.cacheStrip.frame;
        CGRect firstThumb = [v.seek thumbRectForBounds:v.seek.bounds trackRect:track value:v.seek.minimumValue];
        CGRect lastThumb = [v.seek thumbRectForBounds:v.seek.bounds trackRect:track value:v.seek.maximumValue];
        if (fabs(CGRectGetMidX(firstThumb) - CGRectGetMinX(strip)) > .5 ||
            fabs(CGRectGetMidX(lastThumb) - CGRectGetMaxX(strip)) > .5) {
            [self finish:@"Cached ranges do not align with the seek thumb endpoints"]; return;
        }
        if (CGRectGetMinY(strip) < 0 || CGRectGetMaxY(strip) > CGRectGetHeight(v.seek.bounds) ||
            CGRectGetHeight(strip) <= 0) {
            [self finish:@"Cached ranges are clipped outside the slider"]; return;
        }
        if ((v.navigationItem.titleView != v.videoHeader && v.videoHeader.superview != v.view && v.videoHeader.superview != v.controls && v.videoHeader.superview != v.portraitHeader) || !v.videoHeader.window ||
            v.videoHeader.bounds.size.width < 44 || v.videoTitle.textAlignment != (v.portraitTabletop ? NSTextAlignmentLeft : NSTextAlignmentCenter)) {
            [self finish:@"Video identity is not centered in the native title area"]; return;
        }
        [v showCachedRanges:@"{\"ranges\":[[0,0.3],[0.5,0.65],[0.8,1]]}"];
        CGRect title = [v.videoHeader convertRect:v.videoHeader.bounds toView:self.window];
        if (v.tabletop) {
            CGRect deck = [v.controlsScroll convertRect:v.controlsScroll.bounds toView:self.window];
            CGRect movie = [v.movie convertRect:v.movie.bounds toView:self.window];
            if (!v.prefersStatusBarHidden || !self.window.windowScene.statusBarManager.statusBarHidden || !v.navigationController.navigationBarHidden) {
                [self finish:@"Laptop upper screen still shows system chrome"]; return;
            }
            NSMutableSet *labels = [NSMutableSet set];
            NSArray *rows = v.portraitTabletop ? @[v.portraitUtilities] : v.tabletopUtilities.arrangedSubviews;
            for (UIStackView *row in rows) {
                for (UIButton *button in row.arrangedSubviews) {
                    [labels addObject:button.accessibilityLabel];
                    CGRect frame = [button convertRect:button.bounds toView:self.window];
                    if (!CGRectContainsRect(CGRectInset(deck, -1, -1), frame) || frame.size.height < 44 || frame.size.width < 44) {
                        [self finish:[NSString stringWithFormat:@"Laptop setting clipped: %@ %@ inside %@", button.accessibilityLabel, NSStringFromCGRect(frame), NSStringFromCGRect(deck)]]; return;
                    }
                }
            }
            if (![labels containsObject:@"Speed"] || ![labels containsObject:@"Fill view"] || labels.count != (v.portraitTabletop ? 6 : 8)) {
                [self finish:@"Laptop quick settings missing"]; return;
            }
            if (!CGRectContainsRect(deck, title) || CGRectGetMinY(title) < CGRectGetMaxY(movie)) {
                [self finish:@"Laptop title is outside the lower control deck"]; return;
            }
            if (v.portraitTabletop) {
                CGRect close = [v.portraitClose convertRect:v.portraitClose.bounds toView:self.window];
                if (!CGRectContainsRect(deck, close) || ![v.portraitClose.configuration.image isEqual:[UIImage systemImageNamed:@"xmark"]]) {
                    [self finish:@"Portrait deck lacks its X close action"]; return;
                }
                __block BOOL closed = NO;
                v.closed = ^{ closed = YES; };
                [v.portraitClose sendActionsForControlEvents:UIControlEventTouchUpInside];
                v.closed = nil;
                if (!closed) { [self finish:@"X did not dispatch the existing close callback"]; return; }
                if (deck.size.height < v.tabletopArea.size.height - 20) {
                    [self finish:@"Portrait deck does not use the lower panel height"]; return;
                }
            }
        }
        CGRect filename = [v.videoTitle convertRect:v.videoTitle.bounds toView:self.window];
        UIView *source = v.sourceLabel.superview;
        CGRect details = [source convertRect:source.bounds toView:self.window];
        if (!v.portraitTabletop && fabs(CGRectGetMidX(filename) - CGRectGetMidX(details)) > .5) {
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
    NSArray *selectors = @[@"playbackTools:", @"speedOptions:", @"subtitleOptions:", @"queueVideos:", @"audioTracks:", @"subtitleTracks:", @"chapters:", @"goToTime:", @"hdrDisplayOptions:", @"subtitleSizeOptions:"];
    if (index >= selectors.count) {
#ifdef LG_VIDEO_FOLD_QA
        [(LGVideoPoseQAController *)v applyTestFold:NO];
        [v setControlsShown:YES];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, .4 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            if (v.tabletop || v.prefersStatusBarHidden || self.window.windowScene.statusBarManager.statusBarHidden)
                [self finish:@"Leaving laptop mode did not restore normal visible chrome"];
            else [self finish:nil];
        });
#else
        [self finish:nil];
#endif
        return;
    }
    @try {
        id sender = nil;
        for (UIBarButtonItem *item in self.video.mediaItems)
            if ([item.accessibilityLabel isEqualToString:@"More playback options"]) sender = item;
        SEL selector = NSSelectorFromString(selectors[index]);
        for (UIBarButtonItem *item in self.video.mediaItems)
            if (item.action == selector) sender = item;
        if (self.video.tabletop) {
            for (UIStackView *row in (self.video.portraitTabletop ? @[self.video.portraitUtilities] : self.video.tabletopUtilities.arrangedSubviews))
                for (UIButton *button in row.arrangedSubviews)
                    if ([[button actionsForTarget:self.video forControlEvent:UIControlEventTouchUpInside] containsObject:selectors[index]]) sender = button;
        }
        void (*invoke)(id,SEL,id) = (void (*)(id,SEL,id))[self.video methodForSelector:selector];
        invoke(self.video, selector, sender);
        UIViewController *presentation = self.video.presentedViewController;
        UIAlertController *menu = [presentation isKindOfClass:LGVideoDeckSettings.class]
            ? ((LGVideoDeckSettings *)presentation).dialog : (UIAlertController *)presentation;
        if (!menu) { [self finish:@"Playback menu did not present"]; return; }
        if (index == 0) for (UIAlertAction *action in menu.actions) {
            if ([action.title hasPrefix:@"Picture size"]) { [self finish:@"Playback duplicates the Picture icon"]; return; }
        }
        NSUInteger cancel = 0;
        for (UIAlertAction *action in menu.actions) if (action.style == UIAlertActionStyleCancel) cancel++;
        if (!menu.textFields.count && cancel != 0) { [self finish:@"Playback menus must dismiss without Cancel actions"]; return; }
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 1 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            if (self.video.portraitTabletop) {
                UIViewController *presented = self.video.presentedViewController;
                CGRect frame = [presented.view convertRect:presented.view.bounds toView:self.video.view];
                if (![presented isKindOfClass:LGVideoDeckSettings.class] ||
                    !CGRectContainsRect(CGRectInset(self.video.tabletopArea, -1, -1), frame)) {
                    [self finish:[NSString stringWithFormat:@"Settings escaped the lower panel: %@", NSStringFromCGRect(frame)]]; return;
                }
                CGRect lower = self.video.tabletopArea;
                if (frame.size.width > 360.5 || CGRectGetMinX(frame) - CGRectGetMinX(lower) < 23 ||
                    CGRectGetMaxX(lower) - CGRectGetMaxX(frame) < 23) {
                    [self finish:@"Lower menu has no reachable side dismissal gutters"]; return;
                }
                UIView *close = nil;
                if (!menu.textFields.count) {
                    // Find the public, accessible close control in the table header.
                    close = nil;
                    UIStackView *header = (UIStackView *)((LGVideoDeckSettings *)presented).tableView.tableHeaderView;
                    for (UIView *row in header.arrangedSubviews) if ([row isKindOfClass:UIStackView.class])
                        for (UIView *child in ((UIStackView *)row).arrangedSubviews)
                            if ([child.accessibilityIdentifier isEqualToString:@"video.deck.settings.close"]) close = child;
                    if (!close || close.bounds.size.width < 44 || close.bounds.size.height < 44) {
                        [self finish:@"Lower selection menu lacks an accessible X close target"]; return;
                    }
                }
                UIGraphicsImageRenderer *renderer = [[UIGraphicsImageRenderer alloc] initWithBounds:self.window.bounds];
                UIImage *image = [renderer imageWithActions:^(UIGraphicsImageRendererContext *context) {
                    [self.window drawViewHierarchyInRect:self.window.bounds afterScreenUpdates:YES];
                }];
                [UIImagePNGRepresentation(image) writeToFile:[self outputPath:[NSString stringWithFormat:@"menu-%lu.png", (unsigned long)index]] atomically:YES];
                if (!self.video.surfaceVisible) { [self finish:@"Lower menu hid the playing video owner"]; return; }
                LGVideoDeckPresentation *deckPresentation = (LGVideoDeckPresentation *)presented.presentationController;
                CGRect backdrop = [deckPresentation.backdrop convertRect:deckPresentation.backdrop.bounds toView:self.video.view];
                if (!CGRectContainsRect(CGRectInset(self.video.tabletopArea, -1, -1), backdrop)) {
                    [self finish:@"Settings backdrop covers the upper movie"]; return;
                }
                if (index == 7) {
                    LGVideoDeckSettings *settings = (LGVideoDeckSettings *)presented;
                    settings.dialog.textFields.firstObject.text = @"0:12";
                    self.video.command = ^(NSString *name, NSString *value) { self.deckCommand = [NSString stringWithFormat:@"%@:%@", name, value]; };
                    [settings tableView:settings.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:1 inSection:0]];
                } else if (index == 0) [deckPresentation dismiss:nil];
                else if (index == 2) [(UIButton *)close sendActionsForControlEvents:UIControlEventTouchUpInside];
                else if (index == 1) {
                    LGVideoDeckSettings *settings = (LGVideoDeckSettings *)presented;
                    // Select a real speed row through the production table delegate.
                    [settings tableView:settings.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:0]];
                } else [presented dismissViewControllerAnimated:YES completion:nil];
                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 1 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
                    if (index == 1 && fabs([[self.video playbackOptions][@"rate"] doubleValue] - .5) > .01) {
                        [self finish:[NSString stringWithFormat:@"Deck Speed selection failed: %@", [self.video playbackOptions]]]; return;
                    }
                    if (index == 7 && ![self.deckCommand isEqualToString:@"seek:0:12"]) {
                        [self finish:@"Lower-panel text entry lost its existing seek command"]; return;
                    }
                    [self menus:index+1];
                });
                return;
            }
            if (menu.textFields.count) {
                [self.video.presentedViewController dismissViewControllerAnimated:NO completion:^{ [self menus:index+1]; }];
                return;
            }
            // Regular iPad popovers own outside-tap dismissal in UIKit; their
            // container need not expose the compact alert's backdrop recognizer.
            if (menu.presentationController.presentationStyle == UIModalPresentationPopover) {
                if (!menu.popoverPresentationController.barButtonItem && !menu.popoverPresentationController.sourceView && !menu.popoverPresentationController.sourceItem) {
                    [self finish:@"iPad menu lost its native popover anchor"]; return;
                }
                [menu dismissViewControllerAnimated:YES completion:^{ [self menus:index+1]; }];
                return;
            }
            if (!self.video.menuOutsideTap.view) { [self finish:@"Menu backdrop dismissal was not installed"]; return; }
            UIView *backdrop = self.video.menuOutsideTap.view;
            LGVideoMenuTouch *touch = [[LGVideoMenuTouch alloc] init];
            touch.coordinateView = menu.view;
            touch.point = CGPointMake(CGRectGetMidX(menu.view.bounds), CGRectGetMidY(menu.view.bounds));
            if ([self.video gestureRecognizer:self.video.menuOutsideTap shouldReceiveTouch:touch]) {
                [self finish:@"Menu taps are intercepted by backdrop dismissal"]; return;
            }
            touch.coordinateView = backdrop;
            touch.point = CGPointMake(CGRectGetMinX(backdrop.bounds) + 1, CGRectGetMinY(backdrop.bounds) + 1);
            if (![self.video gestureRecognizer:self.video.menuOutsideTap shouldReceiveTouch:touch]) {
                [self finish:@"Outside taps cannot reach menu dismissal"]; return;
            }
            [self.video dismissPlaybackMenu:self.video.menuOutsideTap];
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 1 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
                if (self.video.presentedViewController) { [self finish:@"Menu backdrop did not dismiss"]; return; }
                [self menus:index+1];
            });
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
