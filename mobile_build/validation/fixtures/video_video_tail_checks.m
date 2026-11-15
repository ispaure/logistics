// A real MKV with ten seconds of video and two three-second audio tracks.
// Language selection after audio EOF must not trap valid video playback.
@interface LGVideoVideoTailChecks : UIResponder <UIApplicationDelegate, UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) LGVideoController *video;
@property(nonatomic, strong) NSTimer *timer;
@property(nonatomic, strong) NSMutableArray *samples;
@property(nonatomic) NSInteger stage;
@property(nonatomic) NSTimeInterval began, changed;
@property(nonatomic) int64_t held;
@end
@implementation LGVideoVideoTailChecks
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
    self.video.startMilliseconds = 6000; self.video.knownDuration = 10000;
    self.video.subtitleJSON = @"[]"; self.video.queueJSON = @"[]"; self.video.optionsJSON = @"{}";
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
        @"clock": @([v positionMilliseconds]), @"nativeClock": v.player.time.value ?: @(-1), @"coreClock": @([v nativeTimeMilliseconds]),
        @"target": @(v.startMilliseconds), @"state": @(v.player.state),
        @"frames": @(stats.displayedPictures), @"audio": @(stats.playedAudioBuffers), @"decodedAudio": @(stats.decodedAudio),
        @"switchClock": @(v.audioSwitchClock), @"switchFrames": @(v.audioSwitchFrames), @"buffered": @(v.audioSwitchBuffered),
        @"buffering": @(v.buffering), @"seekable": @(v.player.isSeekable)}];
    if (now-self.began > 35) { [self finish:@"Audio-tail playback timed out"]; return; }
    if (self.stage == 0 && v.player.isPlaying && v.startMilliseconds < 0 &&
        stats.displayedPictures > 0 && [v positionMilliseconds] >= 6500) {
        if (v.buffering || !v.seek.enabled) { [self finish:@"Video-only resume remained loading"]; return; }
        if (v.player.audioTracks.count < 2) { [self finish:@"Missing second short audio track"]; return; }
        [v switchAudioTrack:v.player.audioTracks.lastObject];
        self.changed = now; self.stage = 1;
    } else if (self.stage == 1 && ((!v.audioSwitchTrack.length && now-self.changed > 1) || now-self.changed > 3)) {
        if (v.audioSwitchTrack.length || v.buffering || !v.player.isPlaying) {
            [self finish:@"Changing language after audio EOF blocked valid video playback"]; return;
        }
        self.held = [v positionMilliseconds]; [v pause]; self.changed = now; self.stage = 2;
    } else if (self.stage == 2 && now-self.changed > .5) {
        if (v.player.isPlaying || llabs([v positionMilliseconds]-self.held) > 200) {
            [self finish:@"Video-only Pause changed its position"]; return;
        }
        [v seekToMilliseconds:0]; [v startByUser]; self.changed = now; self.stage = 3;
    } else if (self.stage == 3 && v.player.isPlaying && v.startMilliseconds < 0 &&
        stats.playedAudioBuffers > 0 && [v positionMilliseconds] > 500 && [v positionMilliseconds] < 2500) {
        [self finish:nil];
    }
}
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(LGVideoVideoTailChecks.class)); }
}
