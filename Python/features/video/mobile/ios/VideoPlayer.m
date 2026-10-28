// Logistics native video owner. VLCKit is linked by the mobile build manager.
#import <UIKit/UIKit.h>
#import <AVFoundation/AVFoundation.h>
#import <CallKit/CallKit.h>
#import <VLCKit/VLCKit.h>

@interface LGVideoController : UIViewController
    <VLCDrawable, VLCPictureInPictureDrawable, VLCPictureInPictureMediaControlling,
     VLCMediaPlayerDelegate, CXCallObserverDelegate>
@property(nonatomic, copy) NSString *videoURL;
@property(nonatomic, copy) NSString *subtitleJSON;
@property(nonatomic) int64_t startMilliseconds;
@property(nonatomic) BOOL restricted;
@property(nonatomic, copy) BOOL (^allowed)(BOOL external);
@property(nonatomic, copy) void (^closed)(void);
@property(nonatomic, strong) VLCMediaPlayer *player;
@property(nonatomic, strong) UIView *movie;
@property(nonatomic, strong) UIStackView *controls;
@property(nonatomic, strong) UILabel *message;
@property(nonatomic, strong) UISlider *seek;
@property(nonatomic, strong) UIButton *playButton;
@property(nonatomic, strong) NSTimer *timer;
@property(nonatomic, strong) id<VLCPictureInPictureWindowControlling> pipController;
@property(nonatomic, strong) NSMutableArray<VLCRendererDiscoverer *> *discoverers;
@property(nonatomic) BOOL pipActive;
@property(nonatomic) BOOL casting;
@property(nonatomic) BOOL retired;
@property(nonatomic) BOOL ended;
@property(nonatomic) BOOL lockHidden;
@property(nonatomic) BOOL interrupted;
@property(nonatomic) BOOL manualResumeRequired;
@property(nonatomic) BOOL pausePending;
@property(nonatomic) BOOL audioSuppressed;
@property(nonatomic) BOOL resumeMuted;
@property(nonatomic, strong) CXCallObserver *callObserver;
@property(nonatomic) int64_t lastPosition;
@end

@implementation LGVideoController
- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.blackColor;
    self.lastPosition = self.startMilliseconds;
    self.movie = [[UIView alloc] init];
    self.movie.backgroundColor = UIColor.blackColor;
    self.movie.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.movie];
    self.controls = [[UIStackView alloc] init];
    self.controls.axis = UILayoutConstraintAxisVertical;
    self.controls.spacing = 8;
    self.controls.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.controls];
    self.message = [[UILabel alloc] init];
    self.message.textColor = UIColor.whiteColor;
    self.message.numberOfLines = 2;
    self.message.text = @"Ready. Press Play to start.";
    [self.controls addArrangedSubview:self.message];
    self.seek = [[UISlider alloc] init];
    self.seek.accessibilityLabel = @"Video position";
    [self.seek addTarget:self action:@selector(seekChanged:) forControlEvents:UIControlEventTouchUpInside | UIControlEventTouchUpOutside];
    [self.controls addArrangedSubview:self.seek];
    UIStackView *buttons = [[UIStackView alloc] init];
    buttons.distribution = UIStackViewDistributionFillEqually;
    [self.controls addArrangedSubview:buttons];
    self.playButton = [self button:@"Play" selector:@selector(togglePlay:) row:buttons];
    [self button:@"−10s" selector:@selector(back:) row:buttons];
    [self button:@"+10s" selector:@selector(forward:) row:buttons];
    [self button:@"Tracks" selector:@selector(tracks:) row:buttons];
    [self button:@"Done" selector:@selector(done:) row:buttons];
    if (!self.restricted) {
        UIStackView *external = [[UIStackView alloc] init];
        external.distribution = UIStackViewDistributionFillEqually;
        [self.controls addArrangedSubview:external];
        [self button:@"Picture in picture" selector:@selector(pip:) row:external];
        [self button:@"Cast…" selector:@selector(cast:) row:external];
    }
    UILayoutGuide *safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [self.movie.topAnchor constraintEqualToAnchor:safe.topAnchor],
        [self.movie.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor],
        [self.movie.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor],
        [self.movie.bottomAnchor constraintEqualToAnchor:self.controls.topAnchor constant:-8],
        [self.controls.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:12],
        [self.controls.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-12],
        [self.controls.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor constant:-8]
    ]];
    self.player = [[VLCMediaPlayer alloc] initWithOptions:@[@"--quiet", @"--no-video-title-show", @"--no-stats"]];
    self.player.drawable = self;
    self.player.delegate = self;
    self.player.media = [VLCMedia mediaWithURL:[NSURL URLWithString:self.videoURL]];
    self.discoverers = [NSMutableArray array];
    self.timer = [NSTimer scheduledTimerWithTimeInterval:.5 target:self selector:@selector(tick:) userInfo:nil repeats:YES];
    NSNotificationCenter *center = NSNotificationCenter.defaultCenter;
    [center addObserver:self selector:@selector(backgroundNotification:) name:UIApplicationWillResignActiveNotification object:nil];
    [center addObserver:self selector:@selector(protectedData:) name:UIApplicationProtectedDataWillBecomeUnavailable object:nil];
    [center addObserver:self selector:@selector(captureChanged:) name:UIScreenCapturedDidChangeNotification object:nil];
    [center addObserver:self selector:@selector(audioInterrupted:) name:AVAudioSessionInterruptionNotification object:nil];
    [center addObserver:self selector:@selector(audioRouteChanged:) name:AVAudioSessionRouteChangeNotification object:nil];
    self.callObserver = [[CXCallObserver alloc] init];
    [self.callObserver setDelegate:self queue:dispatch_get_main_queue()];
}

