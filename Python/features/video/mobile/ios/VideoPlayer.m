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

// The real navigation container owns adaptive system bar placement. Forward
// immersive preferences to the video owner instead of drawing a private rail.
@interface LGVideoNavigationController : UINavigationController
@end
@implementation LGVideoNavigationController
- (UIViewController *)childViewControllerForStatusBarHidden { return self.topViewController; }
- (UIViewController *)childViewControllerForHomeIndicatorAutoHidden { return self.topViewController; }
- (UIViewController *)childViewControllerForScreenEdgesDeferringSystemGestures { return self.topViewController; }
- (UIInterfaceOrientationMask)supportedInterfaceOrientations { return self.topViewController.supportedInterfaceOrientations; }
- (BOOL)shouldAutorotate { return self.topViewController.shouldAutorotate; }
@end

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
@property(nonatomic, strong) UIActivityIndicatorView *bufferSpinner;
@property(nonatomic, strong) UILabel *bufferLabel;
@property(nonatomic, strong) UIStackView *bufferOverlay;
@property(nonatomic) BOOL buffering, hasPlayed;
@property(nonatomic, copy) NSString *transportFailure;
@property(nonatomic) BOOL hingePartiallyOpen, tabletop;
@property(nonatomic, strong) UIStackView *tabletopTransport, *tabletopUtilities;
@property(nonatomic, strong) UIButton *tabletopPlay;
@property(nonatomic, strong) NSLayoutConstraint *movieBottom, *deckCenterY, *controlsHeightLimit;

@property(nonatomic) BOOL networkWaiting, networkResumePending, playRequested;
@property(nonatomic) int64_t bufferPosition;
@property(nonatomic) int64_t observedClock, lastRenderedClock;
@property(nonatomic) uint64_t observedFrames;
@property(nonatomic) NSTimeInterval lastPlaybackProgress, lastFrameProgress;
@property(nonatomic, strong) NSLayoutConstraint *bufferCenterX, *bufferCenterY;
@property(nonatomic, strong) NSArray<UIBarButtonItem *> *mediaItems;
@property(nonatomic, strong) UILabel *timeLabel;
@property(nonatomic, strong) NSLayoutConstraint *controlsLeading, *controlsTrailing, *controlsTop, *controlsBottom;
@property(nonatomic, strong) UILabel *message;
@property(nonatomic, strong) UISlider *seek;
@property(nonatomic, strong) UIBarButtonItem *playButton;
@property(nonatomic, strong) UIBarButtonItem *fullscreenButton;
@property(nonatomic) BOOL fullscreen;
@property(nonatomic) BOOL controlsVisible;
@property(nonatomic) BOOL systemChromeHidden;
@property(nonatomic, strong) UIStackView *videoHeader;
@property(nonatomic, strong) UILabel *videoTitle, *sourceLabel;
@property(nonatomic, strong) UIImageView *sourceIcon;
@property(nonatomic) NSUInteger chromeGeneration;
@property(nonatomic, strong) NSTimer *controlsTimer;
@property(nonatomic, strong) NSTimer *timer;
@property(nonatomic, strong) id<VLCPictureInPictureWindowControlling> pipController;
@property(nonatomic, strong) NSMutableArray<VLCRendererDiscoverer *> *discoverers;
@property(nonatomic) BOOL pipActive;
@property(nonatomic) BOOL casting;
@property(nonatomic) BOOL retired;
@property(nonatomic) BOOL retirementComplete;
@property(nonatomic, strong) NSMutableArray *retirementCallbacks;
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
@property(nonatomic, copy) NSString *optionsJSON, *queueJSON, *pictureGeometry;
@property(nonatomic, copy) void (^command)(NSString *, NSString *);
@property(nonatomic) int64_t undoMilliseconds;
@property(nonatomic) NSTimeInterval undoUntil;
@property(nonatomic) BOOL controlsLocked, cacheApproximate;
@property(nonatomic, strong) UIButton *unlockButton, *undoSeekButton;
@property(nonatomic, strong) UIView *cacheStrip, *pauseSnapshot;
@property(nonatomic, copy) NSString *languageSignature;
@end

@interface LGVideoController (PlaybackControls)
- (void)installPlaybackTools;
- (void)applyPlaybackOptions;
- (void)applyPictureSize;
- (NSDictionary *)playbackOptions;
- (void)emitCommand:(NSString *)name value:(NSString *)value;
- (void)playbackTools:(id)sender;
@end

