// A real MKV with three seconds of video and ten seconds of audio. Reopening
// at six seconds must not require a video frame that does not exist.
@interface LGVideoDurationTailChecks : UIResponder <UIApplicationDelegate, UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) LGVideoController *video;
@property(nonatomic, strong) NSTimer *timer;
@property(nonatomic, strong) NSMutableArray *samples;
@property(nonatomic) NSInteger stage;
@property(nonatomic) NSTimeInterval began, changed;
@property(nonatomic) int64_t held;
@end
@implementation LGVideoDurationTailChecks
- (void)finish:(NSString *)error {
    [self.timer invalidate]; self.timer = nil;
    [self.video retireWithCompletion:nil];
    NSString *path = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents/result.json"];
    [NSFileManager.defaultManager createDirectoryAtPath:path.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil];
    NSDictionary *result = @{@"success": @(!error), @"error": error ?: @"", @"samples": self.samples};
    [[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil] writeToFile:path atomically:YES];
}
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    self.samples = [NSMutableArray array];
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    self.video = [LGVideoController new];
    self.video.videoURL = [[NSBundle.mainBundle URLForResource:@"fixture" withExtension:@"mkv"] absoluteString];
    self.video.startMilliseconds = 0; self.video.knownDuration = 3000;
    self.video.subtitleJSON = @"[]"; self.video.queueJSON = @"[]"; self.video.optionsJSON = @"{\"media_bounds\":{\"end_ms\":3023}}";
    self.video.allowed = ^BOOL(BOOL external) { return YES; };
    self.video.requestPlay = ^BOOL { return YES; };
    self.window.rootViewController = [[LGVideoNavigationController alloc] initWithRootViewController:self.video];
    [self.window makeKeyAndVisible];
    self.began = NSProcessInfo.processInfo.systemUptime;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC/2), dispatch_get_main_queue(), ^{
        [self.video startByUser];
        self.timer = [NSTimer scheduledTimerWithTimeInterval:.05 target:self selector:@selector(sample:) userInfo:nil repeats:YES];
    });
}
- (void)sample:(NSTimer *)timer {
    LGVideoController *v = self.video;
    NSTimeInterval now = NSProcessInfo.processInfo.systemUptime;
    VLCMediaStats stats = [v playbackStats];
    [self.samples addObject:@{@"stage": @(self.stage), @"time": @(now-self.began),
        @"clock": @([v positionMilliseconds]), @"nativeClock": v.player.time.value ?: @(-1),
        @"target": @(v.startMilliseconds), @"state": @(v.player.state), @"duration": @([v durationMilliseconds]),
        @"frames": @(stats.displayedPictures), @"audio": @(stats.playedAudioBuffers),
        @"buffering": @(v.buffering), @"seekable": @(v.player.isSeekable)}];
    if (now-self.began > 35) { [self finish:@"Audio-tail playback timed out"]; return; }
    if (now-self.began > 9) { [self finish:@"Subtitle cue extended playback past both A/V streams"]; return; }
    if (v.ended || (now-self.began > 2 && v.player.state == VLCMediaPlayerStateStopped)) {
        if ([v durationMilliseconds] > 3500) { [self finish:@"Subtitle cue inflated the playable timeline"]; return; }
        [self finish:nil];
    }
}
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(LGVideoDurationTailChecks.class)); }
}
