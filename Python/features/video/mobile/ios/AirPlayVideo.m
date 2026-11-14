// AVKit owns playback, the AirPlay picker and the system remote commands.
@interface LGAirPlayVideoController : UIViewController <CXCallObserverDelegate>
@property(nonatomic, strong) NSURL *videoURL;
@property(nonatomic, copy) NSString *videoTitle;
@property(nonatomic, strong) AVPlayer *player;
@property(nonatomic, strong) AVPlayerViewController *playback;
@property(nonatomic, strong) LGScreenAwakeLease *awakeLease;
@property(nonatomic, strong) NSTimer *timer;
@property(nonatomic, strong) UILabel *message;
@property(nonatomic, strong) CXCallObserver *callObserver;
@property(nonatomic, copy) BOOL (^allowed)(void);
@property(nonatomic, copy) BOOL (^audioAvailable)(void);
@property(nonatomic, copy) BOOL (^requestPlay)(void);
@property(nonatomic, copy) dispatch_block_t closed;
@property(nonatomic, copy) dispatch_block_t fallback;
@property(nonatomic) int64_t startMilliseconds;
@property(nonatomic) NSUInteger seekGeneration;
@property(nonatomic) int64_t lastProgress;
@property(nonatomic) BOOL retired, hiddenForLock, ended, seeking, failed, playAfterSeek;
@end

static int64_t LGAirPlayMilliseconds(CMTime time) {
    double seconds = CMTimeGetSeconds(time);
    return isfinite(seconds) && seconds >= 0 && seconds <= 1e7 ? llround(seconds * 1000) : -1;
}

@implementation LGAirPlayVideoController
- (BOOL)canUseSource {
    return !self.retired && !self.hiddenForLock && self.allowed && self.allowed();
}

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.blackColor;
    self.lastProgress = -1;
    self.navigationItem.leftBarButtonItem = [[UIBarButtonItem alloc]
        initWithBarButtonSystemItem:UIBarButtonSystemItemDone target:self action:@selector(done:)];
    self.navigationItem.title = self.videoTitle ?: self.videoURL.lastPathComponent;
    if (self.fallback) {
        self.navigationItem.rightBarButtonItem = [[UIBarButtonItem alloc]
            initWithTitle:@"Use VLC" style:UIBarButtonItemStylePlain target:self action:@selector(useVLC:)];
    }
    AVURLAsset *asset = [AVURLAsset URLAssetWithURL:self.videoURL
        options:@{AVURLAssetReferenceRestrictionsKey: @(AVAssetReferenceRestrictionForbidAll)}];
    AVPlayerItem *item = [AVPlayerItem playerItemWithAsset:asset];
    self.player = [AVPlayer playerWithPlayerItem:item];
    self.player.allowsExternalPlayback = [self canUseSource];
    if (@available(iOS 15.0, *)) self.player.audiovisualBackgroundPlaybackPolicy = AVPlayerAudiovisualBackgroundPlaybackPolicyContinuesIfPossible;
    self.playback = [AVPlayerViewController new];
    self.playback.player = self.player;
    self.playback.allowsPictureInPicturePlayback = NO;
    [self addChildViewController:self.playback];
    UIView *surface = self.playback.view;
    surface.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:surface];
    [self.playback didMoveToParentViewController:self];

    self.message = [UILabel new];
    self.message.textColor = UIColor.whiteColor;
    self.message.textAlignment = NSTextAlignmentCenter;
    self.message.numberOfLines = 0;
    self.message.font = [UIFont preferredFontForTextStyle:UIFontTextStyleFootnote];
    self.message.adjustsFontForContentSizeCategory = YES;
    self.message.hidden = YES;
    self.message.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.message];
    UILayoutGuide *safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [surface.topAnchor constraintEqualToAnchor:safe.topAnchor],
        [surface.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [surface.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        [surface.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor],
        [self.message.topAnchor constraintEqualToAnchor:safe.topAnchor constant:8],
        [self.message.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:16],
        [self.message.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-16]
    ]];
    NSNotificationCenter *center = NSNotificationCenter.defaultCenter;
    [center addObserver:self selector:@selector(didEnd:) name:AVPlayerItemDidPlayToEndTimeNotification object:item];
    [center addObserver:self selector:@selector(didFail:) name:AVPlayerItemFailedToPlayToEndTimeNotification object:item];
    [center addObserver:self selector:@selector(backgroundNotification:) name:UIApplicationDidEnterBackgroundNotification object:nil];
    [center addObserver:self selector:@selector(protectedData:) name:UIApplicationProtectedDataWillBecomeUnavailable object:nil];
    self.callObserver = [CXCallObserver new];
    [self.callObserver setDelegate:self queue:dispatch_get_main_queue()];
    self.timer = [NSTimer scheduledTimerWithTimeInterval:.25 target:self selector:@selector(tick:) userInfo:nil repeats:YES];
}

- (void)done:(id)sender { if (self.closed) self.closed(); }
- (void)useVLC:(id)sender { if (self.fallback) self.fallback(); }

- (void)setAwake:(BOOL)awake {
    if (awake && !self.awakeLease) self.awakeLease = [LGScreenAwakeLease new];
    if (!awake) {
        [self.awakeLease finish];
        self.awakeLease = nil;
    }
}

