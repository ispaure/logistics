// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

typedef NS_ENUM(NSInteger, LGBackgroundStage) {
    LGWaitForVideo, LGForegroundPause, LGEnterPausedBackground, LGPausedBackground,
    LGReturnPaused, LGExplicitResume, LGEnterBackground, LGWaitInBackground, LGReturnToVideo,
    LGLockOrdinary, LGPauseWhileLocked, LGUnlockOrdinary, LGResumeOrdinary,
    LGRevokeOrdinary, LGReauthorizeOrdinary, LGStartProtected, LGLockProtected, LGUnlockProtected
};

@interface LGBackgroundAudioVideo : LGVideoController
@property(nonatomic) BOOL dataAvailable;
@end

@implementation LGBackgroundAudioVideo
- (BOOL)protectedDataAvailable { return self.dataAvailable; }
@end

@interface LGVideoBackgroundAudioChecks : UIResponder <UIApplicationDelegate, UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) LGBackgroundAudioVideo *video;
@property(nonatomic, strong) NSTimer *timer;
@property(nonatomic, strong) NSMutableArray *samples;
@property(nonatomic) LGBackgroundStage stage;
@property(nonatomic) NSTimeInterval began, changed;
@property(nonatomic) uint64_t heldAudio, heldFrames;
@property(nonatomic) int64_t heldClock;
@property(nonatomic) NSInteger cycle;
@property(nonatomic) uint64_t lateAudio, lateFrames;
@property(nonatomic) int64_t lateClock;
@property(nonatomic) BOOL earlyOutput;
@property(nonatomic) BOOL grant;
@end

