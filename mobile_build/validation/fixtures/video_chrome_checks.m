// Compiled with the production video controller in a disposable UIKit app.
@interface LGVideoChromeChecks : UIResponder <UIApplicationDelegate, UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) LGVideoController *video;
@property(nonatomic, strong) NSMutableArray *samples;
@property(nonatomic, strong) NSTimer *sampler;
@property(nonatomic) NSTimeInterval started;
@property(nonatomic) BOOL completed;
@end
@implementation LGVideoChromeChecks
- (void)finish:(NSString *)error {
    if (self.completed) return;
    self.completed = YES;
    [self.sampler invalidate];
    NSDictionary *report = @{@"success": @(!error), @"error": error ?: @"", @"samples": self.samples ?: @[],
        @"scope": @"Real UIKit controller and VLC; synthetic local movie; simulator only"};
    NSMutableDictionary *details = [report mutableCopy];
    details[@"bounds"] = NSStringFromCGRect(self.window.bounds);
    details[@"orientation"] = @(self.window.windowScene.interfaceOrientation);
    details[@"idiom"] = @(self.video.traitCollection.userInterfaceIdiom);
    report = details;
    NSString *path = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents/result.json"];
    [[NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:nil] writeToFile:path atomically:YES];
}
- (BOOL)application:(UIApplication *)app didFinishLaunchingWithOptions:(NSDictionary *)options { return YES; }
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    self.samples = [NSMutableArray array];
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    self.video = [LGVideoController new];
    self.video.videoURL = [[NSBundle.mainBundle URLForResource:@"fixture" withExtension:@"mp4"] absoluteString];
    self.video.startMilliseconds = 0;
    self.video.subtitleJSON = @"[]";
    self.video.queueJSON = @"[]";
    self.video.optionsJSON = @"{\"video_title\":\"A long video filename for title alignment.mp4\",\"source_label\":\"Cloud file\",\"source_remote\":true}";
    self.video.allowed = ^BOOL(BOOL external) { return YES; };
    self.video.requestPlay = ^BOOL { return YES; };
    self.window.rootViewController = [[LGVideoNavigationController alloc] initWithRootViewController:self.video];
    [self.window makeKeyAndVisible];
    if ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAOrientation"] isEqualToString:@"landscape"]) {
        UIWindowSceneGeometryPreferencesIOS *geometry = [[UIWindowSceneGeometryPreferencesIOS alloc]
            initWithInterfaceOrientations:UIInterfaceOrientationMaskLandscapeLeft];
        [(UIWindowScene *)scene requestGeometryUpdateWithPreferences:geometry errorHandler:^(NSError *error) {
            [self finish:error.localizedDescription];
        }];
    }
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, .5 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        self.video.player.audio.muted = YES;
        [self.video startByUser];
        self.started = NSProcessInfo.processInfo.systemUptime;
        self.sampler = [NSTimer scheduledTimerWithTimeInterval:1.0/60 target:self selector:@selector(sample:) userInfo:nil repeats:YES];
    });
}
- (void)sample:(NSTimer *)timer {
    LGVideoController *v = self.video;
    CGFloat opacity = ((CALayer *)v.controlsScroll.layer.presentationLayer).opacity;
    CGFloat barOpacity = ((CALayer *)v.navigationController.navigationBar.layer.presentationLayer).opacity;
    CGRect headerFrame = [v.videoHeader convertRect:v.videoHeader.bounds toView:self.window];
    [self.samples addObject:@{@"time": @(NSProcessInfo.processInfo.systemUptime-self.started),
        @"opacity": @(opacity), @"barOpacity": @(barOpacity), @"visible": @(v.controlsVisible),
        @"systemHidden": @(v.systemChromeHidden), @"headerY": @(CGRectGetMinY(headerFrame)),
        @"statusHidden": @(self.window.windowScene.statusBarManager.statusBarHidden),
        @"playing": @(v.player.isPlaying)}];
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
        if ((v.navigationItem.titleView != v.videoHeader && v.videoHeader.superview != v.view) || !v.videoHeader.window ||
            v.videoHeader.bounds.size.width < 44 || v.videoTitle.textAlignment != NSTextAlignmentCenter) {
            [self finish:@"Video identity is not centered in the native title area"]; return;
        }
        [v showCachedRanges:@"{\"ranges\":[[0,0.3],[0.5,0.65],[0.8,1]]}"];
        CGRect title = [v.videoHeader convertRect:v.videoHeader.bounds toView:self.window];
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
        [UIImagePNGRepresentation(image) writeToFile:[NSHomeDirectory() stringByAppendingPathComponent:@"Documents/controls.png"] atomically:YES];
    }
    NSString *progress = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents/progress.json"];
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
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(LGVideoChromeChecks.class)); }
}
