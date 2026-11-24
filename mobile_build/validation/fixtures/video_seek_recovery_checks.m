// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

// Recover a real VLC input error and a stopped input using the production
// timeline/actions, then require decoded pictures at the replacement target.
@interface LGResumeVideoFixture : LGVideoController
@property(nonatomic) BOOL holdVideoCounter;
@property(nonatomic) uint64_t heldFrames;
@property(nonatomic) NSUInteger seekCalls;
@property(nonatomic) int64_t seekTarget;
@end
@implementation LGResumeVideoFixture
- (VLCMediaStats)playbackStats {
    VLCMediaStats stats = [super playbackStats];
    if (self.holdVideoCounter) return (VLCMediaStats){
        .displayedPictures = self.heldFrames, .playedAudioBuffers = stats.playedAudioBuffers,
        .decodedAudio = stats.decodedAudio, .decodedVideo = stats.decodedVideo,
    };
    return stats;
}
- (void)seekToMilliseconds:(int64_t)target {
    self.seekCalls++;
    self.seekTarget = target;
    [super seekToMilliseconds:target];
}
@end

@interface LGVideoSeekRecoveryChecks : UIResponder <UIApplicationDelegate, UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) LGResumeVideoFixture *video;
@property(nonatomic, strong) NSTimer *timer;
@property(nonatomic, strong) NSMutableArray *samples;
@property(nonatomic) NSInteger stage;
@property(nonatomic) NSTimeInterval began, changed;
@property(nonatomic) BOOL permitted;
@property(nonatomic) NSUInteger priorSeeks;
@property(nonatomic) int64_t pausedPosition;
@end
@implementation LGVideoSeekRecoveryChecks
- (void)finish:(NSString *)error {
    [self.timer invalidate]; self.timer = nil;
    [self.video retireWithCompletion:nil];
    NSString *path = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents/result.json"];
    [NSFileManager.defaultManager createDirectoryAtPath:path.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil];
    NSDictionary *result = @{@"success": @(!error), @"error": error ?: @"", @"samples": self.samples};
    [[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil] writeToFile:path atomically:YES];
}
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    self.samples = [NSMutableArray array]; self.permitted = YES;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    self.video = [LGResumeVideoFixture new];
    self.video.videoURL = [[NSBundle.mainBundle URLForResource:@"fixture" withExtension:@"mp4"] absoluteString];
    self.video.startMilliseconds = 0; self.video.knownDuration = 30000;
    self.video.subtitleJSON = @"[]"; self.video.queueJSON = @"[]"; self.video.optionsJSON = @"{\"media_bounds\":null}";
    __weak LGVideoSeekRecoveryChecks *owner = self;
    self.video.allowed = ^BOOL(BOOL external) { return owner.permitted; };
    self.video.requestPlay = ^BOOL { return owner.permitted; };
    self.window.rootViewController = [[LGVideoNavigationController alloc] initWithRootViewController:self.video];
    [self.window makeKeyAndVisible];
    self.began = NSProcessInfo.processInfo.systemUptime;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC/2), dispatch_get_main_queue(), ^{
        // Open an invalid input while retaining a legitimate known-duration
        // source for the explicit retry, just as a failed persisted seek does.
        self.video.player.media = [VLCMedia mediaWithURL:[NSURL fileURLWithPath:@"/nonexistent-logistics-seek-probe.mp4"]];
        self.video.hasPlayed = YES;
        self.video.startMilliseconds = self.video.lastPosition = 24000;
        [self.video.player play];
        self.timer = [NSTimer scheduledTimerWithTimeInterval:.05 target:self selector:@selector(sample:) userInfo:nil repeats:YES];
    });
}
- (void)sample:(NSTimer *)timer {
    LGResumeVideoFixture *v = self.video;
    NSTimeInterval now = NSProcessInfo.processInfo.systemUptime;
    [self.samples addObject:@{@"stage": @(self.stage), @"time": @(now-self.began),
        @"clock": @([v positionMilliseconds]), @"target": @(v.startMilliseconds),
        @"seekable": @(v.player.isSeekable), @"timelineEnabled": @(v.seek.enabled),
        @"nativeState": @(v.player.state), @"requested": @(v.playRequested),
        @"frames": @([v playbackStats].displayedPictures), @"seeks": @(v.seekCalls)}];
    if (now-self.began > 35) { [self finish:@"Seek recovery timed out"]; return; }
    if (self.stage == 0 && now-self.began > 1 && (v.player.state == VLCMediaPlayerStateError || v.player.state == VLCMediaPlayerStateStopped)) {
        [v pause]; v.startMilliseconds = v.lastPosition = 24000;
        [v updateTimeline];
        if (!v.seek.enabled) { [self finish:@"Failed input disabled its known-duration timeline"]; return; }
        v.controlsLocked = YES;
        [v seekToMilliseconds:1000];
        if (v.startMilliseconds != 24000) { [self finish:@"Locked controls changed the recovery target"]; return; }
        v.controlsLocked = NO; self.permitted = NO;
        [v seekToMilliseconds:1000];
        if (v.startMilliseconds != 24000) { [self finish:@"Revoked access changed the recovery target"]; return; }
        self.permitted = YES;
        [v seekToMilliseconds:1000];
        if (v.startMilliseconds != 1000 || v.playRequested || v.player.isPlaying || !v.inputNeedsRestart) {
            [self finish:@"Failed input ignored the new target or autoplayed while paused"]; return;
        }
        [v startByUser]; self.changed = now; self.stage = 1;
    } else if (self.stage == 1 && v.player.isPlaying && v.startMilliseconds < 0 &&
               [v playbackStats].displayedPictures > 0 && now-self.changed > .5) {
        if ([v positionMilliseconds] > 5000) { [self finish:@"Retry reopened the old failed checkpoint"]; return; }
        [v pause]; [v.player stop]; self.stage = 2;
    } else if (self.stage == 2 && v.player.state == VLCMediaPlayerStateStopped) {
        v.startMilliseconds = v.lastPosition = 24000;
        v.playRequested = YES; v.manualResumeRequired = NO;
        [v seekToMilliseconds:4000];
        if (!v.playRequested || v.startMilliseconds != 4000) {
            [self finish:@"Stopped-input seek lost the current Play intent or target"]; return;
        }
        self.changed = now; self.stage = 3;
    } else if (self.stage == 3 && v.player.isPlaying && v.startMilliseconds < 0 &&
               [v playbackStats].displayedPictures > 0 && now-self.changed > .5) {
        int64_t position = [v positionMilliseconds];
        if (position < 3500 || position > 8000) { [self finish:@"Stopped input did not decode at the replacement position"]; return; }
        [v pause]; self.stage = 4;
    } else if (self.stage == 4 && v.player.state == VLCMediaPlayerStatePaused) {
        self.priorSeeks = v.seekCalls;
        [v startByUser]; self.changed = now; self.stage = 5;
    } else if (self.stage == 5 && now-self.changed > 1.8 && v.player.isPlaying) {
        if (v.seekCalls != self.priorSeeks) { [self finish:@"Healthy resume triggered an extra seek"]; return; }
        [v pause]; self.stage = 6;
    } else if (self.stage == 6 && v.player.state == VLCMediaPlayerStatePaused) {
        self.pausedPosition = [v positionMilliseconds];
        v.heldFrames = [v playbackStats].displayedPictures;
        v.holdVideoCounter = YES;
        [v startByUser]; self.changed = now; self.stage = 7;
    } else if (self.stage == 7 && v.seekCalls > self.priorSeeks) {
        if (v.seekTarget != self.pausedPosition || v.seekCalls != self.priorSeeks + 1 ||
            now-self.changed < 1.4 || now-self.changed > 5) {
            [self finish:@"Frozen video did not recover once at the paused position"]; return;
        }
        v.holdVideoCounter = NO; self.changed = now; self.stage = 8;
    } else if (self.stage == 8 && now-self.changed > 1.8 && v.player.isPlaying &&
               [v playbackStats].displayedPictures > v.heldFrames &&
               [v nativeTimeMilliseconds] >= self.pausedPosition + 500) {
        if (v.seekCalls != self.priorSeeks + 1) { [self finish:@"Recovery sought more than once"]; return; }
        [self finish:nil];
    }
}
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(LGVideoSeekRecoveryChecks.class)); }
}