@interface LGVideoController (PausePresentation)
- (void)holdPausePresentation;
- (void)clearPausePresentation;
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
        !self.ended && !self.casting && !self.pipActive && self.playRequested &&
        UIApplication.sharedApplication.applicationState == UIApplicationStateActive];
}
- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.blackColor;
    self.edgesForExtendedLayout = UIRectEdgeAll;
    self.extendedLayoutIncludesOpaqueBars = YES;
    self.navigationItem.largeTitleDisplayMode = UINavigationItemLargeTitleDisplayModeNever;
    self.lastPosition = self.startMilliseconds;
    self.observedClock = -1;
    self.lastPlaybackProgress = self.lastFrameProgress = NSProcessInfo.processInfo.systemUptime;
    self.movie = [[UIView alloc] init];
    self.movie.backgroundColor = UIColor.blackColor;
    self.movie.clipsToBounds = YES;
    // VLC installs rendering subviews after presentation. Keep them out of hit
    // testing so the controller tap recognizer always receives video touches.
    self.movie.userInteractionEnabled = NO;
    self.movie.isAccessibilityElement = YES;
    self.movie.accessibilityLabel = @"Video";
    self.movie.accessibilityCustomActions = @[
        [[UIAccessibilityCustomAction alloc] initWithName:@"Show video controls" target:self selector:@selector(showControlsForAccessibility)]
    ];
    self.movie.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.movie];
    self.controls = [[UIStackView alloc] init];
    self.controls.insetsLayoutMarginsFromSafeArea = NO;
    self.controls.axis = UILayoutConstraintAxisVertical;
    self.controls.spacing = 4;
    self.controlsVisible = YES;
    self.fullscreen = YES;
    self.controls.translatesAutoresizingMaskIntoConstraints = NO;
    self.controlsScroll = [[UIScrollView alloc] init];
    // Constraints already handle safe regions; automatic scroll insets would
    // reserve the native rail twice and push the deck off center.
    self.controlsScroll.contentInsetAdjustmentBehavior = UIScrollViewContentInsetAdjustmentNever;
    self.controlsScroll.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.controlsScroll];
    [self.controlsScroll addSubview:self.controls];
    self.message = [[UILabel alloc] init];
    self.message.textColor = UIColor.whiteColor;
    self.message.font = [UIFont preferredFontForTextStyle:UIFontTextStyleCaption1];
    self.message.adjustsFontForContentSizeCategory = YES;
    self.message.numberOfLines = 2;
    self.message.text = @"";
    self.message.hidden = YES;
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
    NSNumber *seekExtent = [self playbackOptions][@"reader_layout"][@"extent"];
    [self.seek.heightAnchor constraintGreaterThanOrEqualToConstant:seekExtent ? seekExtent.doubleValue : 48].active = YES;
    [self.seek addTarget:self action:@selector(seekChanged:) forControlEvents:UIControlEventTouchUpInside | UIControlEventTouchUpOutside];
    [self.controls addArrangedSubview:self.seek];
    UIBarButtonItem *close = [self item:@"Done" selector:@selector(done:)];
    UIBarButtonItem *back = [self item:@"Back 10 seconds" selector:@selector(back:)];
    self.playButton = [self item:@"Play" selector:@selector(togglePlay:)];
    UIBarButtonItem *forward = [self item:@"Forward 10 seconds" selector:@selector(forward:)];
    UIBarButtonItem *chapters = [self item:@"Chapters" selector:@selector(chapters:)];
    UIBarButtonItem *audio = [self item:@"Audio tracks" selector:@selector(audioTracks:)];
    UIBarButtonItem *subtitles = [self item:@"Subtitles" selector:@selector(subtitleTracks:)];
    self.fullscreenButton = [self item:@"Exit fullscreen" selector:@selector(toggleFullscreen:)];
    UIBarButtonItem *tools = [self item:@"Playback" selector:@selector(playbackTools:)];
    NSMutableArray<UIBarButtonItem *> *utilities = [NSMutableArray arrayWithArray:@[audio, subtitles, chapters, self.fullscreenButton, tools]];
    if (!self.restricted) {
        UIBarButtonItem *more = [self item:@"More playback options" selector:NULL];
        __weak LGVideoController *owner = self;
        __weak UIBarButtonItem *anchor = more;
        more.menu = [UIMenu menuWithChildren:@[
            [UIAction actionWithTitle:@"Show in folder" image:[UIImage systemImageNamed:@"folder"] identifier:nil handler:^(UIAction *action) { [owner emitCommand:@"showInFolder" value:@""]; }],
            [UIAction actionWithTitle:@"Picture in picture" image:[UIImage systemImageNamed:@"pip"] identifier:nil handler:^(UIAction *action) { [owner pip:anchor]; }],
            [UIAction actionWithTitle:@"Cast…" image:[UIImage systemImageNamed:@"tv"] identifier:nil handler:^(UIAction *action) { [owner cast:anchor]; }]
        ]];
        [utilities addObject:more];
    }
    self.mediaItems = [@[close, back, self.playButton, forward] arrayByAddingObjectsFromArray:utilities];
    if (@available(iOS 16.0, *)) {
        self.navigationItem.leadingItemGroups = @[[[UIBarButtonItemGroup alloc] initWithBarButtonItems:@[close] representativeItem:nil]];
        // Center groups can move wholesale into overflow on compact bars.
        // Keep Play pinned and expose skips as ordinary native trailing items.
        self.navigationItem.pinnedTrailingGroup = [[UIBarButtonItemGroup alloc] initWithBarButtonItems:@[self.playButton] representativeItem:nil];
        self.navigationItem.trailingItemGroups = @[
            [[UIBarButtonItemGroup alloc] initWithBarButtonItems:@[back, forward] representativeItem:nil],
            [[UIBarButtonItemGroup alloc] initWithBarButtonItems:@[tools, audio, subtitles, chapters, self.fullscreenButton] representativeItem:nil]
        ];
        if (!self.restricted) {
            UIMenu *externalMenu = utilities.lastObject.menu;
            self.navigationItem.additionalOverflowItems = [UIDeferredMenuElement elementWithUncachedProvider:^(void (^completion)(NSArray<UIMenuElement *> *)) {
                completion(externalMenu.children);
            }];
        }
    } else {
        self.navigationItem.leftBarButtonItem = close;
        self.navigationItem.rightBarButtonItems = [@[forward, self.playButton, back] arrayByAddingObjectsFromArray:utilities];
    }
    self.tabletopTransport = [[UIStackView alloc] init];
    self.tabletopTransport.axis = UILayoutConstraintAxisHorizontal;
    self.tabletopTransport.alignment = UIStackViewAlignmentCenter;
    self.tabletopTransport.distribution = UIStackViewDistributionEqualCentering;
    self.tabletopTransport.spacing = 28;
    [self.tabletopTransport addArrangedSubview:[self deckButton:@"Back 10 seconds" symbol:@"gobackward.10" selector:@selector(back:) primary:NO]];
    self.tabletopPlay = [self deckButton:@"Play" symbol:@"play.fill" selector:@selector(togglePlay:) primary:YES];
    [self.tabletopTransport addArrangedSubview:self.tabletopPlay];
    [self.tabletopTransport addArrangedSubview:[self deckButton:@"Forward 10 seconds" symbol:@"goforward.10" selector:@selector(forward:) primary:NO]];
    [self.controls insertArrangedSubview:self.tabletopTransport atIndex:0];
    self.tabletopTransport.hidden = YES;
    self.tabletopUtilities = [[UIStackView alloc] init];
    self.tabletopUtilities.distribution = UIStackViewDistributionFillEqually;
    for (NSArray *entry in @[@[@"Audio", @"speaker.wave.2", @"audioTracks:"],
                            @[@"Subtitles", @"captions.bubble", @"subtitleTracks:"],
                            @[@"Chapters", @"list.bullet", @"chapters:"],
                            @[@"Playback", @"slider.horizontal.3", @"playbackTools:"],
                            @[@"Done", @"xmark", @"done:"]]) {
        UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
        UIButtonConfiguration *config = [UIButtonConfiguration plainButtonConfiguration];
        config.image = [UIImage systemImageNamed:entry[1]];
        config.title = entry[0]; config.imagePlacement = NSDirectionalRectEdgeTop;
        config.imagePadding = 6; config.baseForegroundColor = UIColor.whiteColor;
        config.titleLineBreakMode = NSLineBreakByTruncatingTail;
        config.titleTextAttributesTransformer = ^NSDictionary<NSAttributedStringKey,id> *(NSDictionary<NSAttributedStringKey,id> *attributes) {
            NSMutableDictionary *result = [attributes mutableCopy];
            result[NSFontAttributeName] = [UIFont preferredFontForTextStyle:UIFontTextStyleCaption1];
            return result;
        };
        button.configuration = config;
        button.accessibilityLabel = entry[0];
        [button addTarget:self action:NSSelectorFromString(entry[2]) forControlEvents:UIControlEventTouchUpInside];
        [button.heightAnchor constraintGreaterThanOrEqualToConstant:52].active = YES;
        [self.tabletopUtilities addArrangedSubview:button];
    }
    [self.controls addArrangedSubview:self.tabletopUtilities];
    self.tabletopUtilities.hidden = YES;
    self.bufferSpinner = [[UIActivityIndicatorView alloc] initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleLarge];
    self.bufferSpinner.color = UIColor.whiteColor;
    self.bufferLabel = [[UILabel alloc] init];
    self.bufferLabel.textColor = UIColor.whiteColor;
    self.bufferLabel.hidden = YES;
    self.bufferSpinner.accessibilityLabel = @"Buffering video";
    self.bufferLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleCaption1];
    self.bufferOverlay = [[UIStackView alloc] initWithArrangedSubviews:@[self.bufferSpinner, self.bufferLabel]];
    self.bufferOverlay.axis = UILayoutConstraintAxisVertical;
    self.bufferOverlay.alignment = UIStackViewAlignmentCenter;
    self.bufferOverlay.spacing = 8;
    self.bufferOverlay.userInteractionEnabled = NO;
    self.bufferOverlay.translatesAutoresizingMaskIntoConstraints = NO;
    self.bufferOverlay.hidden = YES;
    [self.view addSubview:self.bufferOverlay];
    UILayoutGuide *safe = self.view.safeAreaLayoutGuide;
    NSLayoutConstraint *naturalHeight = [self.controlsScroll.heightAnchor constraintEqualToAnchor:self.controls.heightAnchor];
    naturalHeight.priority = UILayoutPriorityDefaultHigh;
    self.controlsLeading = [self.controlsScroll.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:12];
    self.controlsTrailing = [self.controlsScroll.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-12];
    self.controlsBottom = [self.controlsScroll.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor];
    self.controlsTop = [self.controlsScroll.topAnchor constraintGreaterThanOrEqualToAnchor:safe.topAnchor constant:8];
    self.deckCenterY = [self.controlsScroll.centerYAnchor constraintEqualToAnchor:safe.centerYAnchor];
    self.controlsHeightLimit = [self.controlsScroll.heightAnchor constraintLessThanOrEqualToConstant:10000];
    self.controlsHeightLimit.active = YES;
    self.bufferCenterX = [self.bufferOverlay.centerXAnchor constraintEqualToAnchor:safe.centerXAnchor];
    self.bufferCenterY = [self.bufferOverlay.centerYAnchor constraintEqualToAnchor:safe.centerYAnchor];
    self.movieBottom = [self.movie.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor];
    [NSLayoutConstraint activateConstraints:@[
        [self.movie.topAnchor constraintEqualToAnchor:self.view.topAnchor],
        [self.movie.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [self.movie.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        self.movieBottom,
        self.controlsLeading, self.controlsTrailing, self.controlsBottom, self.controlsTop,
        naturalHeight,
        self.bufferCenterX, self.bufferCenterY,
        [self.controls.leadingAnchor constraintEqualToAnchor:self.controlsScroll.contentLayoutGuide.leadingAnchor],
        [self.controls.trailingAnchor constraintEqualToAnchor:self.controlsScroll.contentLayoutGuide.trailingAnchor],
        [self.controls.topAnchor constraintEqualToAnchor:self.controlsScroll.contentLayoutGuide.topAnchor],
        [self.controls.bottomAnchor constraintEqualToAnchor:self.controlsScroll.contentLayoutGuide.bottomAnchor],
        [self.controls.widthAnchor constraintEqualToAnchor:self.controlsScroll.frameLayoutGuide.widthAnchor]
    ]];
    UITapGestureRecognizer *tap = [[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(tapVideo:)];
    tap.delegate = self;
    tap.cancelsTouchesInView = NO;
    [self.view addGestureRecognizer:tap];
#if __has_include(<UIKit/UIHingeInteraction.h>)
    if (@available(iOS 27.1, *)) {
        __weak LGVideoController *owner = self;
        [self.view addInteraction:[[UIHingeInteraction alloc] initWithUpdateHandler:^(UIHingeInteraction *interaction, UIHingeInteractionUpdate *update) {
            owner.hingePartiallyOpen = update.hinge && update.hinge.status == UIHingeStatusPartiallyOpen;
            [owner.view setNeedsLayout];
        }]];
    }
#endif
    self.player = [[VLCMediaPlayer alloc] initWithOptions:@[@"--quiet", @"--no-video-title-show", @"--stats"]];
    self.player.drawable = self;
    self.player.delegate = self;
    self.player.media = [self playbackMedia];
    self.discoverers = [NSMutableArray array];
    [self installPlaybackTools];
    [self applyPlaybackOptions];
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

- (BOOL)prefersStatusBarHidden { return self.fullscreen && self.systemChromeHidden && !self.pipActive; }
- (UIInterfaceOrientationMask)supportedInterfaceOrientations { return UIInterfaceOrientationMaskAll; }
- (BOOL)prefersHomeIndicatorAutoHidden { return self.fullscreen && self.systemChromeHidden && !self.pipActive; }
- (UIRectEdge)preferredScreenEdgesDeferringSystemGestures {
    return self.fullscreen && self.systemChromeHidden && !self.pipActive ? UIRectEdgeAll : UIRectEdgeNone;
}
- (BOOL)gestureRecognizer:(UIGestureRecognizer *)gesture shouldReceiveTouch:(UITouch *)touch {
    return ![touch.view isDescendantOfView:self.controlsScroll];
}
- (void)setControlsShown:(BOOL)visible {
    if (self.tabletop) visible = YES;
    if (self.controlsLocked) visible = NO;
    self.controlsVisible = visible;
    [self.controlsTimer invalidate]; self.controlsTimer = nil;
    BOOL shown = visible && !self.pipActive;
    BOOL hideBar = !shown || self.tabletop;
    NSUInteger generation = ++self.chromeGeneration;
    BOOL immediate = self.pipActive || self.lockHidden || self.retired || UIAccessibilityIsReduceMotionEnabled();
    for (UIView *view in @[self.controlsScroll, self.videoHeader]) {
        if (shown) view.hidden = NO;
        view.userInteractionEnabled = shown;
        view.accessibilityElementsHidden = !shown;
    }
    UINavigationBar *bar = self.navigationController.navigationBar;
    if (shown) {
        // Resolve safe-area changes while the incoming controls are transparent.
        self.systemChromeHidden = NO;
        [self setNeedsStatusBarAppearanceUpdate];
    }
    if (!hideBar) [self.navigationController setNavigationBarHidden:NO animated:NO];
    [self.view layoutIfNeeded];
    [bar layoutIfNeeded];
    bar.userInteractionEnabled = !hideBar;
    bar.accessibilityElementsHidden = hideBar;
    [UIView animateWithDuration:immediate ? 0 : .2 delay:0
        options:UIViewAnimationOptionBeginFromCurrentState | UIViewAnimationOptionAllowUserInteraction
        animations:^{
            self.controlsScroll.alpha = shown ? 1 : 0;
            self.videoHeader.alpha = shown ? 1 : 0;
            bar.alpha = hideBar ? 0 : 1;
        } completion:^(BOOL finished) {
            if (generation != self.chromeGeneration) return;
            self.controlsScroll.hidden = !shown;
            self.videoHeader.hidden = !shown;
            // Changing status/navigation visibility earlier shrinks the safe
            // area and moves still-visible controls during their fade.
            self.systemChromeHidden = !shown;
            [self.navigationController setNavigationBarHidden:hideBar animated:NO];
            [self setNeedsStatusBarAppearanceUpdate];
            [self setNeedsUpdateOfHomeIndicatorAutoHidden];
            [self setNeedsUpdateOfScreenEdgesDeferringSystemGestures];
        }];
    self.bufferOverlay.hidden = !self.buffering || self.lockHidden || self.pipActive;
    [self scheduleControls];
}
- (void)scheduleControls {
    BOOL eligible = !self.tabletop && self.fullscreen && self.controlsVisible && !self.pipActive &&
        !self.retired && !self.lockHidden && self.view.window && !self.buffering && self.player.isPlaying;
    if (!eligible) { [self.controlsTimer invalidate]; self.controlsTimer = nil; return; }
    // Decoder notifications must not continually postpone an existing deadline.
    if (!self.controlsTimer.valid) {
        self.controlsTimer = [NSTimer scheduledTimerWithTimeInterval:3 target:self selector:@selector(hideControls:) userInfo:nil repeats:NO];
    }
}
- (void)hideControls:(NSTimer *)timer {
    self.controlsTimer = nil;
    if (self.player.isPlaying && !self.seek.tracking && !self.presentedViewController &&
        !self.navigationController.presentedViewController && !UIAccessibilityIsVoiceOverRunning())
        [self setControlsShown:NO];
    else [self scheduleControls];
}
- (void)toggleFullscreen:(id)sender {
    self.fullscreen = !self.fullscreen;
    [self updateItem:self.fullscreenButton label:self.fullscreen ? @"Exit fullscreen" : @"Fullscreen"];
    [self setControlsShown:YES];
}
- (void)tapVideo:(id)sender {
    if (self.controlsLocked) return;
    if (!self.fullscreen) [self toggleFullscreen:sender];
    else [self setControlsShown:!self.controlsVisible];
}
- (BOOL)showControlsForAccessibility { [self setControlsShown:YES]; return YES; }
- (void)viewWillDisappear:(BOOL)animated {
    [super viewWillDisappear:animated];
    self.surfaceVisible = NO;
    [self clearPausePresentation];
    [self setScreenAwake:NO];
    [self.controlsTimer invalidate]; self.controlsTimer = nil;
}
- (void)viewDidAppear:(BOOL)animated {
    [super viewDidAppear:animated];
    self.surfaceVisible = YES;
    [self becomeFirstResponder];
    [self updateScreenAwake];
    [self setControlsShown:YES];
}
- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    // VLCKit installs its surface through VLCDrawable, not a UIView drawable.
    // Explicitly resize that surface after rotations, folds and bar changes.
    for (UIView *surface in self.movie.subviews) surface.frame = self.movie.bounds;
    CGRect safe = self.view.safeAreaLayoutGuide.layoutFrame;
    NSDictionary *layout = [self playbackOptions][@"reader_layout"];
    CGFloat margin = layout[@"margin"] ? [layout[@"margin"] doubleValue] : 12;
    CGRect available = safe;
    if (self.view.window) {
        // Adaptive navigation bars can contribute a bottom safe-area inset even
        // when their controls are on the side. Only the physical window inset
        // belongs below the timeline; retain the controller's side/top guards.
        UIWindow *window = self.view.window;
        CGRect physical = [self.view convertRect:UIEdgeInsetsInsetRect(window.bounds, window.safeAreaInsets)
                                       fromView:window];
        CGFloat bottom = MIN(CGRectGetMaxY(self.view.bounds), CGRectGetMaxY(physical));
        available.size.height = MAX(0, bottom - CGRectGetMinY(available));
    }
    CGRect movieArea = self.view.bounds;
    BOOL tabletop = NO;
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
                if (self.hingePartiallyOpen && CGRectGetMinY(fold) > 150 &&
                    CGRectGetMaxY(safe) - CGRectGetMaxY(fold) > 220) {
                    tabletop = YES;
                    movieArea.size.height = CGRectGetMinY(fold);
                }
                CGFloat bottom = CGRectGetMaxY(available) - CGRectGetMaxY(fold);
                // Keep the timeline below a horizontal crease when it fits.
                if (bottom >= 112) { available.origin.y = CGRectGetMaxY(fold); available.size.height = bottom; }
                else available.size.height = CGRectGetMinY(fold) - CGRectGetMinY(available);
            }
        }
    }
