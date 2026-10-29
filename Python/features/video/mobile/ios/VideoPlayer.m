// Logistics native video owner. VLCKit is linked by the mobile build manager.
#import <UIKit/UIKit.h>
#import <AVFoundation/AVFoundation.h>
#import <CallKit/CallKit.h>
#import <VLCKit/VLCKit.h>
#if __has_include(<UIKit/UIHingeInteraction.h>)
#import <UIKit/UIHingeInteraction.h>
#import <UIKit/UIViewReservedRegion.h>
#endif

// UIApplication's idle policy is shared by independent scene players.
static NSUInteger LGVideoAwakeOwners = 0;
static BOOL LGVideoPreviousIdleTimerDisabled = NO;

@interface LGVideoController : UIViewController
    <VLCDrawable, VLCPictureInPictureDrawable, VLCPictureInPictureMediaControlling,
     VLCMediaPlayerDelegate, CXCallObserverDelegate, UIGestureRecognizerDelegate>
@property(nonatomic, copy) NSString *videoURL;
@property(nonatomic, copy) NSString *subtitleJSON;
@property(nonatomic) int64_t startMilliseconds; // Deferred resume/paused seek; -1 means no pending seek.
@property(nonatomic) BOOL restricted;
@property(nonatomic, copy) BOOL (^allowed)(BOOL external);
@property(nonatomic, copy) BOOL (^requestPlay)(void);
@property(nonatomic, copy) void (^closed)(void);
@property(nonatomic, strong) VLCMediaPlayer *player;
@property(nonatomic, strong) UIView *movie;
@property(nonatomic, strong) UIStackView *controls;
@property(nonatomic, strong) UIScrollView *controlsScroll;
@property(nonatomic, strong) UIStackView *buttonGroups;
@property(nonatomic, strong) UILabel *timeLabel;
@property(nonatomic, strong) NSLayoutConstraint *controlsLeading, *controlsTrailing, *controlsTop, *controlsBottom;
@property(nonatomic, strong) UILabel *message;
@property(nonatomic, strong) UISlider *seek;
@property(nonatomic, strong) UIButton *playButton;
@property(nonatomic, strong) UIButton *fullscreenButton;
@property(nonatomic) BOOL fullscreen;
@property(nonatomic) BOOL controlsVisible;
@property(nonatomic, strong) NSTimer *controlsTimer;
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
@property(nonatomic) BOOL holdsIdleTimer;
@property(nonatomic) BOOL surfaceVisible;
@property(nonatomic, strong) CXCallObserver *callObserver;
@property(nonatomic) int64_t lastPosition;
@end