- (void)pause {
    self.playAfterSeek = NO;
    [self.player pause];
    [self setAwake:NO];
}

- (void)background {
    [self setAwake:NO];
    if (!self.player.externalPlaybackActive) [self pause];
}

- (void)backgroundNotification:(NSNotification *)note { [self background]; }
- (void)protectedData:(NSNotification *)note { [self pause]; }
- (void)callObserver:(CXCallObserver *)observer callChanged:(CXCall *)call { [self pause]; }

- (BOOL)canPlayAudio {
    if (!self.audioAvailable || !self.audioAvailable()) return NO;
    for (CXCall *call in self.callObserver.calls) if (!call.hasEnded) return NO;
    return YES;
}

- (void)startByUser {
    if (![self canUseSource] || ![self canPlayAudio] || !self.requestPlay ||
        !self.requestPlay() || ![self canUseSource]) return;
    if (self.startMilliseconds > 0 || self.seeking) self.playAfterSeek = YES;
    else [self.player play];
}

- (void)seekToMilliseconds:(int64_t)position {
    if (![self canUseSource]) return;
    NSUInteger generation = ++self.seekGeneration;
    self.seeking = YES;
    __weak LGAirPlayVideoController *owner = self;
    [self.player seekToTime:CMTimeMake(MAX(0, position), 1000) toleranceBefore:kCMTimeZero
        toleranceAfter:kCMTimeZero completionHandler:^(BOOL finished) {
        dispatch_async(dispatch_get_main_queue(), ^{
            if (!owner || owner.retired || owner.seekGeneration != generation) return;
            owner.seeking = NO;
            if (finished && owner.playAfterSeek && [owner canUseSource] &&
                [owner canPlayAudio]) [owner.player play];
            owner.playAfterSeek = NO;
        });
    }];
}

- (int64_t)positionMilliseconds {
    if (self.ended) return 0;
    return MAX(0, LGAirPlayMilliseconds(self.player.currentTime));
}
- (int64_t)durationMilliseconds { return MAX(0, LGAirPlayMilliseconds(self.player.currentItem.duration)); }
- (int64_t)progressPosition {
    if (self.ended) return 0;
    if (self.failed) return self.lastProgress;
    if (self.startMilliseconds > 0 || self.seeking ||
        self.player.currentItem.status != AVPlayerItemStatusReadyToPlay) return -1;
    return LGAirPlayMilliseconds(self.player.currentTime);
}
- (BOOL)completed { return self.ended; }
- (BOOL)continuesAfterDisplayDisconnect { return NO; }
- (void)setNetworkWaiting:(BOOL)waiting {}
- (void)setTransportFailure:(NSString *)message {}

- (void)showStatus:(NSString *)message {
    self.message.text = message;
    self.message.backgroundColor = [UIColor colorWithWhite:0 alpha:.85];
    self.message.hidden = message.length == 0;
}

- (void)didEnd:(NSNotification *)note {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (!self.retired) self.ended = YES;
    });
}

- (void)playbackFailed {
    if (self.failed || self.retired) return;
    self.failed = YES;
    [self pause];
    [self showStatus:@"Apple’s player couldn’t play this video. Tap Use VLC to continue."];
}

- (void)didFail:(NSNotification *)note {
    dispatch_async(dispatch_get_main_queue(), ^{ [self playbackFailed]; });
}

- (void)tick:(NSTimer *)timer {
    if (![self canUseSource]) {
        [self suspendForLock];
        return;
    }
    if (self.player.status == AVPlayerStatusFailed || self.player.currentItem.status == AVPlayerItemStatusFailed) {
        [self playbackFailed];
        return;
    }
    if (![self canPlayAudio]) [self pause];
    if (self.startMilliseconds > 0 && self.player.currentItem.status == AVPlayerItemStatusReadyToPlay) {
        int64_t duration = [self durationMilliseconds];
        int64_t position = self.startMilliseconds;
        self.startMilliseconds = 0;
        [self seekToMilliseconds:duration > 0 ? MIN(position, duration - 1) : position];
    }
    BOOL playing = self.player.timeControlStatus != AVPlayerTimeControlStatusPaused;
    if (self.ended && playing) self.ended = NO;
    int64_t progress = [self progressPosition];
    if (progress >= 0) self.lastProgress = progress;
    [self setAwake:playing && !self.player.externalPlaybackActive && self.view.window &&
        UIApplication.sharedApplication.applicationState == UIApplicationStateActive];
}

- (void)suspendForLock {
    if (self.hiddenForLock) return;
    self.hiddenForLock = YES;
    [self pause];
    self.playback.view.hidden = YES;
    self.playback.player = nil;
    self.player.allowsExternalPlayback = NO;
    [self.player replaceCurrentItemWithPlayerItem:nil];
    [self showStatus:@"Video access changed. Close and reopen the video."];
}

- (void)revealSurface {}

- (void)retireWithCompletion:(dispatch_block_t)completion {
    self.retired = YES;
    [self.timer invalidate];
    self.timer = nil;
    [NSNotificationCenter.defaultCenter removeObserver:self];
    [self.callObserver setDelegate:nil queue:NULL];
    self.callObserver = nil;
    [self suspendForLock];
    self.allowed = nil;
    self.audioAvailable = nil;
    self.requestPlay = nil;
    self.closed = nil;
    self.fallback = nil;
    if (completion) completion();
}
@end