- (UIButton *)button:(NSString *)title selector:(SEL)selector row:(UIStackView *)row {
    UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
    [button setTitle:title forState:UIControlStateNormal];
    [button addTarget:self action:selector forControlEvents:UIControlEventTouchUpInside];
    [button.heightAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;
    [row addArrangedSubview:button];
    return button;
}

- (BOOL)canPlay:(BOOL)external {
    if (self.retired || self.interrupted || [self hasActiveCall] || (external && self.restricted)) return NO;
    if (self.restricted && (self.lockHidden || UIApplication.sharedApplication.applicationState != UIApplicationStateActive)) return NO;
    if (!UIApplication.sharedApplication.protectedDataAvailable) return NO;
    if (self.restricted && (self.view.window.screen.isCaptured || [self hasExternalAudio])) return NO;
    return self.allowed && self.allowed(external);
}

- (void)togglePlay:(id)sender {
    if (![self canPlay:NO]) { [self pause]; return; }
    if (self.player.isPlaying) [self pause]; else [self startByUser];
}
- (void)back:(id)sender { if ([self canPlay:NO]) [self.player jumpBackward:10]; }
- (void)forward:(id)sender { if ([self canPlay:NO]) [self.player jumpForward:10]; }
- (void)seekChanged:(UISlider *)slider { if ([self canPlay:NO]) self.player.position = slider.value; }
- (void)done:(id)sender { if (self.closed) self.closed(); }
- (void)pause {
    // VLCKit pause is an explicit pause, but coalesce duplicate OS/lifecycle events.
    self.manualResumeRequired = YES;
    if (!self.audioSuppressed) {
        self.resumeMuted = self.player.audio.isMuted;
        self.audioSuppressed = YES;
    }
    self.player.audio.muted = YES; // Retain silence across any unsolicited decoder restart.
    if (self.player.isPlaying && !self.pausePending) {
        self.pausePending = YES;
        [self.player pause];
    }
    [self.pipController invalidatePlaybackState];
}
- (BOOL)hasExternalAudio {
    for (AVAudioSessionPortDescription *output in AVAudioSession.sharedInstance.currentRoute.outputs) {
        NSString *type = output.portType;
        if ([type isEqualToString:AVAudioSessionPortAirPlay] ||
            [type isEqualToString:AVAudioSessionPortHDMI] ||
            [type isEqualToString:AVAudioSessionPortDisplayPort]) return YES;
    }
    return NO;
}
- (BOOL)hasActiveCall {
    for (CXCall *call in self.callObserver.calls) if (!call.hasEnded) return YES;
    return NO;
}
- (void)startByUser {
    if (![self canPlay:NO]) return;
    NSError *error = nil;
    AVAudioSession *audio = AVAudioSession.sharedInstance;
    if (![audio setCategory:AVAudioSessionCategoryPlayback error:&error] ||
        ![audio setActive:YES error:&error]) return;
    self.manualResumeRequired = NO;
    self.pausePending = NO;
    if (self.audioSuppressed) { self.player.audio.muted = self.resumeMuted; self.audioSuppressed = NO; }
    [self.player play];
}
- (void)audioInterrupted:(NSNotification *)notification {
    NSUInteger type = [notification.userInfo[AVAudioSessionInterruptionTypeKey] unsignedIntegerValue];
    self.interrupted = type == AVAudioSessionInterruptionTypeBegan;
    [self pause]; // Ignore ShouldResume, including after an OS-initiated pause.
}
- (void)audioRouteChanged:(NSNotification *)notification {
    NSUInteger reason = [notification.userInfo[AVAudioSessionRouteChangeReasonKey] unsignedIntegerValue];
    if (reason == AVAudioSessionRouteChangeReasonOldDeviceUnavailable ||
        reason == AVAudioSessionRouteChangeReasonNoSuitableRouteForCategory ||
        (self.restricted && [self hasExternalAudio])) [self pause];
}
- (void)callObserver:(CXCallObserver *)observer callChanged:(CXCall *)call {
    [self pause]; // Ringing banners and Continuity calls need not background a scene.
}
- (void)suspendForLock {
    if (self.lockHidden) return;
    self.lockHidden = YES;
    [self pause];
    self.startMilliseconds = [self positionMilliseconds];
    self.movie.hidden = YES;
    [self.player stop];
    for (UIView *view in self.movie.subviews) [view removeFromSuperview];
}
- (void)revealSurface {
    // Only the authenticated Python presentation owner calls this entry point.
    self.lockHidden = NO;
    self.movie.hidden = self.restricted && self.view.window.screen.isCaptured;
}
- (void)background { if (self.restricted) [self suspendForLock]; else if (!self.pipActive && !self.casting) [self pause]; }
- (void)backgroundNotification:(NSNotification *)notification { [self background]; }
- (void)protectedData:(NSNotification *)notification { if (self.restricted) [self suspendForLock]; else [self pause]; }
- (void)captureChanged:(NSNotification *)notification {
    if (self.restricted && self.view.window.screen.isCaptured) {
        [self pause]; self.movie.hidden = YES;
    } else if (!self.lockHidden && [self canPlay:NO]) self.movie.hidden = NO;
}
- (int64_t)positionMilliseconds {
    if (self.ended) return 0;
    if (self.startMilliseconds > 0) return self.startMilliseconds;
    int64_t value = self.player.time.value.longLongValue;
    return value >= 0 ? value : self.lastPosition;
}
- (BOOL)completed { return self.ended; }
- (void)showStatus:(NSString *)message { self.message.text = message; }
- (void)tick:(NSTimer *)timer {
    if (![self canPlay:NO]) [self pause];
    int64_t position = [self positionMilliseconds];
    int64_t duration = self.player.media.length.value.longLongValue;
    if (!self.seek.tracking && duration > 0) self.seek.value = (float)position / duration;
    self.lastPosition = position;
    [self.playButton setTitle:self.player.isPlaying ? @"Pause" : @"Play" forState:UIControlStateNormal];
}
- (void)mediaPlayerStateChanged:(VLCMediaPlayerState)state {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (self.retired) return;
        if (state != VLCMediaPlayerStatePlaying) self.pausePending = NO;
        if (state == VLCMediaPlayerStatePlaying) {
            if (self.manualResumeRequired || ![self canPlay:NO]) { [self pause]; return; }
            if (self.startMilliseconds > 0) {
                self.player.time = [VLCTime timeWithNumber:@(self.startMilliseconds)];
                self.startMilliseconds = 0;
            }
            self.ended = NO;
        }
        if (state == VLCMediaPlayerStateStopped && self.player.position >= .999) self.ended = YES;
        if (state == VLCMediaPlayerStateError) [self showStatus:@"Playback failed. Close and reopen this video to retry."];
        [self.pipController invalidatePlaybackState];
    });
}
- (void)mediaPlayerLengthChanged:(int64_t)length { [self.pipController invalidatePlaybackState]; }