@implementation LGVideoController
- (void)setScreenAwake:(BOOL)awake {
    if (self.holdsIdleTimer == awake) return;
    self.holdsIdleTimer = awake;
    UIApplication *application = UIApplication.sharedApplication;
    if (awake) {
        if (LGVideoAwakeOwners++ == 0) LGVideoPreviousIdleTimerDisabled = application.idleTimerDisabled;
        application.idleTimerDisabled = YES;
    } else if (--LGVideoAwakeOwners == 0) {
        application.idleTimerDisabled = LGVideoPreviousIdleTimerDisabled;
    }
}
- (void)updateScreenAwake {
    [self setScreenAwake:!self.retired && self.surfaceVisible && self.view.window &&
        !self.lockHidden && !self.manualResumeRequired && !self.pausePending &&
        !self.ended && !self.casting && !self.pipActive && self.player.isPlaying &&
        self.player.state == VLCMediaPlayerStatePlaying &&
        UIApplication.sharedApplication.applicationState == UIApplicationStateActive];
}
- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.blackColor;
    self.lastPosition = self.startMilliseconds;
    self.movie = [[UIView alloc] init];
    self.movie.backgroundColor = UIColor.blackColor;
    self.movie.isAccessibilityElement = YES;
    self.movie.accessibilityLabel = @"Video";
    self.movie.accessibilityCustomActions = @[
        [[UIAccessibilityCustomAction alloc] initWithName:@"Show video controls" target:self selector:@selector(showControlsForAccessibility)]
    ];
    self.movie.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.movie];
    self.controls = [[UIStackView alloc] init];
    self.controls.axis = UILayoutConstraintAxisVertical;
    self.controls.spacing = 8;
    self.controls.backgroundColor = [UIColor colorWithWhite:0 alpha:.8];
    self.controlsVisible = YES;
    self.controls.translatesAutoresizingMaskIntoConstraints = NO;
    self.controlsScroll = [[UIScrollView alloc] init];
    self.controlsScroll.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.controlsScroll];
    [self.controlsScroll addSubview:self.controls];
    self.message = [[UILabel alloc] init];
    self.message.textColor = UIColor.whiteColor;
    self.message.font = [UIFont preferredFontForTextStyle:UIFontTextStyleCaption1];
    self.message.adjustsFontForContentSizeCategory = YES;
    self.message.numberOfLines = 2;
    self.message.text = @"Ready. Press Play to start.";
    [self.controls addArrangedSubview:self.message];
    self.timeLabel = [[UILabel alloc] init];
    self.timeLabel.textColor = UIColor.whiteColor;
    self.timeLabel.font = [UIFont monospacedDigitSystemFontOfSize:13 weight:UIFontWeightRegular];
    self.timeLabel.adjustsFontSizeToFitWidth = YES;
    self.timeLabel.text = @"0:00 / 0:00";
    self.timeLabel.accessibilityLabel = @"Playback time";
    [self.controls addArrangedSubview:self.timeLabel];
    self.seek = [[UISlider alloc] init];
    self.seek.minimumTrackTintColor = UIColor.whiteColor;
    self.seek.maximumTrackTintColor = [UIColor colorWithWhite:.65 alpha:1];
    self.seek.thumbTintColor = UIColor.whiteColor;
    self.seek.accessibilityLabel = @"Video position";
    [self.seek.heightAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;
    [self.seek addTarget:self action:@selector(seekChanged:) forControlEvents:UIControlEventTouchUpInside | UIControlEventTouchUpOutside];
    [self.controls addArrangedSubview:self.seek];
    UIStackView *buttons = [[UIStackView alloc] init];
    buttons.distribution = UIStackViewDistributionFillEqually;
    buttons.spacing = 8;
    self.buttonGroups = [[UIStackView alloc] init];
    self.buttonGroups.axis = UILayoutConstraintAxisVertical;
    self.buttonGroups.spacing = 8;
    self.buttonGroups.distribution = UIStackViewDistributionFillProportionally;
    [self.controls addArrangedSubview:self.buttonGroups];
    [self.buttonGroups addArrangedSubview:buttons];
    [self button:@"Back 10 seconds" selector:@selector(back:) row:buttons];
    self.playButton = [self button:@"Play" selector:@selector(togglePlay:) row:buttons];
    [self button:@"Forward 10 seconds" selector:@selector(forward:) row:buttons];
    UIStackView *display = [[UIStackView alloc] init];
    display.distribution = UIStackViewDistributionFillEqually;
    display.spacing = 8;
    [self.buttonGroups addArrangedSubview:display];
    [self button:@"Audio and subtitles" selector:@selector(tracks:) row:display];
    self.fullscreenButton = [self button:@"Fullscreen" selector:@selector(toggleFullscreen:) row:display];
    if (!self.restricted) {
        UIButton *more = [self button:@"More playback options" selector:NULL row:display];
        __weak LGVideoController *owner = self;
        __weak UIButton *anchor = more;
        more.menu = [UIMenu menuWithChildren:@[
            [UIAction actionWithTitle:@"Picture in picture" image:[UIImage systemImageNamed:@"pip"] identifier:nil handler:^(UIAction *action) { [owner pip:anchor]; }],
            [UIAction actionWithTitle:@"Cast…" image:[UIImage systemImageNamed:@"tv"] identifier:nil handler:^(UIAction *action) { [owner cast:anchor]; }]
        ]];
        more.showsMenuAsPrimaryAction = YES;
    }
    [self button:@"Done" selector:@selector(done:) row:display];
    UILayoutGuide *safe = self.view.safeAreaLayoutGuide;
    NSLayoutConstraint *naturalHeight = [self.controlsScroll.heightAnchor constraintEqualToAnchor:self.controls.heightAnchor];
    naturalHeight.priority = UILayoutPriorityDefaultHigh;
    self.controlsLeading = [self.controlsScroll.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:12];
    self.controlsTrailing = [self.controlsScroll.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-12];
    self.controlsBottom = [self.controlsScroll.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor constant:-8];
    self.controlsTop = [self.controlsScroll.topAnchor constraintGreaterThanOrEqualToAnchor:safe.topAnchor constant:8];
    [NSLayoutConstraint activateConstraints:@[
        [self.movie.topAnchor constraintEqualToAnchor:self.view.topAnchor],
        [self.movie.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [self.movie.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        [self.movie.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor],
        self.controlsLeading, self.controlsTrailing, self.controlsBottom, self.controlsTop,
        naturalHeight,
        [self.controls.leadingAnchor constraintEqualToAnchor:self.controlsScroll.contentLayoutGuide.leadingAnchor],
        [self.controls.trailingAnchor constraintEqualToAnchor:self.controlsScroll.contentLayoutGuide.trailingAnchor],
        [self.controls.topAnchor constraintEqualToAnchor:self.controlsScroll.contentLayoutGuide.topAnchor],
        [self.controls.bottomAnchor constraintEqualToAnchor:self.controlsScroll.contentLayoutGuide.bottomAnchor],
        [self.controls.widthAnchor constraintEqualToAnchor:self.controlsScroll.frameLayoutGuide.widthAnchor]
    ]];
    UITapGestureRecognizer *tap = [[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(tapVideo:)];
    tap.delegate = self;
    [self.view addGestureRecognizer:tap];
#if __has_include(<UIKit/UIHingeInteraction.h>)
    if (@available(iOS 27.1, *)) {
        __weak LGVideoController *owner = self;
        [self.view addInteraction:[[UIHingeInteraction alloc] initWithUpdateHandler:^(UIHingeInteraction *interaction, UIHingeInteractionUpdate *update) {
            [owner.view setNeedsLayout];
        }]];
    }
#endif
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

- (BOOL)prefersStatusBarHidden { return self.fullscreen && !self.controlsVisible && !self.pipActive; }
- (BOOL)prefersHomeIndicatorAutoHidden { return self.fullscreen && !self.controlsVisible && !self.pipActive; }
- (UIRectEdge)preferredScreenEdgesDeferringSystemGestures {
    return self.fullscreen && !self.controlsVisible && !self.pipActive ? UIRectEdgeAll : UIRectEdgeNone;
}
- (BOOL)gestureRecognizer:(UIGestureRecognizer *)gesture shouldReceiveTouch:(UITouch *)touch {
    return ![touch.view isDescendantOfView:self.controlsScroll];
}
- (void)setControlsShown:(BOOL)visible {
    self.controlsVisible = visible;
    self.controls.hidden = !visible || self.pipActive;
    self.controlsScroll.hidden = self.controls.hidden;
    [self setNeedsStatusBarAppearanceUpdate];
    [self setNeedsUpdateOfHomeIndicatorAutoHidden];
    [self setNeedsUpdateOfScreenEdgesDeferringSystemGestures];
    [self scheduleControls];
}
- (void)scheduleControls {
    [self.controlsTimer invalidate]; self.controlsTimer = nil;
    if (self.fullscreen && self.controlsVisible && !self.pipActive && !self.retired && self.view.window && self.player.isPlaying) {
        self.controlsTimer = [NSTimer scheduledTimerWithTimeInterval:3 target:self selector:@selector(hideControls:) userInfo:nil repeats:NO];
    }
}
- (void)hideControls:(NSTimer *)timer {
    if (self.player.isPlaying && !self.seek.tracking && !self.presentedViewController && !UIAccessibilityIsVoiceOverRunning())
        [self setControlsShown:NO];
    else [self scheduleControls];
}
- (void)toggleFullscreen:(id)sender {
    self.fullscreen = !self.fullscreen;
    [self updateButton:self.fullscreenButton label:self.fullscreen ? @"Exit fullscreen" : @"Fullscreen"];
    [self setControlsShown:!self.fullscreen];
}
- (void)tapVideo:(id)sender {
    if (!self.fullscreen) [self toggleFullscreen:sender];
    else [self setControlsShown:!self.controlsVisible];
}
- (BOOL)showControlsForAccessibility { [self setControlsShown:YES]; return YES; }
- (void)viewWillDisappear:(BOOL)animated {
    [super viewWillDisappear:animated];
    self.surfaceVisible = NO;
    [self setScreenAwake:NO];
    [self.controlsTimer invalidate]; self.controlsTimer = nil;
}
- (void)viewDidAppear:(BOOL)animated {
    [super viewDidAppear:animated];
    self.surfaceVisible = YES;
    [self updateScreenAwake];
    [self setControlsShown:YES];
}
- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    CGRect safe = self.view.safeAreaLayoutGuide.layoutFrame;
    CGRect available = safe;
#if __has_include(<UIKit/UIHingeInteraction.h>)
    if (@available(iOS 27.1, *)) {
        for (UIViewReservedRegion *region in [self.view reservedRegionsOfKind:UIViewReservedRegionKind.divisionRegionKind]) {
            CGRect fold = CGRectIntersection(available, region.frame);
            if (CGRectIsNull(fold) || CGRectIsEmpty(fold)) continue;
            if (fold.size.height > fold.size.width) {
                CGFloat left = CGRectGetMinX(fold) - CGRectGetMinX(available);
                CGFloat right = CGRectGetMaxX(available) - CGRectGetMaxX(fold);
                if (right >= left) { available.origin.x = CGRectGetMaxX(fold); available.size.width = right; }
                else available.size.width = left;
            } else {
                CGFloat bottom = CGRectGetMaxY(available) - CGRectGetMaxY(fold);
                // A partially folded device keeps transport buttons below the crease.
                if (bottom >= 112) { available.origin.y = CGRectGetMaxY(fold); available.size.height = bottom; }
                else available.size.height = CGRectGetMinY(fold) - CGRectGetMinY(available);
            }
        }
    }
#endif
    self.controlsLeading.constant = 12 + CGRectGetMinX(available) - CGRectGetMinX(safe);
    self.controlsTrailing.constant = -12 + CGRectGetMaxX(available) - CGRectGetMaxX(safe);
    self.controlsTop.constant = 8 + CGRectGetMinY(available) - CGRectGetMinY(safe);
    self.controlsBottom.constant = -8 + CGRectGetMaxY(available) - CGRectGetMaxY(safe);
    CGFloat width = available.size.width - 24;
    // Adapt to the actual window, including outer display and system Split View.
    UILayoutConstraintAxis axis = width >= 500 ? UILayoutConstraintAxisHorizontal : UILayoutConstraintAxisVertical;
    if (self.buttonGroups.axis != axis) self.buttonGroups.axis = axis;
}

- (void)updateButton:(UIButton *)button label:(NSString *)label {
    NSDictionary *symbols = @{@"Play": @"play.fill", @"Pause": @"pause.fill",
        @"Back 10 seconds": @"gobackward.10", @"Forward 10 seconds": @"goforward.10",
        @"Audio and subtitles": @"captions.bubble", @"Fullscreen": @"arrow.up.left.and.arrow.down.right",
        @"Exit fullscreen": @"arrow.down.right.and.arrow.up.left", @"More playback options": @"ellipsis",
        @"Done": @"xmark"};
    [button setImage:[UIImage systemImageNamed:symbols[label]] forState:UIControlStateNormal];
    button.accessibilityLabel = label;
    button.accessibilityIdentifier = [@"video." stringByAppendingString:label];
    button.accessibilityHint = [label isEqualToString:@"Done"] ? @"Close video player" : nil;
}

- (UIButton *)button:(NSString *)title selector:(SEL)selector row:(UIStackView *)row {
    UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
    [self updateButton:button label:title];
    button.tintColor = UIColor.whiteColor;
    button.backgroundColor = [UIColor colorWithWhite:1 alpha:.15];
    button.layer.cornerRadius = 8;
    if (selector) [button addTarget:self action:selector forControlEvents:UIControlEventTouchUpInside];
    [button addTarget:self action:@selector(scheduleControls) forControlEvents:UIControlEventTouchUpInside];
    [button.heightAnchor constraintGreaterThanOrEqualToConstant:48].active = YES;
    [button.widthAnchor constraintGreaterThanOrEqualToConstant:48].active = YES;
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
    if (self.player.isPlaying) [self pause]; else [self startByUser];
}
- (void)seekToMilliseconds:(int64_t)target {
    if (![self canPlay:NO] || !self.player.isSeekable) return;
    int64_t duration = self.player.media.length.value.longLongValue;
    target = MAX(0, target);
    if (duration > 0) target = MIN(target, MAX(0, duration - 1));
    // VLC may retain the old reported clock while paused. Preserve the requested
    // position for controls/checkpoints and apply it again on explicit Play.
    self.ended = NO;
    self.startMilliseconds = self.player.isPlaying ? -1 : target;
    self.player.time = [VLCTime timeWithNumber:@(target)];
}
- (void)skipMilliseconds:(int64_t)offset { [self seekToMilliseconds:[self positionMilliseconds] + offset]; }
- (void)back:(id)sender { [self skipMilliseconds:-10000]; }
- (void)forward:(id)sender { [self skipMilliseconds:10000]; }
- (void)seekChanged:(UISlider *)slider {
    int64_t duration = self.player.media.length.value.longLongValue;
    if (duration <= 0) return;
    [self seekToMilliseconds:(int64_t)(slider.value * duration)];
    [self scheduleControls];
}
- (void)done:(id)sender { if (self.closed) self.closed(); }
- (void)pause {
    [self setScreenAwake:NO];
    [self setControlsShown:YES];
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
    if (!self.requestPlay || !self.requestPlay() || ![self canPlay:NO]) return;
    NSError *error = nil;
    AVAudioSession *audio = AVAudioSession.sharedInstance;
    if (![audio setCategory:AVAudioSessionCategoryPlayback error:&error] ||
        ![audio setActive:YES error:&error]) return;
    if (![self canPlay:NO]) return; // Activation can change the selected output.
    self.manualResumeRequired = NO;
    self.pausePending = NO;
    if (self.audioSuppressed) { self.player.audio.muted = self.resumeMuted; self.audioSuppressed = NO; }
    [self.player play];
    if ([self.message.text isEqualToString:@"Ready. Press Play to start."]) {
        self.message.text = @"";
        self.message.hidden = YES;
    }
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
- (void)background {
    [self setScreenAwake:NO];
    if (self.restricted) [self suspendForLock]; else if (!self.pipActive && !self.casting) [self pause];
}
- (void)backgroundNotification:(NSNotification *)notification { [self background]; }
- (void)protectedData:(NSNotification *)notification { if (self.restricted) [self suspendForLock]; else [self pause]; }
- (void)captureChanged:(NSNotification *)notification {
    if (self.restricted && self.view.window.screen.isCaptured) {
        [self pause]; self.movie.hidden = YES;
    } else if (!self.lockHidden && [self canPlay:NO]) self.movie.hidden = NO;
}
- (int64_t)positionMilliseconds {
    if (self.ended) return 0;
    if (self.startMilliseconds >= 0) return self.startMilliseconds;
    int64_t value = self.player.time.value.longLongValue;
    return value >= 0 ? value : self.lastPosition;
}
- (BOOL)completed { return self.ended; }
- (void)showStatus:(NSString *)message {
    self.message.text = message;
    self.message.hidden = message.length == 0;
    [self setControlsShown:YES];
}
- (void)tick:(NSTimer *)timer {
    if (![self canPlay:NO]) [self pause];
    [self updateScreenAwake];
    int64_t position = [self positionMilliseconds];
    int64_t duration = self.player.media.length.value.longLongValue;
    if (!self.seek.tracking && duration > 0) self.seek.value = (float)position / duration;
    NSString *(^time)(int64_t) = ^NSString *(int64_t value) {
        int64_t seconds = MAX(0, value / 1000);
        return [NSString stringWithFormat:@"%lld:%02lld:%02lld", seconds / 3600, seconds / 60 % 60, seconds % 60];
    };
    self.timeLabel.text = [NSString stringWithFormat:@"%@ / %@", time(position), time(duration)];
    self.timeLabel.accessibilityValue = self.timeLabel.text;
    self.seek.accessibilityValue = self.timeLabel.text;
    self.lastPosition = position;
    [self updateButton:self.playButton label:self.player.isPlaying ? @"Pause" : @"Play"];
}
- (void)mediaPlayerStateChanged:(VLCMediaPlayerState)state {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (self.retired) return;
        if (state != VLCMediaPlayerStatePlaying) self.pausePending = NO;
        if (state == VLCMediaPlayerStatePlaying) {
            if (self.manualResumeRequired || ![self canPlay:NO]) { [self pause]; return; }
            if (self.startMilliseconds >= 0) {
                self.player.time = [VLCTime timeWithNumber:@(self.startMilliseconds)];
                self.startMilliseconds = -1;
            }
            self.ended = NO;
            [self scheduleControls];
        }
        if (state == VLCMediaPlayerStateStopped && self.player.position >= .999) {
            self.ended = YES;
            [self setControlsShown:YES];
        }
        if (state == VLCMediaPlayerStateError) [self showStatus:@"Playback failed. Close and reopen this video to retry."];
        if (state == VLCMediaPlayerStatePlaying) [self updateScreenAwake];
        else [self setScreenAwake:NO];
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
    [self updateScreenAwake];
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
        controller.stateChangeEventHandler = ^(BOOL active) {
            owner.pipActive = active;
            [owner updateScreenAwake];
            [owner setControlsShown:YES];
        };
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
    [self setScreenAwake:NO];
    self.retired = YES;
    self.fullscreen = NO;
    [self setControlsShown:YES];
    [self.timer invalidate]; self.timer = nil;
    [NSNotificationCenter.defaultCenter removeObserver:self];
    [self.callObserver setDelegate:nil queue:NULL]; self.callObserver = nil;
    [self.pipController stopPictureInPicture]; self.pipController = nil;
    for (VLCRendererDiscoverer *discoverer in self.discoverers) [discoverer stop];
    [self.discoverers removeAllObjects];
    self.player.delegate = nil;
    [self.player stop]; self.player.drawable = nil;
    self.player = nil;
    self.allowed = nil; self.requestPlay = nil; self.closed = nil;
}
@end