#endif
    BOOL poseChanged = self.tabletop != tabletop;
    self.tabletop = tabletop;
    self.movieBottom.constant = CGRectGetMaxY(movieArea) - CGRectGetMaxY(self.view.bounds);
    self.tabletopTransport.hidden = !tabletop;
    self.tabletopUtilities.hidden = !tabletop;
    self.controls.spacing = tabletop ? 10 : 4;
    self.controls.layoutMarginsRelativeArrangement = tabletop;
    self.controls.layoutMargins = tabletop ? UIEdgeInsetsMake(16, 16, 16, 16) : UIEdgeInsetsZero;
    if (tabletop && self.view.window) {
        // A hidden navigation rail may retain controller safe-area insets.
        // The lower deck uses physical window insets, not that retired rail.
        available.origin.x = CGRectGetMinX(self.view.bounds);
        available.size.width = self.view.bounds.size.width;
#if __has_include(<UIKit/UIHingeInteraction.h>)
        if (@available(iOS 27.1, *)) {
            for (UIViewReservedRegion *region in [self.view reservedRegionsOfKind:UIViewReservedRegionKind.occlusionRegionKind]) {
                CGRect obstacle = CGRectIntersection(available, region.frame);
                if (CGRectIsNull(obstacle) || CGRectIsEmpty(obstacle)) continue;
                if (CGRectGetMinX(obstacle) <= CGRectGetMinX(available)) {
                    CGFloat right = CGRectGetMaxX(available);
                    available.origin.x = CGRectGetMaxX(obstacle);
                    available.size.width = right - available.origin.x;
                } else if (CGRectGetMaxX(obstacle) >= CGRectGetMaxX(available)) {
                    available.size.width = CGRectGetMinX(obstacle) - available.origin.x;
                }
            }
        }
#endif
    }
    self.controlsScroll.backgroundColor = tabletop ? [UIColor colorWithWhite:.08 alpha:1] : UIColor.clearColor;
    self.controlsScroll.layer.cornerRadius = tabletop ? 24 : 0;
    if (poseChanged) [self setControlsShown:YES];
    // In laptop posture the upper panel owns the movie and the lower panel
    // owns persistent controls. The movie never spans the horizontal hinge.
    CGRect spinnerArea = tabletop ? movieArea : available;
    self.controlsBottom.active = !tabletop;
    self.deckCenterY.active = tabletop;
    self.deckCenterY.constant = CGRectGetMidY(available) - CGRectGetMidY(safe);
    self.controlsHeightLimit.constant = MAX(44, available.size.height - 24);
    self.controlsLeading.constant = margin + CGRectGetMinX(available) - CGRectGetMinX(safe);
    self.controlsTrailing.constant = -margin + CGRectGetMaxX(available) - CGRectGetMaxX(safe);
    self.controlsTop.constant = 8 + CGRectGetMinY(available) - CGRectGetMinY(safe);
    self.controlsBottom.constant = CGRectGetMaxY(available) - CGRectGetMaxY(safe);
    self.bufferCenterX.constant = CGRectGetMidX(spinnerArea) - CGRectGetMidX(safe);
    self.bufferCenterY.constant = CGRectGetMidY(spinnerArea) - CGRectGetMidY(safe);
}

