// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

#import <VLCKit/vlc/libvlc_media_player.h>
@interface VLCMediaPlayer (LGClockProbe)
- (libvlc_media_player_t *)libVLCMediaPlayer;
@end
@interface LGTailLogger : NSObject <VLCLogging>
@property(nonatomic) VLCLogLevel level;
@property(nonatomic, strong) NSMutableArray *messages;
@end
@implementation LGTailLogger
- (void)handleMessage:(NSString *)message logLevel:(VLCLogLevel)level context:(VLCLogContext *)context {
    @synchronized(self) { if (self.messages.count < 5000) [self.messages addObject:message]; }
}
@end
// A real MKV with three seconds of video and ten seconds of audio. Reopening
// at six seconds must not require a video frame that does not exist.
@interface LGVideoAudioTailChecks : UIResponder <UIApplicationDelegate, UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) LGVideoController *video;
@property(nonatomic, strong) NSTimer *timer;
@property(nonatomic, strong) LGTailLogger *logger;
@property(nonatomic, strong) NSMutableArray *samples;
@property(nonatomic) NSInteger stage;
@property(nonatomic) NSTimeInterval began, changed;
@property(nonatomic) NSTimeInterval playStarted;
@property(nonatomic) int64_t held;
@property(nonatomic) int64_t tailEntry;
@property(nonatomic) BOOL tailDelivered;
@end
@implementation LGVideoAudioTailChecks
- (void)finish:(NSString *)error {
    [self.timer invalidate]; self.timer = nil;
    [self.video retireWithCompletion:nil];
    NSString *path = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents/result.json"];
    [NSFileManager.defaultManager createDirectoryAtPath:path.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil];
    NSDictionary *result = @{@"success": @(!error), @"error": error ?: @"", @"samples": self.samples, @"vlc": self.logger.messages ?: @[]};
    [[NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil] writeToFile:path atomically:YES];
}
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    self.samples = [NSMutableArray array];
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    self.video = [LGVideoController new];
    self.video.videoURL = [[NSBundle.mainBundle URLForResource:@"fixture" withExtension:@"mkv"] absoluteString];
    self.tailEntry = [NSBundle.mainBundle.infoDictionary[@"QAResume"] longLongValue];
    self.video.startMilliseconds = self.tailEntry ?: 6000;
    self.video.knownDuration = 10000;
    self.video.subtitleJSON = @"[]"; self.video.queueJSON = @"[]"; self.video.optionsJSON = @"{\"media_bounds\":{\"end_ms\":10000,\"video\":[{\"end_ms\":3000}],\"audio\":[{\"end_ms\":10000}]}}";
    self.video.allowed = ^BOOL(BOOL external) { return YES; };
    self.video.requestPlay = ^BOOL { return YES; };
    self.window.rootViewController = [[LGVideoNavigationController alloc] initWithRootViewController:self.video];
    [self.window makeKeyAndVisible];
    self.began = NSProcessInfo.processInfo.systemUptime;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC/2), dispatch_get_main_queue(), ^{
        self.logger = [LGTailLogger new]; self.logger.level = 4; self.logger.messages = [NSMutableArray array];
        self.video.player.libraryInstance.loggers = @[self.logger];
        self.playStarted = NSProcessInfo.processInfo.systemUptime;
        [self.video startByUser];
        self.timer = [NSTimer scheduledTimerWithTimeInterval:.05 target:self selector:@selector(sample:) userInfo:nil repeats:YES];
    });
}
- (void)sample:(NSTimer *)timer {
    LGVideoController *v = self.video;
    NSTimeInterval now = NSProcessInfo.processInfo.systemUptime;
    VLCMediaStats stats = [v playbackStats];
    [self.samples addObject:@{@"stage": @(self.stage), @"time": @(now-self.began),
        @"clock": @([v positionMilliseconds]), @"nativeClock": v.player.time.value ?: @(-1), @"coreClock": @(libvlc_media_player_get_time([v.player libVLCMediaPlayer]) / 1000),
        @"target": @(v.startMilliseconds), @"state": @(v.player.state),
        @"tracks": [v.player.videoTracks valueForKey:@"trackId"],
        @"frames": @(stats.displayedPictures), @"audio": @(stats.playedAudioBuffers),
        @"buffering": @(v.buffering), @"seekable": @(v.player.isSeekable)}];
    if (now-self.began > 45) { [self finish:@"Audio-tail playback timed out"]; return; }
    if (self.tailEntry > 0 && self.stage == 0) {
        int64_t tailLength = v.knownDuration - self.tailEntry;
        int64_t clockTolerance = 350;
        // VLC's public clock is sampled less often than buffer delivery.
        if (stats.playedAudioBuffers && [v nativeTimeMilliseconds] >= v.knownDuration - clockTolerance)
            self.tailDelivered = YES;
        if (v.ended) {
            if (!self.tailDelivered || !v.audioOnlyInput ||
                now-self.playStarted < (tailLength-clockTolerance) / 1000. ||
                stats.playedAudioBuffers < (tailLength-clockTolerance) / 24) {
                [self finish:@"Saved tail reached EOF without advancing the native audio clock"]; return;
            }
            [v startByUser]; self.stage = 7;
        } else if (v.player.state == VLCMediaPlayerStateStopped && now-self.playStarted > 2) {
            [self finish:@"Audio tail stopped without exposing Replay"];
        }
        return;
    }
    if (self.stage == 0 && v.player.isPlaying && v.startMilliseconds < 0 &&
        stats.playedAudioBuffers > 0 && [v positionMilliseconds] >= 6500) {
        if (v.buffering || !v.seek.enabled) { [self finish:@"Audio-only resume remained loading or disabled the timeline"]; return; }
        self.held = [v positionMilliseconds];
        [v pause]; self.changed = now; self.stage = 1;
    } else if (self.stage == 1 && now-self.changed > .6) {
        if (v.player.isPlaying || llabs([v positionMilliseconds]-self.held) > 200) {
            [self finish:@"Pause rewound the audio-only tail to the last picture"]; return;
        }
        [v seekToMilliseconds:0];
        if (v.playRequested || [v positionMilliseconds] != 0) { [self finish:@"Start over lost Pause or zero target"]; return; }
        [v startByUser]; self.stage = 2;
    } else if (self.stage == 2 && v.player.isPlaying && v.startMilliseconds < 0 &&
               stats.displayedPictures > 0 && [v positionMilliseconds] > 300) {
        if ([v positionMilliseconds] > 2500) { [self finish:@"Start over did not return to video"]; return; }
        [v seekToMilliseconds:6000]; self.changed = now; self.stage = 3;
    } else if (self.stage == 3 && now-self.changed > 3) {
        if (!v.player.isPlaying || v.buffering || !v.seek.enabled || [v positionMilliseconds] < 8000) {
            [self finish:@"Video-frame watchdog stalled despite continued audio and clock progress"]; return;
        }
        [v seekToMilliseconds:0]; self.changed = now; self.stage = 4;
    } else if (self.stage == 4 && now-self.changed > 3 && [v positionMilliseconds] >= 6500) {
        if (!v.player.isPlaying || v.buffering || stats.playedAudioBuffers == 0) {
            [self finish:@"Natural video EOF did not continue the audio clock"]; return;
        }
        self.held = [v positionMilliseconds]; [v pause]; self.changed = now; self.stage = 5;
    } else if (self.stage == 5 && now-self.changed > .5) {
        if (v.player.isPlaying || llabs([v positionMilliseconds]-self.held) > 200) {
            [self finish:@"Natural-tail Pause rewound to the last picture"]; return;
        }
        [v seekToMilliseconds:6000]; [v startByUser]; self.stage = 6;
    } else if (self.stage == 6 && v.ended) {
        if (!v.audioOnlyInput) { [self finish:@"Fixture did not finish in the audio-only input"]; return; }
        [v startByUser]; self.changed = now; self.stage = 7;
    } else if (self.stage == 7 && !v.audioOnlyInput && v.startMilliseconds < 0 &&
               stats.displayedPictures > 0 && stats.playedAudioBuffers > 0 && [v nativeTimeMilliseconds] > 300) {
        if ([v nativeTimeMilliseconds] > 2500) { [self finish:@"Replay did not restore opening picture and audio"]; return; }
        [self finish:nil];
    }
}
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(LGVideoAudioTailChecks.class)); }
}
