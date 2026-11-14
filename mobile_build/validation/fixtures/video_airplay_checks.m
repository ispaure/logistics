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
@end
@implementation LGVideoRouteProbe
- (BOOL)hasAirPlayAudioRoute { return self.fixtureRoute; }
@end
@interface LGVideoAirPlayChecks : UIResponder <UIApplicationDelegate, UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) LGVideoRouteProbe *video;
@property(nonatomic, strong) NSMutableArray *samples;
@property(nonatomic) BOOL completed;
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
        @"scope": @"Real UIKit/VLC audio state; simulated AVPlayer loading, seek completions and routes; no physical Apple TV"};
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
    v.subtitleJSON = @"[]"; v.queueJSON = @"[]"; v.optionsJSON = @"{}";
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
    return YES;
}
- (void)checkReceiver {
    LGVideoRouteProbe *v = self.video;
    [v setControlsShown:YES];
    [v.view layoutIfNeeded];
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
    LGReceiverPlayer *player = [LGReceiverPlayer new];
    player.seeks = [NSMutableArray array];
    player.fixtureItem = [[LGReceiverItem alloc] initWithURL:[NSBundle.mainBundle URLForResource:@"fixture" withExtension:@"mp4"]];
    v.airPlayPlayer = player; v.fixtureRoute = YES;
    v.airPlaySeekTarget = v.airPlayStartPosition = 12000;
    [v startAirPlayPlayback];
    [v updateTimeline];
    if (player.playCalls != 1 || !v.seek.enabled || !v.playRequested) { [self finish:@"Loading resume blocked playback or timeline"]; return; }
    [v seekAirPlay:18000];
    if (v.airPlaySeekTarget != 18000 || player.seeks.count) { [self finish:@"Loading seek was not queued"]; return; }
    player.fixtureItem.fixtureStatus = AVPlayerItemStatusReadyToPlay;
    [v updateAirPlay];
    [v seekAirPlay:9000];
    if (player.seeks.count != 2) { [self finish:@"Ready item did not accept updated seek"]; return; }
    ((void (^)(BOOL))player.seeks[0])(NO);
    dispatch_async(dispatch_get_main_queue(), ^{
        if (!v.airPlaySeekPending || v.airPlaySeekTarget != 9000) { [self finish:@"Obsolete completion erased newer seek"]; return; }
        ((void (^)(BOOL))player.seeks[1])(NO);
        dispatch_async(dispatch_get_main_queue(), ^{
            if (v.airPlaySeekPending || v.airPlaySeekTarget >= 0 || player.playCalls != 2) { [self finish:@"Interrupted seek left receiver stuck"]; return; }
            [v seekAirPlay:15000]; [v pause];
            ((void (^)(BOOL))player.seeks[2])(YES);
            dispatch_async(dispatch_get_main_queue(), ^{
                if (player.playCalls != 2 || v.playRequested) { [self finish:@"Seek completion undid explicit Pause"]; return; }
                [v startAirPlayPlayback]; [v seekAirPlay:17000];
                v.airPlaySeekDeadline = NSProcessInfo.processInfo.systemUptime - 1;
                [v updateAirPlay];
                if ([v hasAirPlay] || !v.localAudioNeedsRefresh || [v positionMilliseconds] != 17000) {
                    [self finish:@"Seek timeout failed to detach at requested position"]; return;
                }
                [self.samples addObject:@{@"event": @"receiver", @"loadingSeek": @YES, @"staleCompletion": @YES,
                    @"interruptedSeek": @YES, @"pausedSeek": @YES, @"timeout": @YES}];
                if ([self checkRemuxMetadata]) [self finish:nil];
            });
        });
    });
}
@end
int main(int argc, char **argv) { @autoreleasepool { return UIApplicationMain(argc, argv, nil, @"LGVideoAirPlayChecks"); } }