- (void)updateItem:(UIBarButtonItem *)button label:(NSString *)label {
    NSDictionary *symbols = @{@"Play": @"play.fill", @"Pause": @"pause.fill",
        @"Back 10 seconds": @"gobackward.10", @"Forward 10 seconds": @"goforward.10",
        @"Audio tracks": @"speaker.wave.2", @"Subtitles": @"captions.bubble", @"Fullscreen": @"arrow.up.left.and.arrow.down.right",
        @"Exit fullscreen": @"arrow.down.right.and.arrow.up.left", @"More playback options": @"ellipsis",
        @"Chapters": @"list.bullet", @"Done": @"xmark"};
    button.image = [UIImage systemImageNamed:symbols[label]];
    if (button == self.playButton && self.tabletopPlay) {
        UIButtonConfiguration *config = self.tabletopPlay.configuration;
        config.image = [UIImage systemImageNamed:symbols[label] withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:36 weight:UIImageSymbolWeightSemibold]];
        self.tabletopPlay.configuration = config;
        self.tabletopPlay.accessibilityLabel = label;
    }
    button.title = label;
    button.accessibilityLabel = label;
    button.accessibilityIdentifier = [@"video." stringByAppendingString:label];
    button.accessibilityHint = [label isEqualToString:@"Done"] ? @"Close video player" : nil;
}

