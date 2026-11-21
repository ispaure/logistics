// Two real AAC languages through the production VLCKit controller. No physical
// speaker/receiver claim: playedAudioBuffers verifies native output delivery.
@interface LGVideoNonseekablePlayer : VLCMediaPlayer
@end
@implementation LGVideoNonseekablePlayer
- (BOOL)isSeekable { return NO; }
@end
@interface LGVideoAudioSwitchChecks : UIResponder <UIApplicationDelegate, UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) LGVideoController *video;
@property(nonatomic, strong) NSTimer *timer;
@property(nonatomic, strong) NSMutableArray *samples;
@property(nonatomic, strong) NSMutableArray *measurements;
@property(nonatomic) NSInteger stage;
@property(nonatomic) NSTimeInterval began, switched;
@property(nonatomic) int64_t held;
@property(nonatomic) uint64_t audio;
@end
@implementation LGVideoAudioSwitchChecks
- (void)finish:(NSString *)error {
    [self.timer invalidate]; self.timer = nil;
    [self.video retireWithCompletion:nil];
    NSDictionary *result = @{@"success": @(!error), @"error": error ?: @"",
        @"samples": self.samples, @"selections": self.measurements};
    NSString *path = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents/result.json"];
    [NSFileManager.defaultManager createDirectoryAtPath:path.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil];
    [[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil] writeToFile:path atomically:YES];
}
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    self.samples = [NSMutableArray array];
    self.measurements = [NSMutableArray array];
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    self.video = [LGVideoController new];
    NSString *remote = NSBundle.mainBundle.infoDictionary[@"QAURL"];
    self.video.videoURL = remote.length ? remote :
        [[NSBundle.mainBundle URLForResource:@"fixture" withExtension:@"mp4"] absoluteString];
    self.video.startMilliseconds = 0;
    self.video.subtitleJSON = @"[]"; self.video.queueJSON = @"[]"; self.video.optionsJSON = @"{}";
    self.video.allowed = ^BOOL(BOOL external) { return YES; };
    self.video.requestPlay = ^BOOL { return YES; };
    self.window.rootViewController = [[LGVideoNavigationController alloc] initWithRootViewController:self.video];
    [self.window makeKeyAndVisible];
    self.began = NSProcessInfo.processInfo.systemUptime;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC / 2), dispatch_get_main_queue(), ^{
        [self.video startByUser];
        self.timer = [NSTimer scheduledTimerWithTimeInterval:.05 target:self selector:@selector(sample:) userInfo:nil repeats:YES];
    });
}
- (void)sample:(NSTimer *)timer {
    LGVideoController *v = self.video;
    NSTimeInterval now = NSProcessInfo.processInfo.systemUptime;
    VLCMediaStats stats = v.player.media.statistics;
    [self.samples addObject:@{@"stage": @(self.stage), @"time": @(now-self.began),
        @"clock": @([v positionMilliseconds]), @"nativeClock": @([v nativeTimeMilliseconds]),
        @"audio": @(stats.playedAudioBuffers), @"frames": @(stats.displayedPictures),
        @"renderedClock": @(v.lastRenderedClock), @"buffering": @(v.buffering),
        @"decodedAudio": @(stats.decodedAudio), @"pending": @(v.audioSwitchTrack.length > 0),
        @"buffered": @(v.audioSwitchBuffered), @"sawBuffering": @(v.audioSwitchSawBuffering),
        @"spinner": @(v.bufferSpinner.isAnimating), @"playing": @(v.player.isPlaying)}];
    if (now-self.began > 40) { [self finish:@"Audio-switch probe timed out"]; return; }
    NSArray *tracks = v.player.audioTracks;
    if (tracks.count < 2) return;
    if (self.stage == 0 && stats.playedAudioBuffers > 10 && v.player.time.value.longLongValue > 2000) {
        VLCMediaPlayer *live = v.player;
        v.player = [LGVideoNonseekablePlayer new];
        BOOL accepted = [v switchAudioTrack:tracks[1]];
        v.player = live;
        if (accepted || v.audioSwitchTrack.length || ((VLCMediaPlayerTrack *)tracks[1]).isSelected) {
            [self finish:@"Nonseekable input switched without coordinated preroll"]; return;
        }
        [v showStatus:@""];
        self.held = [v positionMilliseconds]; self.audio = stats.playedAudioBuffers; self.switched = now;
        [self.measurements addObject:@{@"stage": @1, @"action": @"playing switch", @"time": @(now-self.began),
            @"position": @(self.held), @"audio": @(self.audio), @"frames": @(stats.displayedPictures)}];
        [v switchAudioTrack:tracks[1]];
        if (!v.audioSwitchTrack.length || v.bufferOverlay.hidden || v.bufferLabel.hidden) {
            [self finish:@"Playing switch did not immediately present its wait state"]; return;
        }
        self.stage = 1;
    } else if (self.stage == 1 && !v.audioSwitchTrack.length) {
        if (!((VLCMediaPlayerTrack *)tracks[1]).isSelected || stats.playedAudioBuffers <= self.audio ||
            !v.playRequested || llabs([v positionMilliseconds]-self.held) > (now-self.switched)*1000+800) {
            [self finish:@"Switch completed without selected audio output or jumped timeline"]; return;
        }
        [self.measurements addObject:@{@"stage": @1, @"action": @"switch ready",
            @"time": @(now-self.began), @"position": @([v positionMilliseconds])}];
        [v pause]; self.switched = now; self.stage = 2;
    } else if (self.stage == 2 && !v.player.isPlaying && now-self.switched > .5) {
        self.held = [v positionMilliseconds];
        [v switchAudioTrack:tracks[0]];
        self.switched = now; self.stage = 3;
    } else if (self.stage == 3 && now-self.switched > 1) {
        if (v.playRequested || v.player.isPlaying || llabs([v positionMilliseconds]-self.held) > 100) {
            [self finish:@"Paused language selection advanced or restarted playback"]; return;
        }
        [v startByUser]; self.stage = 4;
    } else if (self.stage == 4 && !v.audioSwitchTrack.length && v.player.isPlaying) {
        [v switchAudioTrack:tracks[1]];
        [v mediaPlayerBufferingChanged:1]; // A completion without a reset is insufficient.
        [v switchAudioTrack:tracks[0]]; // Retires the queued callback above.
        if (!v.audioSwitchTrack.length || v.audioSwitchBuffered) {
            [self finish:@"Rapid replacement accepted an earlier completion"]; return;
        }
        self.stage = 5;
    } else if (self.stage == 5 && !v.audioSwitchTrack.length) {
        [v switchAudioTrack:tracks[1]];
        v.audioSwitchDeadline = now-1;
        [v updateAudioSwitch];
        if (v.playRequested || v.audioSwitchTrack.length || ![v.message.text containsString:@"Audio did not become ready"]) {
            [self finish:@"Readiness deadline did not pause and report failure"]; return;
        }
        [v startByUser]; self.stage = 6;
    } else if (self.stage == 6 && v.player.isPlaying) {
        [v switchAudioTrack:tracks[0]];
        [v retireWithCompletion:nil];
        [v mediaPlayerBufferingChanged:1];
        if (v.audioSwitchTrack.length || !v.bufferOverlay.hidden) {
            [self finish:@"Retirement retained the pending audio wait"]; return;
        }
        [self finish:nil];
    }
}
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(LGVideoAudioSwitchChecks.class)); }
}