- (UIAlertController *)menu:(NSString *)title sender:(UIView *)sender {
    UIAlertController *menu = [UIAlertController alertControllerWithTitle:title message:nil preferredStyle:UIAlertControllerStyleActionSheet];
    menu.popoverPresentationController.sourceView = sender;
    menu.popoverPresentationController.sourceRect = sender.bounds;
    [menu addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    return menu;
}
- (void)tracks:(UIButton *)sender {
    if (![self canPlay:NO]) return;
    UIAlertController *menu = [self menu:@"Audio and subtitles" sender:sender];
    [menu addAction:[UIAlertAction actionWithTitle:@"Subtitles off" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        if ([self canPlay:NO]) [self.player deselectAllTextTracks];
    }]];
    NSArray *groups = @[self.player.audioTracks, self.player.textTracks];
    for (NSUInteger group = 0; group < groups.count; group++) {
        NSArray *tracks = groups[group];
        for (NSUInteger index = 0; index < tracks.count; index++) {
            NSString *label = [NSString stringWithFormat:@"%@: track %lu", group == 0 ? @"Audio" : @"Subtitle", (unsigned long)index + 1];
            [menu addAction:[UIAlertAction actionWithTitle:label style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
                if ([self canPlay:NO]) [self.player selectTrackAtIndex:index type:group == 0 ? VLCMediaTrackTypeAudio : VLCMediaTrackTypeText];
            }]];
        }
    }
    NSArray *subtitles = [NSJSONSerialization JSONObjectWithData:[self.subtitleJSON dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
    for (NSDictionary *subtitle in subtitles) {
        [menu addAction:[UIAlertAction actionWithTitle:subtitle[@"name"] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
            if ([self canPlay:NO]) [self.player addPlaybackSlave:[NSURL URLWithString:subtitle[@"url"]] type:VLCMediaPlaybackSlaveTypeSubtitle enforce:YES];
        }]];
    }
    [self presentViewController:menu animated:YES completion:nil];
}
- (void)cast:(UIButton *)sender {
    if (![self canPlay:YES]) return;
    if (self.discoverers.count == 0) {
        for (VLCRendererDiscovererDescription *description in [VLCRendererDiscoverer list]) {
            VLCRendererDiscoverer *discoverer = [[VLCRendererDiscoverer alloc] initWithName:description.name];
            if (discoverer) { [self.discoverers addObject:discoverer]; [discoverer start]; }
        }
    }
    UIAlertController *menu = [self menu:@"Cast video" sender:sender];
    [menu addAction:[UIAlertAction actionWithTitle:@"This device" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        [self selectRenderer:nil];
    }]];
    NSUInteger count = 0;
    for (VLCRendererDiscoverer *discoverer in self.discoverers) {
        for (VLCRendererItem *renderer in discoverer.renderers) {
            count++;
            [menu addAction:[UIAlertAction actionWithTitle:renderer.name style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
                [self selectRenderer:renderer];
            }]];
        }
    }
    if (count == 0) menu.message = @"Looking for receivers. Open Cast again in a few seconds.";
    [self presentViewController:menu animated:YES completion:nil];
}
- (void)selectRenderer:(VLCRendererItem *)renderer {
    if (![self canPlay:YES]) return;
    self.startMilliseconds = [self positionMilliseconds];
    [self.player stop];
    self.casting = [self.player setRendererItem:renderer] && renderer != nil;
    [self startByUser];
}
- (void)pip:(UIButton *)sender {
    if (![self canPlay:YES]) return;
    if (self.pipController) [self.pipController startPictureInPicture];
    else [self showStatus:@"Picture in picture is not ready. Start playback first."];
}
- (id<VLCPictureInPictureMediaControlling>)mediaController { return self; }
- (void (^)(id<VLCPictureInPictureWindowControlling>))pictureInPictureReady {
    __weak LGVideoController *owner = self;
    return ^(id<VLCPictureInPictureWindowControlling> controller) {
        if (owner.restricted) return;
        owner.pipController = controller;
        controller.stateChangeEventHandler = ^(BOOL active) { owner.pipActive = active; };
    };
}
- (void)addSubview:(UIView *)view { [self.movie addSubview:view]; }
- (CGRect)bounds { return self.movie.bounds; }
- (void)play { if ([self canPlay:YES]) [self startByUser]; }
- (void)seekBy:(int64_t)offset completion:(dispatch_block_t)completion {
    if ([self canPlay:YES]) [self.player jumpWithOffset:(int)offset completion:completion];
    else if (completion) completion();
}
- (int64_t)mediaLength { return self.player.media.length.value.longLongValue; }
- (int64_t)mediaTime { return [self positionMilliseconds]; }
- (BOOL)isMediaSeekable { return self.player.isSeekable; }
- (BOOL)isMediaPlaying { return self.player.isPlaying; }
- (void)retire {
    if (self.retired) return;
    self.retired = YES;
    [self.timer invalidate]; self.timer = nil;
    [NSNotificationCenter.defaultCenter removeObserver:self];
    [self.callObserver setDelegate:nil queue:NULL]; self.callObserver = nil;
    [self.pipController stopPictureInPicture]; self.pipController = nil;
    for (VLCRendererDiscoverer *discoverer in self.discoverers) [discoverer stop];
    [self.discoverers removeAllObjects];
    self.player.delegate = nil;
    [self.player stop]; self.player.drawable = nil;
    self.player = nil;
    self.allowed = nil; self.closed = nil;
}
@end
