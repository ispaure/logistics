// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

// Production controller with deterministic receiver events, plus real VLC audio.
// No physical route is changed by this simulator regression fixture.
@interface LGReceiverItem : AVPlayerItem
@property(nonatomic) AVPlayerItemStatus fixtureStatus;
@end
@implementation LGReceiverItem
- (AVPlayerItemStatus)status { return self.fixtureStatus; }
@end
@interface LGReceiverPlayer : AVPlayer
@property(nonatomic, strong) LGReceiverItem *fixtureItem;
@property(nonatomic) BOOL fixtureExternal;
@property(nonatomic) AVPlayerTimeControlStatus fixtureControl;
@property(nonatomic) NSUInteger playCalls;
@property(nonatomic, strong) NSMutableArray *seeks;
@end
@implementation LGReceiverPlayer
- (AVPlayerItem *)currentItem { return self.fixtureItem; }
- (AVPlayerStatus)status { return AVPlayerStatusReadyToPlay; }
- (BOOL)isExternalPlaybackActive { return self.fixtureExternal; }
- (AVPlayerTimeControlStatus)timeControlStatus { return self.fixtureControl; }
- (void)play { self.playCalls++; self.fixtureControl = AVPlayerTimeControlStatusWaitingToPlayAtSpecifiedRate; }
- (void)pause { self.fixtureControl = AVPlayerTimeControlStatusPaused; }
- (void)replaceCurrentItemWithPlayerItem:(AVPlayerItem *)item { self.fixtureItem = (id)item; }
- (void)seekToTime:(CMTime)time toleranceBefore:(CMTime)before toleranceAfter:(CMTime)after completionHandler:(void (^)(BOOL))completion {
    [self.seeks addObject:[completion copy]];
}
@end
@interface LGVideoRouteProbe : LGVideoController
@property(nonatomic) BOOL fixtureRoute;
@property(nonatomic) BOOL fixtureDataUnavailable;
@end
@implementation LGVideoRouteProbe
- (BOOL)hasAirPlayAudioRoute { return self.fixtureRoute; }
- (BOOL)protectedDataAvailable { return !self.fixtureDataUnavailable; }
@end
@interface LGVideoAirPlayChecks : UIResponder <UIApplicationDelegate, UIWindowSceneDelegate, AVPlayerItemLegibleOutputPushDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) LGVideoRouteProbe *video;
@property(nonatomic, strong) NSMutableArray *samples;
@property(nonatomic) BOOL completed;
@property(nonatomic, strong) AVPlayer *hlsPlayer;
@property(nonatomic, copy) NSString *lastCaption;
@property(nonatomic, strong) AVPlayerItemVideoOutput *tailVideoOutput;
@property(nonatomic) NSInteger tailStage;
@property(nonatomic) BOOL tailEnded;
@property(nonatomic, strong) id tailEndObserver;
@property(nonatomic) NSTimeInterval tailPausedAt;
@property(nonatomic) double tailHeld;
@end
@implementation LGVideoAirPlayChecks
- (void)finish:(NSString *)error {
    if (self.completed) return;
    self.completed = YES;
    NSString *directory = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents"];
    [NSFileManager.defaultManager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
    UIGraphicsImageRenderer *renderer = [[UIGraphicsImageRenderer alloc] initWithBounds:self.window.bounds];
    UIImage *image = [renderer imageWithActions:^(UIGraphicsImageRendererContext *context) {
        [self.window drawViewHierarchyInRect:self.window.bounds afterScreenUpdates:YES];
    }];
    [UIImagePNGRepresentation(image) writeToFile:[directory stringByAppendingPathComponent:@"airplay-controls.png"] atomically:YES];
    NSDictionary *report = @{@"success": @(!error), @"error": error ?: @"", @"samples": self.samples,
        @"scope": @"Real UIKit/VLC audio, native MP4/MKV remux and AVKit HLS subtitle selection/seek; simulated receiver events; no physical Apple TV"};
    [[NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:nil]
        writeToFile:[directory stringByAppendingPathComponent:@"result.json"] atomically:YES];
}
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    self.samples = [NSMutableArray array];
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    LGVideoRouteProbe *v = self.video = [LGVideoRouteProbe new];
    v.videoURL = [[NSBundle.mainBundle URLForResource:@"fixture" withExtension:@"mp4"] absoluteString];
    v.startMilliseconds = 0;
    v.knownDuration = 30000;
    v.subtitleJSON = @"[]"; v.queueJSON = @"[]";
    v.optionsJSON = @"{\"video_title\":\"Catching Fire (2013).mkv\",\"source_label\":\"Local file\",\"source_remote\":false}";
    v.allowed = ^BOOL(BOOL external) { return YES; };
    v.requestPlay = ^BOOL { return YES; };
    v.airPlayAllowed = ^BOOL { return YES; };
    v.airPlayAvailable = YES;
    self.window.rootViewController = [[LGVideoNavigationController alloc] initWithRootViewController:v];
    [self.window makeKeyAndVisible];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        // A transient muted decoder must never become the user's mute choice.
        v.player.audio.muted = YES;
        v.audioSuppressed = NO;
        [v pause];
        if (v.resumeMuted) { [self finish:@"Decoder mute leaked into user intent"]; return; }
        [v startByUser];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 3 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            if (!v.player.isPlaying || v.player.audio.isMuted || !v.player.audioTracks.count) {
                [self finish:@"Local playback did not restore unmuted audio"]; return;
            }
            [self.samples addObject:@{@"event": @"local-audio", @"muted": @(v.player.audio.isMuted)}];
            [v toggleMute:nil]; [v pause]; [v startByUser];
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), dispatch_get_main_queue(), ^{
                if (!v.resumeMuted || !v.player.audio.isMuted) { [self finish:@"User mute was lost on resume"]; return; }
                [v toggleMute:nil];
                v.localAudioNeedsRefresh = YES;
                [v tick:nil];
                if (v.localAudioNeedsRefresh || v.player.audio.isMuted) { [self finish:@"Local route recovery did not flush audio"]; return; }
                [v pause];
                [v setControlsShown:YES];
                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC / 2), dispatch_get_main_queue(), ^{ [self checkReceiver]; });
            });
        });
    });
}
- (LGReceiverPlayer *)attachReceiver {
    LGReceiverPlayer *player = [LGReceiverPlayer new];
    player.seeks = [NSMutableArray array];
    player.fixtureItem = [[LGReceiverItem alloc] initWithURL:[NSBundle.mainBundle URLForResource:@"fixture" withExtension:@"mp4"]];
    LGVideoRouteProbe *v = self.video;
    v.airPlayPlayer = v.airPlayRoutePlayer = player;
    v.fixtureRoute = YES;
    v.airPlayWasExternal = NO;
    v.airPlaySeekTarget = -1;
    player.allowsExternalPlayback = YES;
    return player;
}
- (BOOL)checkLockPolicy {
    LGVideoRouteProbe *v = self.video;
    v.fixtureDataUnavailable = YES;
    if ([v canPlay:NO] || [v allowsAirPlay]) { [self finish:@"Locked device admitted new playback"]; return NO; }
    LGReceiverPlayer *player = [self attachReceiver];
    [v protectedData:nil];
    if ([v hasAirPlay] || player.allowsExternalPlayback) { [self finish:@"Lock retained an unestablished handoff"]; return NO; }

    v.fixtureDataUnavailable = NO;
    player = [self attachReceiver];
    player.fixtureItem.fixtureStatus = AVPlayerItemStatusReadyToPlay;
    player.fixtureExternal = YES;
    v.airPlayWasExternal = YES;
    [v startAirPlayPlayback];
    v.fixtureDataUnavailable = YES;
    [v protectedData:nil]; [v background]; [v tick:nil];
    if (v.airPlayPlayer != player || !v.playRequested || ![v canPlay:NO] || ![v allowsAirPlay]) {
        [self finish:@"Screen lock stopped authorized AirPlay"]; return NO;
    }
    // A receiver pause and a resume on the locked phone keep the same item.
    [player pause]; [v updateAirPlay];
    if (v.playRequested || v.airPlayPlayer != player) { [self finish:@"Locked receiver pause lost the session"]; return NO; }
    [v startAirPlayPlayback];
    if (!v.playRequested || player.playCalls != 2) { [self finish:@"Locked AirPlay could not resume"]; return NO; }
    v.interrupted = YES;
    if ([v canPlay:NO]) { [self finish:@"Locked AirPlay bypassed an interruption"]; return NO; }
    v.interrupted = NO;
    v.airPlayAllowed = ^BOOL { return NO; };
    [v updateAirPlay];
    if ([v hasAirPlay] || player.allowsExternalPlayback || [v canPlay:NO]) {
        [self finish:@"Lock exemption bypassed source revocation"]; return NO;
    }
    v.airPlayAllowed = ^BOOL { return YES; };

    player = [self attachReceiver];
    v.airPlayWasExternal = YES;
    v.playRequested = YES;
    v.fixtureRoute = NO; player.fixtureExternal = NO;
    [v updateAirPlay];
    if ([v hasAirPlay] || v.playRequested || [v canPlay:NO]) {
        [self finish:@"Route loss resumed local video while locked"]; return NO;
    }

    player = [self attachReceiver];
    player.fixtureExternal = YES;
    v.airPlayWasExternal = YES;
    v.restricted = YES;
    [v protectedData:nil];
    if ([v hasAirPlay] || !v.lockHidden || [v canPlay:NO] || player.allowsExternalPlayback) {
        [self finish:@"Session-protected video survived lock"]; return NO;
    }
    v.restricted = NO;
    v.fixtureDataUnavailable = NO;
    [v revealSurface];
    [self.samples addObject:@{@"event": @"airplay-lock", @"continued": @YES, @"pauseResume": @YES,
        @"newHandoffDenied": @YES, @"revocation": @YES, @"routeLoss": @YES, @"protectedStopped": @YES}];
    return YES;
}
- (BOOL)checkRemuxMetadata {
    LGMKVRemux *remux = [[LGMKVRemux alloc] initWithPath:[NSBundle.mainBundle pathForResource:@"airplay" ofType:@"mkv"]];
    NSData *data = [[remux renditionsJSON] dataUsingEncoding:NSUTF8StringEncoding];
    NSDictionary *metadata = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
    NSDictionary *video = metadata[@"video"];
    if (![video[@"range"] isEqual:@"PQ"] || fabs([video[@"frameRate"] doubleValue] - 24000.0 / 1001) > .001 ||
        ![remux initializationForTrack:-1].length || ![remux initializationForTrack:[metadata[@"defaultAudio"] intValue]].length) {
        [self finish:@"Bitstream HDR/cadence metadata or playable rendition headers are missing"]; return NO;
    }
    [self.samples addObject:@{@"event": @"hdr-metadata", @"video": video}];
    for (NSNumber *index in @[@0, @2, @1, @0, @2, @1]) {
        if (![remux fragment:index.unsignedIntegerValue track:-1].length ||
            ![remux fragment:index.unsignedIntegerValue track:[metadata[@"defaultAudio"] intValue]].length) {
            [self finish:@"A forward/backward MKV video/audio fragment request failed"]; return NO;
        }
    }
    return YES;
}
- (BOOL)exportSubtitleFixtures {
    NSString *documents = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents"];
    NSMutableDictionary *fixtures = [NSMutableDictionary dictionary];
    for (NSString *extension in @[@"mkv", @"mp4", @"tail", @"reverse", @"reverse-opus"]) {
        BOOL reverseTail = [extension hasPrefix:@"reverse"];
        BOOL tail = [extension isEqualToString:@"tail"] || reverseTail;
        LGMKVRemux *remux = [[LGMKVRemux alloc] initWithPath:[NSBundle.mainBundle pathForResource:tail ? extension : @"captions" ofType:tail ? @"mkv" : extension]
            bounds:reverseTail ? @"{\"end_ms\":18000,\"audio\":[{\"end_ms\":3008}]}" : tail ? @"{\"end_ms\":90016}" : @"{}"];
        NSData *json = [[remux renditionsJSON] dataUsingEncoding:NSUTF8StringEncoding];
        NSDictionary *metadata = json ? [NSJSONSerialization JSONObjectWithData:json options:0 error:nil] : nil;
        if (!metadata || (!tail && [metadata[@"text"] count] != 2)) { [self finish:[extension stringByAppendingString:@" subtitle tracks missing"]]; return NO; }
        fixtures[extension] = metadata;
        NSString *root = [documents stringByAppendingPathComponent:[@"hls/" stringByAppendingString:extension]];
        NSMutableDictionary *routes = [NSMutableDictionary dictionaryWithObject:@-1 forKey:@"video"];
        for (NSDictionary *track in metadata[@"audio"]) routes[[NSString stringWithFormat:@"audio-%@", track[@"id"]]] = track[@"id"];
        for (NSDictionary *track in metadata[@"text"]) routes[[NSString stringWithFormat:@"text-%@", track[@"id"]]] = track[@"id"];
        for (NSString *route in routes) {
            NSString *directory = [root stringByAppendingPathComponent:route];
            [NSFileManager.defaultManager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
            int track = [routes[route] intValue];
            BOOL text = [route hasPrefix:@"text-"];
            if (!text && ![[remux initializationForTrack:track] writeToFile:[directory stringByAppendingPathComponent:@"init.mp4"] atomically:YES]) {
                [self finish:[NSString stringWithFormat:@"%@ %@ initialization failed", extension, route]]; return NO;
            }
            NSUInteger count = [metadata[@"boundaries"] count] - 1;
            // Read backwards first so subtitle extraction cannot depend on the
            // demuxer's previous cursor or a sequential video request.
            for (NSUInteger reverse = count; reverse; reverse--) {
                NSUInteger index = reverse - 1;
                NSNumber *audioEnd = nil;
                for (NSDictionary *audio in metadata[@"audio"]) if ([audio[@"id"] intValue] == track) audioEnd = audio[@"end_ms"];
                if (audioEnd && [metadata[@"boundaries"][index] longLongValue] >= audioEnd.longLongValue) continue;
                NSData *data = text ? [[remux textSegment:index track:track] dataUsingEncoding:NSUTF8StringEncoding] : [remux fragment:index track:track];
                NSString *file = [NSString stringWithFormat:@"segment-%lu.%@", (unsigned long)index, text ? @"json" : @"m4s"];
                if (!data.length || ![data writeToFile:[directory stringByAppendingPathComponent:file] atomically:YES]) {
                    [self finish:[NSString stringWithFormat:@"%@ %@ fragment %lu failed", extension, route, (unsigned long)index]]; return NO;
                }
                if (text && !tail && index == 2) {
                    NSString *cues = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
                    if (![cues containsString:@"CROSSING AIRPLAY CAPTION"] || [cues containsString:@"Default,"]) {
                        [self finish:[extension stringByAppendingString:@" lost overlapping subtitle text"]]; return NO;
                    }
                }
            }
        }
    }
    [[NSJSONSerialization dataWithJSONObject:fixtures options:0 error:nil]
        writeToFile:[documents stringByAppendingPathComponent:@"hls-fixtures.json"] atomically:YES];
    [self awaitHLSFixtures:100];
    return YES;
}
- (void)awaitHLSFixtures:(NSUInteger)attempts {
    NSData *data = [NSData dataWithContentsOfFile:[NSHomeDirectory() stringByAppendingPathComponent:@"Documents/hls-urls.json"]];
    if (data) { [self checkHLS:[NSJSONSerialization JSONObjectWithData:data options:0 error:nil]]; return; }
    if (!attempts) { [self finish:@"Host did not serve subtitle fixtures"]; return; }
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC / 10), dispatch_get_main_queue(), ^{ [self awaitHLSFixtures:attempts - 1]; });
}
- (void)checkHLS:(NSArray<NSString *> *)urls {
    if (!urls.count) { [self finish:nil]; return; }
    if (([urls.firstObject containsString:@"/tail/"] || [urls.firstObject containsString:@"/reverse"])) {
        NSString *tailURL = urls.firstObject;
        if ([NSProcessInfo.processInfo.environment[@"LG_TAIL_AUDIO_ONLY"] boolValue])
            tailURL = [tailURL stringByReplacingOccurrencesOfString:@"/index.m3u8" withString:@"/audio-1/index.m3u8"];
        self.hlsPlayer = [AVPlayer playerWithURL:[NSURL URLWithString:tailURL]];
        AVPlayerItemLegibleOutput *captions = [[AVPlayerItemLegibleOutput alloc] initWithMediaSubtypesForNativeRepresentation:nil];
        [captions setDelegate:self queue:dispatch_get_main_queue()];
        [self.hlsPlayer.currentItem addOutput:captions];
        self.lastCaption = @"";
        AVPlayerItem *tailItem = self.hlsPlayer.currentItem;
        [tailItem.asset loadMediaSelectionGroupForMediaCharacteristic:AVMediaCharacteristicLegible completionHandler:^(AVMediaSelectionGroup *group, NSError *error) {
            dispatch_async(dispatch_get_main_queue(), ^{
                if (error || !group.options.count) { [self finish:@"Tail captions unavailable"]; return; }
                [tailItem selectMediaOption:group.options.firstObject inMediaSelectionGroup:group];
            });
        }];
        self.tailStage = 0; self.tailEnded = NO;
        self.tailEndObserver = [NSNotificationCenter.defaultCenter addObserverForName:AVPlayerItemDidPlayToEndTimeNotification object:self.hlsPlayer.currentItem queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) { self.tailEnded = YES; }];
        self.tailVideoOutput = [[AVPlayerItemVideoOutput alloc] initWithPixelBufferAttributes:@{(id)kCVPixelBufferPixelFormatTypeKey: @(kCVPixelFormatType_32BGRA)}];
        [self.hlsPlayer.currentItem addOutput:self.tailVideoOutput];
        [self.hlsPlayer play];
        [self checkHLSTail:urls attempts:100 sought:NO];
        return;
    }
    AVURLAsset *asset = [AVURLAsset URLAssetWithURL:[NSURL URLWithString:urls.firstObject] options:nil];
    [asset loadMediaSelectionGroupForMediaCharacteristic:AVMediaCharacteristicLegible completionHandler:^(AVMediaSelectionGroup *group, NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            NSArray *options = [AVMediaSelectionGroup playableMediaSelectionOptionsFromArray:group.options ?: @[]];
            if (error || options.count != 2 || !group.allowsEmptySelection) {
                [self finish:[NSString stringWithFormat:@"AVKit subtitles unavailable: %lu options, %@", (unsigned long)options.count, error]]; return;
            }
            AVPlayerItem *item = [AVPlayerItem playerItemWithAsset:asset];
            AVPlayerItemLegibleOutput *captions = [[AVPlayerItemLegibleOutput alloc] initWithMediaSubtypesForNativeRepresentation:nil];
            [captions setDelegate:self queue:dispatch_get_main_queue()];
            [item addOutput:captions];
            self.lastCaption = @"";
            self.hlsPlayer = [AVPlayer playerWithPlayerItem:item];
            [item selectMediaOption:options.lastObject inMediaSelectionGroup:group];
            [self.hlsPlayer play];
            [self checkHLSReady:urls group:group attempts:100];
        });
    }];
}
- (BOOL)checkTailPicture:(NSString *)phase near:(double)expected {
    CMTime display = kCMTimeInvalid;
    CVPixelBufferRef frame = [self.tailVideoOutput copyPixelBufferForItemTime:self.hlsPlayer.currentTime itemTimeForDisplay:&display];
    double time = CMTimeGetSeconds(display);
    BOOL valid = frame && isfinite(time) && fabs(time - expected) < .8;
    [self.samples addObject:@{@"event": @"hls-tail-picture", @"phase": phase, @"present": @(frame != NULL), @"time": @(isfinite(time) ? time : -1)}];
    if (frame) CVPixelBufferRelease(frame);
    return valid;
}
- (void)checkHLSTail:(NSArray *)urls attempts:(NSUInteger)attempts sought:(BOOL)sought {
    AVPlayerItem *item = self.hlsPlayer.currentItem;
    double clock = CMTimeGetSeconds(self.hlsPlayer.currentTime);
    BOOL audioOnly = [NSProcessInfo.processInfo.environment[@"LG_TAIL_AUDIO_ONLY"] boolValue];
    BOOL reverse = [urls.firstObject containsString:@"/reverse"];
    if (attempts % 10 == 0) [self.samples addObject:@{@"event": @"hls-tail-state", @"clock": @(clock),
        @"status": @(item.status), @"control": @(self.hlsPlayer.timeControlStatus), @"stage": @(self.tailStage),
        @"reason": self.hlsPlayer.reasonForWaitingToPlay ?: @"", @"ranges": [item.loadedTimeRanges description]}];
    if (item.status == AVPlayerItemStatusFailed || !attempts) {
        [self finish:[NSString stringWithFormat:@"Audio-tail HLS failed stage %ld at %.3f: %@", (long)self.tailStage, clock, item.error]]; return;
    }
    double target = -1;
    if (item.status == AVPlayerItemStatusReadyToPlay && self.tailStage == 0) { target = 1; self.tailStage = 1; }
    else if (self.tailStage == 1 && clock > 3.5) {
        if (!audioOnly && ![self checkTailPicture:@"transition" near:reverse ? clock : 3]) { [self finish:@"Timing repair shifted the opening video presentation"]; return; }
        target = reverse ? 6 : 60; self.tailStage = 2;
    } else if (self.tailStage == 2 && clock > (reverse ? 6.5 : 60.5) && self.hlsPlayer.timeControlStatus == AVPlayerTimeControlStatusPlaying) {
        if (![self.lastCaption containsString:reverse ? @"VIDEO TAIL CAPTION" : @"AUDIO TAIL CAPTION"]) { [self finish:@"Native AVPlayer omitted the tail caption"]; return; }
        if (!audioOnly && ![self checkTailPicture:@"tail" near:reverse ? clock : 3]) { [self finish:@"Audio-tail HLS did not retain the final picture"]; return; }
        [self.samples addObject:@{@"event": @"hls-audio-tail", @"clock": @(clock), @"duration": @(CMTimeGetSeconds(item.duration))}];
        [self.hlsPlayer pause]; self.tailHeld = clock; self.tailPausedAt = NSProcessInfo.processInfo.systemUptime; self.tailStage = 3;
    } else if (self.tailStage == 3 && NSProcessInfo.processInfo.systemUptime-self.tailPausedAt > .4) {
        if (fabs(clock-self.tailHeld) > .1) { [self finish:@"Audio-tail HLS ignored Pause"]; return; }
        target = 1; self.tailStage = 4;
    } else if (self.tailStage == 4 && clock > 1.3) {
        if (!audioOnly && ![self checkTailPicture:@"back" near:clock]) { [self finish:@"Audio-tail HLS failed to restore video on backward seek"]; return; }
        target = reverse ? 17.5 : 89.5; self.tailStage = 5;
    } else if (self.tailStage == 5 && self.tailEnded && self.hlsPlayer.rate == 0 && clock > (reverse ? 17.5 : 89.5)) {
        double end = reverse ? 18 : 90.016;
        if (clock > end + .3 || CMTimeGetSeconds(item.duration) > end + .3) { [self finish:@"Text extended native HLS playback beyond A/V"]; return; }
        [NSNotificationCenter.defaultCenter removeObserver:self.tailEndObserver]; self.tailEndObserver = nil;
        [self.samples addObject:@{@"event": @"hls-tail-end", @"clock": @(clock), @"duration": @(CMTimeGetSeconds(item.duration))}];
        [self.hlsPlayer pause]; self.hlsPlayer = nil; self.tailVideoOutput = nil;
        [self checkHLS:[urls subarrayWithRange:NSMakeRange(1, urls.count - 1)]]; return;
    }
    if (target >= 0) {
        [self.hlsPlayer seekToTime:CMTimeMakeWithSeconds(target, 1000) toleranceBefore:kCMTimeZero toleranceAfter:kCMTimeZero completionHandler:^(BOOL finished) {
            dispatch_async(dispatch_get_main_queue(), ^{
                if (!finished) { [self finish:@"Audio-tail HLS seek rejected"]; return; }
                [self.hlsPlayer play];
                [self checkHLSTail:urls attempts:100 sought:YES];
            });
        }]; return;
    }
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC/10), dispatch_get_main_queue(), ^{
        [self checkHLSTail:urls attempts:attempts-1 sought:sought];
    });
}
- (void)checkHLSReady:(NSArray *)urls group:(AVMediaSelectionGroup *)group attempts:(NSUInteger)attempts {
    AVPlayerItem *item = self.hlsPlayer.currentItem;
    if (item.status == AVPlayerItemStatusFailed || !attempts) { [self finish:[NSString stringWithFormat:@"HLS playback failed: %@", item.error]]; return; }
    if (item.status != AVPlayerItemStatusReadyToPlay) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC / 10), dispatch_get_main_queue(), ^{ [self checkHLSReady:urls group:group attempts:attempts - 1]; });
        return;
    }
    if (![[item.currentMediaSelection selectedMediaOptionInMediaSelectionGroup:group] isEqual:group.options.lastObject]) { [self finish:@"AVKit did not select the requested subtitles"]; return; }
    [self.hlsPlayer seekToTime:CMTimeMakeWithSeconds(12.5, 1000) toleranceBefore:kCMTimeZero toleranceAfter:kCMTimeZero completionHandler:^(BOOL finished) {
        dispatch_async(dispatch_get_main_queue(), ^{
            if (!finished || item.status == AVPlayerItemStatusFailed) { [self finish:@"Captioned HLS seek failed"]; return; }
            [self checkHLSCaption:urls group:group attempts:30];
        });
    }];
}
- (void)legibleOutput:(AVPlayerItemLegibleOutput *)output didOutputAttributedStrings:(NSArray<NSAttributedString *> *)strings nativeSampleBuffers:(NSArray *)buffers forItemTime:(CMTime)time {
    for (NSAttributedString *string in strings) if (string.length) self.lastCaption = string.string;
}
- (void)checkHLSCaption:(NSArray *)urls group:(AVMediaSelectionGroup *)group attempts:(NSUInteger)attempts {
    if (![self.lastCaption containsString:@"CROSSING AIRPLAY CAPTION"]) {
        if (!attempts) { [self finish:@"AVKit did not deliver the subtitle spanning the seek"]; return; }
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC / 10), dispatch_get_main_queue(), ^{ [self checkHLSCaption:urls group:group attempts:attempts - 1]; });
        return;
    }
    AVPlayerItem *item = self.hlsPlayer.currentItem;
    [item selectMediaOption:nil inMediaSelectionGroup:group];
    if ([item.currentMediaSelection selectedMediaOptionInMediaSelectionGroup:group]) { [self finish:@"AVKit could not turn subtitles off"]; return; }
    [self.samples addObject:@{@"event": @"hls-subtitles", @"container": [[NSURL URLWithString:urls.firstObject] URLByDeletingLastPathComponent].lastPathComponent,
        @"options": @(group.options.count), @"selected": @YES, @"off": @YES, @"seek": @YES, @"caption": self.lastCaption}];
    [self.hlsPlayer pause]; self.hlsPlayer = nil;
    [self checkHLS:[urls subarrayWithRange:NSMakeRange(1, urls.count - 1)]];
}
- (void)checkReceiver {
    LGVideoRouteProbe *v = self.video;
    [v setControlsShown:YES];
    [v.view layoutIfNeeded];
    [v showCachedRanges:@"{\"local\":true,\"approximate\":true,\"ranges\":[[0,1]]}"];
    [v updateTimeline];
    if (!v.cacheStrip.hidden || v.cacheApproximate || [v.timeLabel.text containsString:@"Cache"] ||
        ![v.videoTitle.text isEqual:@"Catching Fire (2013).mkv"] || ![v.sourceLabel.text isEqual:@"Local file"] ||
        !v.sourceIcon.image || v.navigationItem.prompt.length || !v.videoHeader.window) {
        [self finish:[NSString stringWithFormat:@"Local identity/cache: hidden=%d approximate=%d title=%@ source=%@ window=%@",
            v.cacheStrip.hidden, v.cacheApproximate, v.videoTitle.text, v.sourceLabel.text, v.videoHeader.window]]; return;
    }
    if (![LGVideoAudioLabel(2, @[@"", @"Surround", @""], @"Audio Coding 3 (AC-3)", 6, 48000) isEqual:@"#2 · AC-3 · 6 ch"] ||
        ![LGVideoAudioLabel(1, @[@"English", @"Commentary", @"commentary"], @"mp4a", 2, 44100)
            isEqual:@"#1 · English · Commentary · AAC · Stereo · 44.1 kHz"]) {
        [self finish:@"Audio labels lost useful metadata or repeated generic text"]; return;
    }
    NSString *audioLabel = [v trackLabel:v.player.audioTracks.firstObject index:0];
    if (![[audioLabel stringByReplacingOccurrencesOfString:@"✓ " withString:@""] isEqual:@"#1 · AAC · Mono"]) {
        [self finish:[@"Live VLC audio metadata missing from label: " stringByAppendingString:audioLabel]]; return;
    }
    [self.samples addObject:@{@"event": @"local-chrome", @"cacheHidden": @YES, @"audioLabels": @YES, @"audioLabel": audioLabel}];
    NSArray *buttons = v.transport.arrangedSubviews;
    CGRect route = [v.airPlayPicker convertRect:v.airPlayPicker.bounds toView:v.view];
    CGRect forward = [buttons[2] convertRect:[buttons[2] bounds] toView:v.view];
    [self.samples addObject:@{@"event": @"layout", @"route": NSStringFromCGRect(route), @"forward": NSStringFromCGRect(forward), @"bounds": NSStringFromCGRect(v.view.bounds), @"count": @(buttons.count)}];
    CGRect routeAlignment = [v.airPlayPicker alignmentRectForFrame:route];
    CGRect forwardAlignment = [buttons[2] alignmentRectForFrame:forward];
    if (buttons.count != 4 || buttons.lastObject != v.airPlayPicker ||
        CGRectGetMinX(route) < CGRectGetMaxX(forward) || fabs(CGRectGetMidY(routeAlignment)-CGRectGetMidY(forwardAlignment)) > 1 ||
        route.size.width < 44 || route.size.height < 44 || !CGRectContainsRect(v.view.bounds, route)) {
        [self finish:@"AirPlay is not reachable beside forward 10 seconds"]; return;
    }
    [v pause];
    if (![self checkLockPolicy]) return;
    LGReceiverPlayer *player = [LGReceiverPlayer new];
    player.seeks = [NSMutableArray array];
    player.fixtureItem = [[LGReceiverItem alloc] initWithURL:[NSBundle.mainBundle URLForResource:@"fixture" withExtension:@"mp4"]];
    v.airPlayPlayer = v.airPlayRoutePlayer = player; v.fixtureRoute = YES;
    player.allowsExternalPlayback = YES;
    v.airPlaySeekTarget = v.airPlayStartPosition = 12000;
    [v startAirPlayPlayback];
    [v updateTimeline];
    if (player.playCalls != 1 || !v.seek.enabled || !v.playRequested) { [self finish:@"Loading resume blocked playback or timeline"]; return; }
    [v seekAirPlay:18000];
    if (v.airPlaySeekTarget != 18000 || player.seeks.count) { [self finish:@"Loading seek was not queued"]; return; }
    [v forward:nil]; [v forward:nil];
    if (v.airPlaySeekTarget != 29999 || player.seeks.count) { [self finish:@"Loading forward skips did not accumulate and clamp"]; return; }
    [v back:nil];
    if (v.airPlaySeekTarget != 19999) { [self finish:@"Loading direction change lost the pending position"]; return; }
    [v seekAirPlay:18000];
    player.fixtureItem.fixtureStatus = AVPlayerItemStatusReadyToPlay;
    [v updateAirPlay];
    [v forward:nil];
    if (v.airPlaySeekTarget != 28000) { [self finish:@"Ready forward skip lost the pending position"]; return; }
    [v forward:nil];
    if (v.airPlaySeekTarget != 29999) { [self finish:@"Ready forward skip was not bounded by duration"]; return; }
    [v back:nil];
    if (v.airPlaySeekTarget != 19999) { [self finish:@"Ready direction change lost the pending position"]; return; }
    [v seekAirPlay:9000];
    if (player.seeks.count != 5) { [self finish:@"Ready item did not accept updated seek"]; return; }
    ((void (^)(BOOL))player.seeks[0])(NO);
    dispatch_async(dispatch_get_main_queue(), ^{
        if (!v.airPlaySeekPending || v.airPlaySeekTarget != 9000) { [self finish:@"Obsolete completion erased newer seek"]; return; }
        ((void (^)(BOOL))player.seeks.lastObject)(NO);
        dispatch_async(dispatch_get_main_queue(), ^{
            if (v.airPlaySeekPending || v.airPlaySeekTarget >= 0 || player.playCalls != 2) { [self finish:@"Interrupted seek left receiver stuck"]; return; }
            [v seekAirPlay:15000]; [v pause];
            ((void (^)(BOOL))player.seeks.lastObject)(YES);
            dispatch_async(dispatch_get_main_queue(), ^{
                if (player.playCalls != 2 || v.playRequested) { [self finish:@"Seek completion undid explicit Pause"]; return; }
                [self checkReceiverPause:player iteration:0];
            });
        });
    });
}
- (void)checkReceiverPause:(LGReceiverPlayer *)player iteration:(NSUInteger)iteration {
    LGVideoRouteProbe *v = self.video;
    if (iteration < 3) {
        [v startAirPlayPlayback];
        [v seekAirPlay:15000 + iteration * 1000];
        NSUInteger calls = player.playCalls;
        // AVKit/Apple TV pauses AVPlayer directly, bypassing the phone's pause
        // method. Cover both a timer tick during the seek and completion first.
        [player pause];
        if (iteration == 0) [v updateAirPlay];
        ((void (^)(BOOL))player.seeks.lastObject)(iteration != 2);
        dispatch_async(dispatch_get_main_queue(), ^{
            if (player.playCalls != calls || v.playRequested || player.timeControlStatus != AVPlayerTimeControlStatusPaused) {
                [self finish:@"Seek completion undid receiver Pause"]; return;
            }
            [self checkReceiverPause:player iteration:iteration + 1];
        });
        return;
    }
    [self.samples addObject:@{@"event": @"receiver-pause", @"duringSeek": @YES,
        @"beforeTick": @YES, @"interruptedSeek": @YES}];
    player.fixtureExternal = YES;
    v.airPlayWasExternal = YES;
    for (NSUInteger cycle = 0; cycle < 6; cycle++) {
        [player play]; [v updateAirPlay];
        [v backgroundNotification:nil];
        if (!v.playRequested || v.airPlayPlayer != player) { [self finish:@"App switching lost the receiver session"]; return; }
        [player pause];
        [v applyAirPlayPlaybackOptions]; [v updateAirPlay];
        if (v.playRequested || player.timeControlStatus != AVPlayerTimeControlStatusPaused) {
            [self finish:@"Receiver Pause was lost after app switching"]; return;
        }
    }
    [self.samples addObject:@{@"event": @"receiver-background", @"cycles": @6}];
    [v startAirPlayPlayback]; [v seekAirPlay:17000];
    v.airPlaySeekDeadline = NSProcessInfo.processInfo.systemUptime - 1;
    [v updateAirPlay];
    if ([v hasAirPlay] || !v.localAudioNeedsRefresh || [v positionMilliseconds] != 17000) {
        [self finish:@"Seek timeout failed to detach at requested position"]; return;
    }
    [self.samples addObject:@{@"event": @"receiver", @"loadingSeek": @YES, @"staleCompletion": @YES,
        @"interruptedSeek": @YES, @"pausedSeek": @YES, @"timeout": @YES,
        @"forwardSkip": @YES, @"directionChange": @YES, @"endClamp": @YES}];
    if (!player.allowsExternalPlayback || player.currentItem) { [self finish:@"Timeout did not preserve an empty reusable route"]; return; }
    [v retireWithCompletion:^{
        if (player.allowsExternalPlayback || player.currentItem || v.airPlayRoutePlayer) {
            [self finish:@"Closing after detach left AirPlay enabled"]; return;
        }
        [self.samples addObject:@{@"event": @"airplay-close", @"externalPlaybackDisabled": @YES, @"itemReleased": @YES}];
        if ([self checkRemuxMetadata]) [self exportSubtitleFixtures];
    }];
}
@end
int main(int argc, char **argv) { @autoreleasepool { return UIApplicationMain(argc, argv, nil, @"LGVideoAirPlayChecks"); } }