- (UIButton *)deckButton:(NSString *)label symbol:(NSString *)symbol selector:(SEL)selector primary:(BOOL)primary {
    UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
    UIButtonConfiguration *config = primary ? [UIButtonConfiguration filledButtonConfiguration] : [UIButtonConfiguration tintedButtonConfiguration];
    config.image = [UIImage systemImageNamed:symbol withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:primary ? 36 : 28 weight:UIImageSymbolWeightSemibold]];
    config.baseForegroundColor = primary ? UIColor.blackColor : UIColor.whiteColor;
    config.baseBackgroundColor = primary ? UIColor.whiteColor : [UIColor colorWithWhite:.25 alpha:1];
    config.cornerStyle = UIButtonConfigurationCornerStyleCapsule;
    button.configuration = config;
    button.accessibilityLabel = label;
    button.accessibilityIdentifier = [@"video.deck." stringByAppendingString:label];
    [button.widthAnchor constraintEqualToConstant:primary ? 88 : 64].active = YES;
    [button.heightAnchor constraintEqualToConstant:primary ? 88 : 64].active = YES;
    [button addTarget:self action:selector forControlEvents:UIControlEventTouchUpInside];
    return button;
}

- (UIBarButtonItem *)item:(NSString *)title selector:(SEL)selector {
    UIBarButtonItem *button = [[UIBarButtonItem alloc] initWithImage:nil style:UIBarButtonItemStylePlain target:self action:selector];
    [self updateItem:button label:title];
    if (@available(iOS 27.0, *)) {
        button.visibilityPriority = [title isEqualToString:@"Play"] || [title isEqualToString:@"Done"] ? 1000 : 500;
    }
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
    if (self.controlsLocked) return;
    if (self.playRequested) [self pause]; else [self startByUser];
}
- (void)seekToMilliseconds:(int64_t)target {
    if (self.controlsLocked || ![self canPlay:NO] || !self.player.isSeekable) return;
    int64_t previous = [self positionMilliseconds];
    if (llabs(target - previous) >= 10000) { self.undoMilliseconds = previous; self.undoUntil = NSProcessInfo.processInfo.systemUptime + 8; self.undoSeekButton.hidden = NO; }
    int64_t duration = self.player.media.length.value.longLongValue;
    target = MAX(0, target);
    if (duration > 0) target = MIN(target, MAX(0, duration - 1));
    // VLC may retain the old reported clock while paused. Preserve the requested
    // position for controls/checkpoints and apply it again on explicit Play.
    self.ended = NO;
    self.lastPlaybackProgress = self.lastFrameProgress = NSProcessInfo.processInfo.systemUptime;
    self.lastRenderedClock = target;
    if (self.networkResumePending) self.bufferPosition = target;
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
    [self.controlsTimer invalidate]; self.controlsTimer = nil;
    [self scheduleControls];
}
- (void)done:(id)sender { if (self.closed) self.closed(); }
- (void)pause {
    [self holdPausePresentation];
    [self setScreenAwake:NO];
    [self setControlsShown:YES];
    // VLCKit pause is an explicit pause, but coalesce duplicate OS/lifecycle events.
    self.manualResumeRequired = YES;
    self.playRequested = NO;
    [self updateItem:self.playButton label:@"Play"];
    if (self.networkResumePending) self.startMilliseconds = self.bufferPosition;
    self.networkResumePending = NO;
    self.buffering = NO;
    self.bufferOverlay.hidden = YES;
    [self.bufferSpinner stopAnimating];
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
- (VLCMedia *)playbackMedia {
    VLCMedia *media = [VLCMedia mediaWithURL:[NSURL URLWithString:self.videoURL]];
    [media addOption:@":network-caching=3000"];
    [media addOption:@":file-caching=1500"];
    // Cloud starvation makes software-decoded interframe AVI arrive late.
    // Decode complete frames instead of catching up with partial pictures, and
    // retain the last good picture when the decoder flags damaged output.
    [media addOption:@":no-avcodec-hurry-up"];
    [media addOption:@":no-avcodec-corrupted"];
    [media addOption:@":audio-time-stretch"];
    NSDictionary *options = [self playbackOptions];
    for (NSArray *entry in @[@[@"audio_language", @"audio-language"], @[@"subtitle_language", @"sub-language"]]) {
        NSString *language = options[entry[0]];
        if (language.length) [media addOption:[NSString stringWithFormat:@":%@=%@", entry[1], language]];
    }
    return media;
}
- (void)setTransportFailure:(NSString *)message {
    _transportFailure = [message copy];
    if (self.player.state == VLCMediaPlayerStateError) [self showStatus:message];
}
- (void)playbackFailed {
    int64_t position = MAX(0, self.lastPosition);
    [self pause];
    self.startMilliseconds = position;
    [self showStatus:self.transportFailure ?: @"Playback stopped unexpectedly. Press Play to retry from this position."];
}
- (void)startByUser {
    if (!self.requestPlay || !self.requestPlay() || ![self canPlay:NO]) return;
    NSError *error = nil;
    AVAudioSession *audio = AVAudioSession.sharedInstance;
    if (![audio setCategory:AVAudioSessionCategoryPlayback error:&error] ||
        ![audio setActive:YES error:&error]) return;
    if (![self canPlay:NO]) return; // Activation can change the selected output.
    if (self.player.state == VLCMediaPlayerStateError || self.player.state == VLCMediaPlayerStateStopped) {
        if (self.hasPlayed) self.startMilliseconds = self.ended ? 0 : MAX(0, self.lastPosition);
        self.ended = NO;
        self.hasPlayed = NO;
        self.player.media = [self playbackMedia];
    }
    self.transportFailure = nil;
    self.message.text = @"";
    self.message.hidden = YES;
    self.manualResumeRequired = NO;
    self.pausePending = NO;
    if (self.audioSuppressed) { self.player.audio.muted = self.resumeMuted; self.audioSuppressed = NO; }
    self.playRequested = YES;
    [self clearPausePresentation];
    if (self.startMilliseconds >= 0 && self.player.isPlaying) {
        self.player.time = [VLCTime timeWithNumber:@(self.startMilliseconds)];
        self.startMilliseconds = -1;
    }
    self.lastPlaybackProgress = self.lastFrameProgress = NSProcessInfo.processInfo.systemUptime;
    [self updateItem:self.playButton label:@"Pause"];
    self.networkResumePending = NO;
    [self.player play];
    if ([self.message.text isEqualToString:@"Ready. Press Play to start."]) {
        self.message.text = @"";
        self.message.hidden = YES;
    }
}
// A slow prefetch is only a hint. Hold playback only after the renderer
// actually stops progressing; VLC may still have seconds of playable data.
- (void)setNetworkWaiting:(BOOL)waiting {
    if (self.retired) return;
    _networkWaiting = waiting;
    if (!waiting && self.networkResumePending) {
        self.networkResumePending = NO;
        self.lastPlaybackProgress = self.lastFrameProgress = NSProcessInfo.processInfo.systemUptime;
        if (self.playRequested && !self.manualResumeRequired && [self canPlay:self.casting || self.pipActive]) {
            // Pause retains the demuxer and its reference pictures. Seeking on
            // every refill flushes them and forces another remote AVI seek.
            // An explicit user seek already owns startMilliseconds separately.
            [self.player play];
        }
    }
}
- (void)updatePlaybackProgress {
    NSTimeInterval now = NSProcessInfo.processInfo.systemUptime;
    int64_t clock = self.player.time.value.longLongValue;
    uint64_t frames = self.player.media.statistics.displayedPictures;
    // VLC publishes statistics in batches. Advancing playback time is also
    // progress; stale counters must never put a spinner over moving video.
    BOOL progressed = frames != self.observedFrames || clock != self.observedClock;
    if (progressed) self.lastPlaybackProgress = now;
    if (frames != self.observedFrames || (frames == 0 && clock != self.observedClock)) {
        self.lastRenderedClock = clock; self.lastFrameProgress = now;
    }
    self.observedFrames = frames;
    self.observedClock = clock;
    // The audio clock may free-run through a blocked input. A network hold
    // also watches rendered frames, allowing six seconds for batched stats.
    BOOL renderStalled = frames > 0 && now - self.lastFrameProgress >= 6.0;
    BOOL stalled = self.playRequested && !self.manualResumeRequired && !self.ended &&
        (now - self.lastPlaybackProgress >= 3.0 || (self.networkWaiting && renderStalled));
    if (stalled && self.transportFailure) { [self playbackFailed]; return; }
    if (stalled && self.networkWaiting && !self.networkResumePending) {
        self.bufferPosition = MAX(0, self.lastRenderedClock);
        self.networkResumePending = YES;
        if (self.player.isPlaying) [self.player pause];
    }
    BOOL changed = self.buffering != stalled;
    self.buffering = stalled;
    self.bufferOverlay.hidden = !stalled || self.lockHidden || self.pipActive;
    if (stalled) {
        [self.bufferSpinner startAnimating];
        if (changed) [self setControlsShown:YES];
    } else {
        [self.bufferSpinner stopAnimating];
        if (changed) [self scheduleControls];
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
    [self clearPausePresentation];
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
        [self pause]; [self clearPausePresentation]; self.movie.hidden = YES;
    } else if (!self.lockHidden && [self canPlay:NO]) self.movie.hidden = NO;
}
- (int64_t)positionMilliseconds {
    if (self.ended) return 0;
    if (self.networkResumePending) return self.bufferPosition;
    if (self.startMilliseconds >= 0) return self.startMilliseconds;
    int64_t value = self.player.time.value.longLongValue;
    return value >= 0 ? value : self.lastPosition;
}
- (BOOL)completed { return self.ended; }
- (NSString *)playbackDiagnosticJSON {
    VLCMediaStats stats = self.player.media.statistics;
    NSDictionary *value = @{@"requested": @(self.playRequested), @"playing": @(self.player.isPlaying),
        @"manualPause": @(self.manualResumeRequired), @"networkWaiting": @(self.networkWaiting),
        @"held": @(self.networkResumePending), @"buffering": @(self.buffering),
        @"decodedFrames": @(stats.decodedVideo), @"displayedFrames": @(stats.displayedPictures),
        @"lateFrames": @(stats.latePictures), @"lostFrames": @(stats.lostPictures),
        @"readBytes": @(stats.readBytes)};
    return [[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:value options:0 error:nil] encoding:NSUTF8StringEncoding];
}

- (void)showStatus:(NSString *)message {
    self.message.text = message;
    self.message.hidden = message.length == 0;
    [self setControlsShown:YES];
}
- (void)tick:(NSTimer *)timer {
    if (![self canPlay:NO]) [self pause];
    [self updatePlaybackProgress];
    [self applyPictureSize];
    if (NSProcessInfo.processInfo.systemUptime > self.undoUntil) self.undoSeekButton.hidden = YES;
    if (self.controlsLocked) [self.view bringSubviewToFront:self.unlockButton];
    [self updateScreenAwake];
    int64_t position = [self positionMilliseconds];
    int64_t duration = self.player.media.length.value.longLongValue;
    if (!self.seek.tracking && duration > 0) self.seek.value = (float)position / duration;
    NSString *(^time)(int64_t) = ^NSString *(int64_t value) {
        int64_t seconds = MAX(0, value / 1000);
        return [NSString stringWithFormat:@"%lld:%02lld:%02lld", seconds / 3600, seconds / 60 % 60, seconds % 60];
    };
    [self.view bringSubviewToFront:self.controlsScroll];
    [self.view bringSubviewToFront:self.bufferOverlay];
    self.timeLabel.text = [NSString stringWithFormat:@"%@ / %@%@", time(position), time(duration), self.cacheApproximate ? @" · Cache ≈" : @""];
    self.timeLabel.accessibilityValue = self.timeLabel.text;
    self.seek.accessibilityValue = self.timeLabel.text;
    self.pauseSnapshot.frame = self.movie.frame;
    self.lastPosition = position;
    [self updateItem:self.playButton label:self.playRequested ? @"Pause" : @"Play"];
}
- (void)mediaPlayerStateChanged:(VLCMediaPlayerState)state {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (self.retired) return;
        if (state != VLCMediaPlayerStatePlaying) self.pausePending = NO;
        // A blocked input can complete an earlier Pause after Play was queued.
        // Reconcile that completion with current intent, never with read-ahead.
        if (state == VLCMediaPlayerStatePaused && self.playRequested &&
            !self.manualResumeRequired && !self.networkResumePending &&
            [self canPlay:self.casting || self.pipActive]) [self.player play];
        if (state == VLCMediaPlayerStatePlaying) {
            self.hasPlayed = YES;
            [self applyPlaybackOptions];
            if (self.manualResumeRequired || ![self canPlay:NO]) { [self pause]; return; }
            if (self.startMilliseconds >= 0) {
                self.player.time = [VLCTime timeWithNumber:@(self.startMilliseconds)];
                self.startMilliseconds = -1;
            }
            self.ended = NO;
            [self scheduleControls];
        }
        int64_t duration = self.player.media.length.value.longLongValue;
        if (state == VLCMediaPlayerStateStopped && (self.player.position >= .999 ||
            (duration > 0 && self.lastPosition >= duration - 1000))) {
            BOOL notify = !self.ended;
            self.ended = YES;
            self.playRequested = NO;
            if (notify) [self emitCommand:@"ended" value:@""];
            [self setControlsShown:YES];
        }
        if (!self.networkWaiting && (state == VLCMediaPlayerStateError || state == VLCMediaPlayerStateStopped || state == VLCMediaPlayerStatePaused)) {
            self.buffering = NO; self.bufferOverlay.hidden = YES;
            [self.bufferSpinner stopAnimating];
        }
        if ((state == VLCMediaPlayerStateError && self.player.state == VLCMediaPlayerStateError) ||
            (state == VLCMediaPlayerStateStopped && self.player.state == VLCMediaPlayerStateStopped &&
             self.hasPlayed && self.playRequested && !self.ended)) [self playbackFailed];
        if (state == VLCMediaPlayerStatePlaying) [self updateScreenAwake];
        else [self setScreenAwake:NO];
        [self.pipController invalidatePlaybackState];
    });
}
- (void)mediaPlayerLengthChanged:(int64_t)length { [self.pipController invalidatePlaybackState]; }