@implementation LGVideoBackgroundAudioChecks
- (NSString *)documentPath:(NSString *)name {
    return [NSHomeDirectory() stringByAppendingPathComponent:[@"Documents" stringByAppendingPathComponent:name]];
}
- (void)save:(NSDictionary *)report name:(NSString *)name {
    [[NSJSONSerialization dataWithJSONObject:report options:0 error:nil]
        writeToFile:[self documentPath:name] atomically:YES];
}
- (void)finish:(NSString *)error {
    [self.timer invalidate]; self.timer = nil;
    [self.video retireWithCompletion:nil];
    [self save:@{@"success": @(!error), @"error": error ?: @"", @"samples": self.samples}
           name:@"result.json"];
}
- (void)prepareVideoRestricted:(BOOL)restricted {
    LGBackgroundAudioVideo *video = [LGBackgroundAudioVideo new];
    video.videoURL = [[NSBundle.mainBundle URLForResource:@"fixture" withExtension:@"mp4"] absoluteString];
    video.knownDuration = 30000;
    video.startMilliseconds = -1;
    video.optionsJSON = @"{\"subtitle_track\":0}";
    video.subtitleJSON = @"[]";
    video.restricted = restricted;
    video.dataAvailable = YES;
    __weak LGVideoBackgroundAudioChecks *weak = self;
    video.allowed = ^BOOL(BOOL external) { return weak.grant; };
    video.backgroundAudioAllowed = ^BOOL { return YES; };
    video.requestPlay = ^BOOL { return weak.grant; };
    self.video = video;
    self.window.rootViewController = [[LGVideoNavigationController alloc] initWithRootViewController:video];
    [self.window makeKeyAndVisible];
    [video loadViewIfNeeded];
    [video startByUser];
}
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    self.samples = [NSMutableArray array];
    self.grant = YES;
    [NSFileManager.defaultManager createDirectoryAtPath:[[self documentPath:@""] stringByStandardizingPath]
        withIntermediateDirectories:YES attributes:nil error:nil];
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    self.began = NSProcessInfo.processInfo.systemUptime;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC/2), dispatch_get_main_queue(), ^{
        [self prepareVideoRestricted:NO];
        self.timer = [NSTimer scheduledTimerWithTimeInterval:.15 target:self selector:@selector(sample:) userInfo:nil repeats:YES];
    });
}
- (void)enter:(LGBackgroundStage)stage {
    self.stage = stage;
    self.changed = NSProcessInfo.processInfo.systemUptime;
    self.heldClock = [self.video positionMilliseconds];
    VLCMediaStats stats = [self.video playbackStats];
    self.heldAudio = stats.playedAudioBuffers;
    self.heldFrames = stats.displayedPictures;
    self.earlyOutput = NO;
    [self save:@{@"samples": self.samples} name:@"progress.json"];
}
- (void)simulateDataAvailable:(BOOL)available {
    self.video.dataAvailable = available;
    [NSNotificationCenter.defaultCenter postNotificationName:available ? UIApplicationProtectedDataDidBecomeAvailable :
        UIApplicationProtectedDataWillBecomeUnavailable object:UIApplication.sharedApplication];
}
- (void)sample:(NSTimer *)timer {
    LGBackgroundAudioVideo *v = self.video;
    NSTimeInterval now = NSProcessInfo.processInfo.systemUptime, elapsed = now - self.changed;
    BOOL background = UIApplication.sharedApplication.applicationState == UIApplicationStateBackground;
    int64_t time = [v positionMilliseconds];
    VLCMediaStats stats = [v playbackStats];
    BOOL playing = v.player.isPlaying;
    AVSampleBufferDisplayLayer *layer = [v sampleBufferLayer:v.movie.layer];
    BOOL displayReady = layer.status == AVQueuedSampleBufferRenderingStatusRendering;
    if (@available(iOS 17.4, *)) displayReady = layer.readyForDisplay;
    BOOL captions = NO;
    for (VLCMediaPlayerTrack *track in v.player.textTracks) if (track.isSelected) captions = YES;
    CMTime displayTime = layer.controlTimebase ? CMTimebaseGetTime(layer.controlTimebase) : kCMTimeInvalid;
    double displaySeconds = CMTIME_IS_NUMERIC(displayTime) ? CMTimeGetSeconds(displayTime) : -1;
    [self.samples addObject:@{@"stage": @(self.stage), @"cycle": @(self.cycle), @"elapsed": @(elapsed),
        @"time": @(now-self.began), @"clock": @(time), @"nativeClock": @(v.player.time.value.longLongValue),
        @"renderedClock": @(v.lastRenderedClock), @"displaySeconds": @(displaySeconds),
        @"buffering": @(v.buffering), @"decodeAudio": @(stats.decodedAudio),
        @"surface": layer ? [NSString stringWithFormat:@"%p", layer] : @"",
        @"surfaceAttached": @(v.movie.window != nil), @"surfaceStatus": @(layer.status),
        @"audio": @(stats.playedAudioBuffers), @"frames": @(stats.displayedPictures), @"background": @(background),
        @"localAudio": @(v.localAudioInBackground), @"playing": @(playing), @"hidden": @(v.movie.hidden),
        @"playRequested": @(v.playRequested), @"lockHidden": @(v.lockHidden),
        @"displayReady": @(displayReady), @"captionsSelected": @(captions), @"state": @(v.player.state)}];
    if (now-self.began > 39) { [self finish:@"Background audio probe timed out"]; return; }

    switch (self.stage) {
        case LGWaitForVideo:
            if (!playing || time < 1200 || !stats.playedAudioBuffers || !displayReady || !captions) return;
            [v togglePlay:nil];
            [self enter:LGForegroundPause];
            break;
        case LGForegroundPause:
            if (elapsed < .65) return;
            if (playing || v.playRequested || llabs(time-self.heldClock) > 300) {
                [self finish:@"Foreground Pause did not hold position"]; return;
            }
            [v togglePlay:nil];
            [self enter:LGExplicitResume];
            break;
        case LGEnterPausedBackground:
            if (!background) return;
            [self enter:LGPausedBackground];
            break;
        case LGPausedBackground: {
            if (elapsed < .8) return;
            if (!background || playing || v.playRequested || v.localAudioInBackground ||
                llabs(time-self.heldClock) > 300) {
                [self finish:@"Paused app switch changed playback intent or position"]; return;
            }
            [self enter:LGReturnPaused];
            NSString *marker = self.cycle == 1 ? @"foreground-ready" :
                [NSString stringWithFormat:@"foreground-ready-%ld", (long)self.cycle - 1];
            [self save:@{} name:marker];
            break;
        }
        case LGReturnPaused:
            if (UIApplication.sharedApplication.applicationState != UIApplicationStateActive) return;
            if (playing || v.playRequested || llabs(time-self.heldClock) > 300) {
                [self finish:@"Returning to the app changed paused playback"]; return;
            }
            [v togglePlay:nil];
            [self enter:LGExplicitResume];
            break;
        case LGExplicitResume:
            if (elapsed >= 1 && !self.earlyOutput) {
                self.earlyOutput = YES;
                self.lateAudio = stats.playedAudioBuffers;
                self.lateFrames = stats.displayedPictures;
                self.lateClock = time;
            }
            if (elapsed < 2.6) return;
            if (!playing || v.buffering || v.movie.hidden || !displayReady || !captions ||
                time < self.heldClock + 1500 || time < self.lateClock + 900 ||
                stats.playedAudioBuffers <= self.lateAudio || stats.displayedPictures < self.lateFrames + 5) {
                [self finish:@"Explicit Play did not sustain picture and audio after the first second"]; return;
            }
            if (++self.cycle <= 3) {
                [v togglePlay:nil];
                [self enter:LGEnterPausedBackground];
                NSString *marker = self.cycle == 1 ? @"background-ready" :
                    [NSString stringWithFormat:@"background-ready-%ld", (long)self.cycle - 1];
                [self save:@{} name:marker];
            } else {
                [self enter:LGEnterBackground];
                [self save:@{} name:@"background-ready-3"];
            }
            break;
        case LGEnterBackground:
            if (!background) return;
            if (!v.localAudioInBackground || !v.movie.hidden || !v.playRequested || [v canPlay:YES]) {
                [self finish:@"Ordinary video did not enter audio-only presentation"]; return;
            }
            [self enter:LGWaitInBackground];
            break;
        case LGWaitInBackground:
            if (elapsed < 2) return;
            if (!background || !playing || time < self.heldClock + 1200 || stats.playedAudioBuffers <= self.heldAudio) {
                [self finish:@"Ordinary audio or clock stopped in real background"]; return;
            }
            [self enter:LGReturnToVideo];
            [self save:@{} name:@"foreground-ready-3"];
            break;
        case LGReturnToVideo:
            if (background || v.localAudioInBackground || elapsed < .5 || !displayReady ||
                stats.displayedPictures <= self.heldFrames) return;
            if (v.movie.hidden || !playing || !captions || time < self.heldClock - 200) {
                [self finish:@"Foreground did not restore the captioned video at the current clock"]; return;
            }
            [self enter:LGLockOrdinary];
            [self simulateDataAvailable:NO];
            break;
        case LGLockOrdinary:
            if (elapsed < 1.2) return;
            if (!v.localAudioInBackground || !v.movie.hidden || !playing || ![v canPlay:NO] || [v canPlay:YES] ||
                time < self.heldClock + 700 || stats.playedAudioBuffers <= self.heldAudio) {
                [self finish:@"Protected-data notification stopped admitted ordinary audio"]; return;
            }
            [v pause];
            [self enter:LGPauseWhileLocked];
            break;
        case LGPauseWhileLocked:
            if (elapsed < .7) return;
            if (playing || v.playRequested || llabs(time-self.heldClock) > 200 || [v canPlay:NO]) {
                [self finish:@"Pause while locked failed to hold intent and position"]; return;
            }
            [self simulateDataAvailable:YES];
            [self enter:LGUnlockOrdinary];
            break;
        case LGUnlockOrdinary:
            if (elapsed < .7) return;
            if (playing || v.playRequested || v.movie.hidden || llabs(time-self.heldClock) > 200) {
                [self finish:@"Unlock changed paused playback intent"]; return;
            }
            [v startByUser];
            [self enter:LGResumeOrdinary];
            break;
        case LGResumeOrdinary:
            if (!playing || time < self.heldClock + 500 || stats.playedAudioBuffers <= self.heldAudio) return;
            [self simulateDataAvailable:NO];
            self.grant = NO;
            [self enter:LGRevokeOrdinary];
            break;
        case LGRevokeOrdinary:
            if (elapsed < .9) return;
            if (playing || v.playRequested || [v canPlay:NO] || !v.movie.hidden) {
                [self finish:@"Access revocation continued ordinary background playback"]; return;
            }
            self.grant = YES;
            [self simulateDataAvailable:YES];
            [self enter:LGReauthorizeOrdinary];
            break;
        case LGReauthorizeOrdinary: {
            if (elapsed < .7) return;
            if (playing || v.playRequested) { [self finish:@"Restored authorization triggered autoplay"]; return; }
            [self enter:LGStartProtected];
            [v retireWithCompletion:^{ [self prepareVideoRestricted:YES]; }];
            break;
        }
        case LGStartProtected:
            if (!playing || time < 700 || !stats.playedAudioBuffers) return;
            [self simulateDataAvailable:NO];
            [self enter:LGLockProtected];
            break;
        case LGLockProtected:
            if (elapsed < .7) return;
            if (playing || v.playRequested || !v.lockHidden || !v.movie.hidden || [v canPlay:NO]) {
                [self finish:@"Protected video played after device lock"]; return;
            }
            [self simulateDataAvailable:YES];
            [v revealSurface];
            [self enter:LGUnlockProtected];
            break;
        case LGUnlockProtected:
            if (elapsed < .7) return;
            if (playing || v.playRequested || v.lockHidden || llabs(time-self.heldClock) > 200) {
                [self finish:@"Protected video unlock changed Pause or position"]; return;
            }
            [self finish:nil];
            break;
    }
}
@end

int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(LGVideoBackgroundAudioChecks.class)); }
}