- (UIAlertController *)menu:(NSString *)title sender:(id)sender {
    // Phone-sized Duo windows can offer less height than a long popover's
    // minimum size. Use UIKit's scrollable alert there; reserve anchored sheets
    // for iPad, whose popover has room for the playback option list.
    UIAlertControllerStyle style = self.traitCollection.userInterfaceIdiom == UIUserInterfaceIdiomPhone
        ? UIAlertControllerStyleAlert : UIAlertControllerStyleActionSheet;
    UIAlertController *menu = [UIAlertController alertControllerWithTitle:title message:nil preferredStyle:style];
    BOOL anchoredToOverflow = NO;
    if (@available(iOS 16.0, *)) {
        if ([sender isKindOfClass:UIBarButtonItem.class] &&
            [((UIBarButtonItem *)sender).accessibilityLabel isEqualToString:@"More playback options"] &&
            self.navigationItem.overflowPresentationSource) {
            menu.popoverPresentationController.sourceItem = self.navigationItem.overflowPresentationSource;
            anchoredToOverflow = YES;
        }
    }
    if (!anchoredToOverflow && [sender isKindOfClass:UIBarButtonItem.class]) menu.popoverPresentationController.barButtonItem = sender;
    else if (!anchoredToOverflow) {
        menu.popoverPresentationController.sourceView = sender ?: self.view;
        menu.popoverPresentationController.sourceRect = [sender isKindOfClass:UIView.class] ? ((UIView *)sender).bounds : self.view.bounds;
    }
    [menu addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    return menu;
}
- (void)chapters:(id)sender {
    if (![self canPlay:NO]) return;
    [self setControlsShown:YES];
    UIAlertController *menu = [self menu:@"Chapters" sender:sender];
    NSArray<VLCMediaPlayerChapterDescription *> *chapters = [self.player chapterDescriptionsOfTitle:self.player.currentTitleIndex];
    for (NSUInteger index = 0; index < chapters.count; index++) {
        VLCMediaPlayerChapterDescription *chapter = chapters[index];
        int64_t offset = chapter.timeOffset.value.longLongValue;
        NSString *name = chapter.name.length ? chapter.name : [NSString stringWithFormat:@"Chapter %lu", (unsigned long)index + 1];
        NSString *label = [NSString stringWithFormat:@"%@%lld:%02lld · %@", chapter.isCurrent ? @"✓ " : @"", offset / 60000, offset / 1000 % 60, name];
        [menu addAction:[UIAlertAction actionWithTitle:label style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
            [self seekToMilliseconds:offset];
        }]];
    }
    if (!chapters.count) menu.message = @"This video has no embedded chapters.";
    [self presentViewController:menu animated:YES completion:nil];
}
- (void)audioTracks:(id)sender { [self tracks:sender subtitles:NO]; }
- (void)subtitleTracks:(id)sender { [self tracks:sender subtitles:YES]; }
- (NSString *)trackLabel:(VLCMediaPlayerTrack *)track index:(NSUInteger)index {
    NSMutableArray *parts = [NSMutableArray array];
    if (track.trackName.length) [parts addObject:track.trackName];
    if (track.language.length && ![track.language isEqualToString:@"und"]) {
        NSString *language = [NSLocale.currentLocale localizedStringForLanguageCode:track.language] ?: track.language;
        if (![parts containsObject:language]) [parts addObject:language];
    }
    if (track.trackDescription.length && ![parts containsObject:track.trackDescription]) [parts addObject:track.trackDescription];
    NSString *codec = [track codecName];
    if (codec.length) [parts addObject:codec];
    NSString *label = parts.count ? [parts componentsJoinedByString:@" · "] : [NSString stringWithFormat:@"Track %lu", (unsigned long)index + 1];
    return track.isSelected ? [@"✓ " stringByAppendingString:label] : label;
}
- (void)tracks:(id)sender subtitles:(BOOL)text {
    if (![self canPlay:NO]) return;
    // The timer defers hiding while a menu is presented and resumes afterward.
    [self setControlsShown:YES];
    UIAlertController *menu = [self menu:text ? @"Subtitles" : @"Audio tracks" sender:sender];
    if (text) [menu addAction:[UIAlertAction actionWithTitle:@"Subtitles off" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        if ([self canPlay:NO]) [self.player deselectAllTextTracks];
    }]];
    NSArray<VLCMediaPlayerTrack *> *tracks = text ? self.player.textTracks : self.player.audioTracks;
    for (NSUInteger index = 0; index < tracks.count; index++) {
        VLCMediaPlayerTrack *track = tracks[index];
        [menu addAction:[UIAlertAction actionWithTitle:[self trackLabel:track index:index] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
            if ([self canPlay:NO]) track.selectedExclusively = YES;
        }]];
    }
    if (text) {
        NSArray *subtitles = [NSJSONSerialization JSONObjectWithData:[self.subtitleJSON dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
        for (NSDictionary *subtitle in subtitles) {
            [menu addAction:[UIAlertAction actionWithTitle:subtitle[@"name"] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
                if ([self canPlay:NO]) [self.player addPlaybackSlave:[NSURL URLWithString:subtitle[@"url"]] type:VLCMediaPlaybackSlaveTypeSubtitle enforce:YES];
            }]];
        }
    }
    if (!tracks.count) menu.message = @"No embedded tracks available yet. Start playback to discover tracks.";
    [self presentViewController:menu animated:YES completion:nil];
}
- (void)mediaPlayerBufferingChanged:(float)progress {
    // Decoder progress callbacks also describe prebuffering while frames are
    // flowing. The render-progress watchdog owns the quiet buffering indicator.
}
- (void)cast:(id)sender {
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
- (void)pip:(id)sender {
    if (![self canPlay:YES]) return;
    if (self.pipController) [self.pipController startPictureInPicture];
    else [self showStatus:@"Picture in picture is not ready. Start playback first."];
}
- (id<VLCPictureInPictureMediaControlling>)mediaController { return self; }
- (void (^)(id<VLCPictureInPictureWindowControlling>))pictureInPictureReady {
    __weak LGVideoController *owner = self;
    return ^(id<VLCPictureInPictureWindowControlling> controller) {
        if (owner.restricted || owner.retired) return;
        owner.pipController = controller;
        controller.stateChangeEventHandler = ^(BOOL active) {
            owner.pipActive = active;
            [owner updateScreenAwake];
            [owner setControlsShown:YES];
        };
    };
}
- (void)addSubview:(UIView *)view {
    if (self.retired) return;
    view.frame = self.movie.bounds;
    view.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    [self.movie addSubview:view];
}
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
- (void)retireWithCompletion:(dispatch_block_t)completion {
    NSAssert(NSThread.isMainThread, @"Retire video on the UI thread");
    if (self.retirementComplete) { if (completion) completion(); return; }
    if (!self.retirementCallbacks) self.retirementCallbacks = [NSMutableArray array];
    if (completion) [self.retirementCallbacks addObject:[completion copy]];
    if (self.retired) return;
    [self setScreenAwake:NO];
    self.retired = YES;
    [self clearPausePresentation];
    self.command = nil;
    self.bufferOverlay.hidden = YES;
    [self.bufferSpinner stopAnimating];
    self.movie.hidden = YES;
    self.player.audio.muted = YES;
    self.fullscreen = NO;
    [self setControlsShown:YES];
    [self.timer invalidate]; self.timer = nil;
    [NSNotificationCenter.defaultCenter removeObserver:self];
    [self.callObserver setDelegate:nil queue:NULL]; self.callObserver = nil;
    [self.pipController stopPictureInPicture]; self.pipController = nil;
    self.player.delegate = nil;
    self.player.drawable = nil;
    // VLC teardown joins a decoder which may synchronously enter UIKit. Keep
    // MAIN available, and ensure the *last* strong reference dies on the worker.
    __block VLCMediaPlayer *retiringPlayer = self.player;
    __block NSMutableArray *retiringDiscoverers = self.discoverers;
    self.player = nil;
    self.discoverers = nil;
    self.allowed = nil; self.requestPlay = nil; self.closed = nil;
    static dispatch_queue_t teardownQueue;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ teardownQueue = dispatch_queue_create("logistics.video.teardown", DISPATCH_QUEUE_SERIAL); });
    dispatch_async(teardownQueue, ^{
        @autoreleasepool {
            for (VLCRendererDiscoverer *discoverer in retiringDiscoverers) [discoverer stop];
            retiringDiscoverers = nil;
            [retiringPlayer stop];
            retiringPlayer = nil;
        }
        dispatch_async(dispatch_get_main_queue(), ^{
            self.retirementComplete = YES;
            NSArray *callbacks = [self.retirementCallbacks copy];
            self.retirementCallbacks = nil;
            for (dispatch_block_t callback in callbacks) callback();
        });
    });
}
@end

#import "PlaybackControls.m"

#import "PausePresentation.m"
