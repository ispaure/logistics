// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

// Logistics native video owner. VLCKit is linked by the mobile build manager.
#import <UIKit/UIKit.h>
#import <AVFoundation/AVFoundation.h>
#import <AVKit/AVKit.h>
#import <CallKit/CallKit.h>
#import <math.h>
#import <VLCKit/VLCKit.h>
#import <VLCKit/vlc/libvlc.h>
#import <VLCKit/vlc/libvlc_media.h>
#import <VLCKit/vlc/libvlc_media_player.h>
// VLCKit's existing descriptor bridge keeps this call on its retained media.
@interface VLCMedia (LGStatisticsDescriptor)
- (libvlc_media_t *)libVLCMediaDescriptor;
@end
@interface VLCMediaPlayer (LGClockDescriptor)
- (libvlc_media_player_t *)libVLCMediaPlayer;
@end
#if __has_include(<UIKit/UIHingeInteraction.h>)
#import <UIKit/UIHingeInteraction.h>
#import <UIKit/UIViewReservedRegion.h>
#endif

#import "ScreenAwake.m"

static NSString *const LGVideoChapterHint = @"Open Chapters for named positions and chapter skips.";
static const int64_t LGVideoChapterRestartMilliseconds = 1000;

@interface LGVideoTimeline : UISlider
@property(nonatomic, copy) NSArray<NSNumber *> *chapterFractions;
@property(nonatomic, strong) CAShapeLayer *chapterMarkers;
@end

@implementation LGVideoTimeline
- (void)setChapterFractions:(NSArray<NSNumber *> *)fractions {
    if ([_chapterFractions isEqualToArray:fractions]) return;
    _chapterFractions = [fractions copy];
    self.accessibilityHint = fractions.count ? LGVideoChapterHint : nil;
    [self setNeedsLayout];
}
- (void)layoutSubviews {
    [super layoutSubviews];
    if (!self.chapterMarkers && !self.chapterFractions.count) return;
    if (!self.chapterMarkers) {
        self.chapterMarkers = [CAShapeLayer layer];
        self.chapterMarkers.fillColor = UIColor.whiteColor.CGColor;
        [self.layer addSublayer:self.chapterMarkers];
    }
    CGRect track = [self trackRectForBounds:self.bounds];
    CGFloat start = CGRectGetMidX([self thumbRectForBounds:self.bounds trackRect:track value:0]);
    CGFloat end = CGRectGetMidX([self thumbRectForBounds:self.bounds trackRect:track value:1]);
    UIBezierPath *path = [UIBezierPath bezierPath];
    for (NSNumber *fraction in self.chapterFractions) {
        CGFloat x = start + fraction.doubleValue * (end - start);
        [path appendPath:[UIBezierPath bezierPathWithRect:CGRectMake(x - 1, CGRectGetMaxY(track) + 4, 2, 5)]];
    }
    self.chapterMarkers.frame = self.bounds;
    self.chapterMarkers.path = path.CGPath;
}
@end

static NSString *LGVideoCompactCodec(NSString *value) {
    NSString *key = [[(value ?: @"") lowercaseString] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    NSDictionary *names = @{@"a52": @"AC-3", @"ac3": @"AC-3", @"ac-3": @"AC-3",
        @"audio coding 3 (ac-3)": @"AC-3", @"eac3": @"E-AC-3", @"e-ac-3": @"E-AC-3",
        @"a/52 b audio (aka e-ac3)": @"E-AC-3", @"audio coding 3 (e-ac-3)": @"E-AC-3",
        @"trhd": @"TrueHD", @"truehd": @"TrueHD", @"dolby truehd": @"TrueHD",
        @"mp4a": @"AAC", @"aac": @"AAC", @"mpeg aac audio": @"AAC", @"mpeg aac audio (mp4a)": @"AAC", @"mpeg-4 audio (aac)": @"AAC",
        @"dts": @"DTS", @"dts audio (dts )": @"DTS", @"flac": @"FLAC", @"opus": @"Opus"};
    return names[key] ?: value ?: @"";
}

static NSString *LGVideoAudioLabel(NSUInteger number, NSArray<NSString *> *names, NSString *codec,
                                 unsigned channels, unsigned sampleRate) {
    codec = LGVideoCompactCodec(codec);
    NSMutableArray *parts = [NSMutableArray arrayWithObject:[NSString stringWithFormat:@"#%lu", (unsigned long)number]];
    NSMutableSet *seen = [NSMutableSet setWithArray:@[@"", @"und", @"unknown", @"undefined", @"audio", codec.lowercaseString]];
    if (channels) [seen addObjectsFromArray:@[@"surround", @"stereo", @"mono"]];
    for (NSString *raw in names) {
        NSString *name = [raw stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
        NSString *key = name.lowercaseString;
        if ([seen containsObject:key] || [LGVideoCompactCodec(name).lowercaseString isEqual:codec.lowercaseString] ||
            [key rangeOfString:@"^(audio\\s*)?track\\s*[0-9]+$" options:NSRegularExpressionSearch].location != NSNotFound) continue;
        [seen addObject:key]; [parts addObject:name];
    }
    if (codec.length) [parts addObject:codec];
    if (channels) [parts addObject:channels == 1 ? @"Mono" : channels == 2 ? @"Stereo" :
        [NSString stringWithFormat:@"%u ch", channels]];
    if (sampleRate && sampleRate != 48000) [parts addObject:[NSString stringWithFormat:@"%g kHz", sampleRate / 1000.0]];
    if (parts.count == 1) [parts addObject:@"Audio"];
    return [parts componentsJoinedByString:@" · "];
}

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

@class LGVideoController;
// Modern PiP is owned by the caption compositor. Expose only drawable methods
// to VLC so its automatic background PiP cannot replace the captioned stream.
@interface LGCaptionVideoDrawable : NSObject <VLCDrawable>
@property(nonatomic, weak) LGVideoController *owner;
@end

@interface LGVideoController : UIViewController
    <VLCDrawable, VLCPictureInPictureDrawable, VLCPictureInPictureMediaControlling,
     VLCMediaPlayerDelegate, CXCallObserverDelegate, UIGestureRecognizerDelegate, AVRoutePickerViewDelegate>
@property(nonatomic, copy) NSString *videoURL;
@property(nonatomic) VLCMediaStats lastPlaybackStats;
@property(nonatomic, weak) VLCMedia *statisticsMedia;
@property(nonatomic, strong) LGScreenAwakeLease *awakeLease;
@property(nonatomic, copy) NSString *subtitleJSON;
@property(nonatomic, copy) NSString *pendingSubtitleURL;
@property(nonatomic, copy) NSSet<NSString *> *subtitleTracksBeforeAttachment;
@property(nonatomic) int64_t startMilliseconds; // Deferred resume/paused seek; -1 means no pending seek.
@property(nonatomic) int64_t knownDuration;
@property(nonatomic) BOOL resumeSeekSubmitted, inputNeedsRestart, audioOnlyInput, openingSeekPending;
@property(nonatomic) NSTimeInterval seekSubmittedAt, seekDeadline;
@property(nonatomic) uint64_t seekAudioBaseline, seekFrameBaseline;
@property(nonatomic) BOOL restricted;
@property(nonatomic) BOOL airPlayAvailable, airPlayWasExternal, airPlaySeekPending;
@property(nonatomic) BOOL airPlayPickerOpen, airPlayPreparing, airPlayResumeLocal;
@property(nonatomic) NSTimeInterval airPlayRouteDeadline;
@property(nonatomic) int64_t airPlaySeekTarget, airPlayStartPosition;
@property(nonatomic) int64_t airPlayClock, airPlayConfirmedPosition;
@property(nonatomic) BOOL airPlayAdvanced, airPlayRecovered, airPlaySystemPaused, airPlaySawTransport;
@property(nonatomic) NSTimeInterval airPlayStartDeadline, airPlaySeekDeadline, airPlayRouteLossDeadline;
@property(nonatomic) NSTimeInterval airPlayLastProgress, airPlayLastTrace;
@property(nonatomic) NSTimeInterval airPlayLastPoll, airPlayStallGraceUntil;
@property(nonatomic, copy) NSString *airPlayTraceState;
@property(nonatomic) NSUInteger airPlaySeekGeneration;
@property(nonatomic, copy) BOOL (^airPlayAllowed)(void);
@property(nonatomic, copy) void (^airPlaySourceTrace)(void);
@property(nonatomic, strong) AVPlayerViewController *airPlayController;
@property(nonatomic, strong) AVRoutePickerView *airPlayPicker;
@property(nonatomic, strong) AVPlayer *airPlayPlayer;
@property(nonatomic) BOOL airPlayChapterSeek;
@property(nonatomic, copy) NSDictionary<NSNumber *, NSString *> *airPlayChapters;
@property(nonatomic, copy) NSDictionary<NSNumber *, NSString *> *localChapters;
@property(nonatomic) NSInteger chapterTitleIndex;
@property(nonatomic) NSTimeInterval nextChapterLookup;
@property(nonatomic) BOOL chaptersInvalidated;
@property(nonatomic, weak) UIAlertController *chapterDialog;
@property(nonatomic, copy) BOOL (^allowed)(BOOL external);
@property(nonatomic, copy) BOOL (^backgroundAudioAllowed)(void);
@property(nonatomic) BOOL localAudioInBackground;
@property(nonatomic, copy) BOOL (^requestPlay)(void);
@property(nonatomic, copy) void (^closed)(void);
@property(nonatomic, strong) VLCMediaPlayer *player;
@property(nonatomic) BOOL usesXvidAVI;
@property(nonatomic, strong) UIView *movie;
@property(nonatomic, strong) UIView *inlineMovie, *externalVideoHost;
@property(nonatomic, copy) BOOL (^externalDisplayAllowed)(void);
@property(nonatomic, copy) dispatch_block_t externalOutputChanged;
@property(nonatomic) BOOL externalVideoRevoked;
@property(nonatomic) NSTimeInterval externalDisconnectTime;
@property(nonatomic, strong) UITapGestureRecognizer *menuOutsideTap;
@property(nonatomic, strong) UIStackView *controls;
@property(nonatomic, strong) UIScrollView *controlsScroll;
@property(nonatomic, strong) CADisplayLink *subtitleLayoutLink;
@property(nonatomic, weak) UIView *shiftedSubtitleView;
@property(nonatomic) CGFloat subtitleClearance;
@property(nonatomic, strong) UIVisualEffectView *controlsBackdrop;
@property(nonatomic, strong) UIVisualEffect *controlsMaterial;
@property(nonatomic, strong) UIActivityIndicatorView *bufferSpinner;
@property(nonatomic, strong) UILabel *bufferLabel;
@property(nonatomic, strong) UIStackView *bufferOverlay;
@property(nonatomic) BOOL buffering, hasPlayed;
@property(nonatomic, copy) NSString *audioSwitchTrack;
@property(nonatomic) NSUInteger audioSwitchGeneration;
@property(nonatomic) BOOL audioSwitchSawBuffering, audioSwitchBuffered;
@property(nonatomic) uint64_t audioSwitchPlayed, audioSwitchDecoded, audioSwitchFrames, audioMissingPlayed;
@property(nonatomic) BOOL audioOutputMissing;
@property(nonatomic) int64_t audioSwitchPosition, audioSwitchClock, audioSwitchDecodeClock;
@property(nonatomic) NSTimeInterval audioSwitchDeadline;
@property(nonatomic, copy) NSString *transportFailure;
@property(nonatomic) BOOL hingePartiallyOpen, tabletop, portraitTabletop;
@property(nonatomic) CGRect tabletopArea;
@property(nonatomic, strong) UIStackView *portraitHeader, *portraitUtilities;
@property(nonatomic, strong) UIVisualEffectView *portraitToolbar;
@property(nonatomic, strong) UIButton *portraitClose, *portraitPictureButton, *portraitSpeedButton;
@property(nonatomic, strong) NSLayoutConstraint *portraitDeckHeight;
@property(nonatomic, strong) NSArray<NSLayoutConstraint *> *transportSizes;
@property(nonatomic, strong) UIStackView *videoIdentity;
@property(nonatomic, strong) UIStackView *transport, *tabletopUtilities;
@property(nonatomic, strong) UIButton *playButton;
@property(nonatomic, strong) NSLayoutConstraint *movieWidth, *movieHeight, *movieCenterY, *deckCenterY, *controlsHeightLimit;

@property(nonatomic) BOOL networkWaiting, networkResumePending, playRequested;
@property(nonatomic) NSTimeInterval openDeadline;
@property(nonatomic) BOOL aviFromBeginning;
@property(nonatomic) int64_t bufferPosition;
@property(nonatomic) int64_t observedClock, lastRenderedClock;
@property(nonatomic) uint64_t observedFrames, observedAudio;
@property(nonatomic) NSTimeInterval lastPlaybackProgress, lastFrameProgress, lastAudioProgress;
@property(nonatomic, strong) NSLayoutConstraint *bufferCenterX, *bufferCenterY;
@property(nonatomic, strong) UILabel *timeLabel;
@property(nonatomic, strong) NSLayoutConstraint *controlsLeading, *controlsTrailing, *controlsTop, *controlsBottom;
@property(nonatomic, strong) UILabel *message;
@property(nonatomic, strong) LGVideoTimeline *seek;
@property(nonatomic, strong) UIBarButtonItem *pictureButton;
@property(nonatomic, strong) UIButton *tabletopPictureButton;
@property(nonatomic) BOOL fullscreen;
@property(nonatomic) BOOL controlsVisible;
@property(nonatomic) BOOL systemChromeHidden;
@property(nonatomic, strong) UIView *videoHeader;
@property(nonatomic, strong) NSLayoutConstraint *deckHeaderHeight;
@property(nonatomic, strong) UILabel *videoTitle, *sourceLabel;
@property(nonatomic, strong) UIImageView *sourceIcon;
@property(nonatomic) NSUInteger chromeGeneration;
@property(nonatomic, strong) NSTimer *controlsTimer;
@property(nonatomic, strong) NSTimer *timer;
@property(nonatomic, strong) id<VLCPictureInPictureWindowControlling> pipController, captionPiP;
@property(nonatomic, strong) LGCaptionVideoDrawable *captionDrawable;
@property(nonatomic, strong) NSMutableArray<VLCRendererDiscoverer *> *discoverers;
@property(nonatomic) BOOL pipActive, subtitlePiPEnabled;
@property(nonatomic) BOOL casting;
@property(nonatomic) BOOL retired;
@property(nonatomic) BOOL retirementComplete;
@property(nonatomic, strong) NSMutableArray *retirementCallbacks;
@property(nonatomic) BOOL ended;
@property(nonatomic) BOOL lockHidden;
@property(nonatomic) BOOL interrupted;
@property(nonatomic) BOOL manualResumeRequired;
@property(nonatomic) BOOL pausePending;
@property(nonatomic) BOOL rateChangePending;
@property(nonatomic) BOOL audioSuppressed;
@property(nonatomic) BOOL resumeMuted;
@property(nonatomic) BOOL localAudioNeedsRefresh;
@property(nonatomic) BOOL holdsIdleTimer;
@property(nonatomic) BOOL surfaceVisible;
@property(nonatomic, strong) CXCallObserver *callObserver;
@property(nonatomic) int64_t lastPosition;
@property(nonatomic) int64_t progressSeek;
@property(nonatomic) NSUInteger lastAudioTrackCount, lastTextTrackCount;
@property(nonatomic, copy) NSString *optionsJSON, *queueJSON, *pictureGeometry;
@property(nonatomic, copy) void (^command)(NSString *, NSString *);
@property(nonatomic) BOOL controlsLocked, cacheApproximate;
@property(nonatomic, strong) UIButton *unlockButton;
@property(nonatomic, strong) UIView *cacheStrip, *pauseSnapshot;
@property(nonatomic, copy) NSString *languageSignature;
@property(nonatomic) CGSize lastVideoSize;
@property(nonatomic) BOOL forceMaximumHDR; // Session-only diagnostic; default uses automatic HDR.
- (void)invalidatePiPPlaybackState;
- (NSString *)trackKey:(VLCMediaPlayerTrack *)track;
- (void)revokeExternalVideo;
- (BOOL)isExternalAudioPort:(NSString *)type;
- (BOOL)protectedDataAvailable;
- (VLCMediaStats)playbackStats;
- (int64_t)nativeTimeMilliseconds;
@end

static id<VLCPictureInPictureWindowControlling> LGCreateCaptionPiP(LGVideoController *owner);

@interface LGVideoController (AudioSwitch)
- (BOOL)switchAudioTrack:(VLCMediaPlayerTrack *)track;
- (void)cancelAudioSwitch;
- (void)updateAudioSwitch;
@end

@interface LGVideoController (AirPlay)
- (void)installAirPlayControls;
- (BOOL)beginAirPlay:(AVPlayer *)player URL:(NSURL *)url title:(NSString *)title;
- (BOOL)hasAirPlay;
- (BOOL)hasEstablishedAirPlay;
- (BOOL)allowsAirPlay;
- (void)startAirPlayPlayback;
- (void)seekAirPlay:(int64_t)target;
- (void)seekAirPlay:(int64_t)target chapter:(BOOL)chapter;
- (int64_t)airPlayTime:(CMTime)time;
- (void)updateAirPlay;
- (void)finishAirPlayWithMessage:(NSString *)message;
- (BOOL)hasAirPlayAudioRoute;
- (void)updateAirPlayRoute;
- (BOOL)holdLocalPlayForAirPlay;
- (void)airPlayPreparationFailed:(NSString *)message;
- (void)showAirPlayTracks:(id)sender subtitles:(BOOL)text;
- (void)detachAirPlay;
- (void)traceAirPlay:(NSString *)event;
- (void)suspendForLock;
@end

@interface LGVideoController (PlaybackControls)
- (void)installPlaybackTools;
- (void)setting:(NSString *)key value:(id)value;
- (void)applyPlaybackOptions;
- (void)applyPlaybackRate;
- (void)applyPictureSize;
- (void)presentPlaybackDialog:(UIAlertController *)dialog;
- (void)layoutPlaybackTools;
- (NSDictionary *)playbackOptions;
- (void)emitCommand:(NSString *)name value:(NSString *)value;
- (void)playbackTools:(id)sender;
@end

@interface LGVideoController (HDRDiagnostics)
- (AVSampleBufferDisplayLayer *)sampleBufferLayer:(CALayer *)layer;
- (NSDictionary *)hdrPresentationState;
- (void)logHDRTransition:(NSString *)event;
@end

@interface LGVideoController (PausePresentation)
- (void)holdPausePresentation;
- (void)clearPausePresentation;
@end

@interface LGVideoController (InlineSubtitles)
- (void)updateInlineSubtitles;
- (void)resetInlineSubtitles;
- (CGRect)naturalSubtitleFrame:(UIView *)surface relativeTo:(UIView *)parent;
@end

typedef struct {
    CGRect safeArea;
    CGRect controlsArea;
    CGRect movieArea;
    BOOL tabletop;
    BOOL portraitTabletop;
} LGVideoLayout;

@interface LGVideoController (VideoChrome)
- (void)configureVideoView;
- (void)installVideoChrome;
- (LGVideoLayout)resolveVideoLayoutInSafeArea:(CGRect)safe;
- (void)layoutInlineMovieInArea:(CGRect)movieArea;
- (void)layoutControlDeck:(LGVideoLayout)layout margin:(CGFloat)margin poseChanged:(BOOL)poseChanged;
@end

#import "DuoDeck.m"

@implementation LGVideoController
- (void)setScreenAwake:(BOOL)awake {
    if (self.holdsIdleTimer == awake) return;
    self.holdsIdleTimer = awake;
    if (awake) {
        self.awakeLease = [[LGScreenAwakeLease alloc] init];
    } else {
        [self.awakeLease finish];
        self.awakeLease = nil;
    }
}
- (void)updateScreenAwake {
    [self setScreenAwake:!self.retired && self.surfaceVisible && self.view.window &&
        !self.lockHidden && !self.manualResumeRequired && (!self.pausePending || self.rateChangePending) &&
        !self.ended && !self.casting && !self.pipActive && self.playRequested &&
        UIApplication.sharedApplication.applicationState == UIApplicationStateActive];
}
- (void)viewDidLoad {
    [super viewDidLoad];
    [self configureVideoView];
    [self initializePlaybackClock];
    [self installVideoChrome];
    [self configureDecoder];

    // Finish installing controls before applying settings or polling the player.
    [self installPlaybackTools];
    [self installPortraitDeck];
    [self applyPlaybackOptions];
    [self startPlaybackMonitoring];
    [self observePlaybackPolicy];
}

- (void)initializePlaybackClock {
    if ([self declaredMediaEnd] > 0 && self.startMilliseconds >= 0)
        self.startMilliseconds = MIN(self.startMilliseconds, [self declaredMediaEnd] - 1);
    self.lastPosition = self.startMilliseconds;
    self.progressSeek = -1;
    self.observedClock = -1;
    self.lastPlaybackProgress = self.lastFrameProgress = NSProcessInfo.processInfo.systemUptime;
}

- (void)configureDecoder {
    // Keep 10-bit frames and their color attachments in Apple's native renderer.
    // Retain automatic fallback for formats the sample-buffer output cannot use.
    self.player = [[VLCMediaPlayer alloc] initWithOptions:@[@"--quiet", @"--no-video-title-show", @"--stats",
        @"--vout=samplebufferdisplay,any"]];
    self.subtitlePiPEnabled = NO;
    if (@available(iOS 17.4, *)) self.subtitlePiPEnabled = [[self playbackOptions][@"pip_subtitles"] boolValue];
    // Snapshot the mode for this player. Changing settings does not replace a
    // live drawable or switch PiP ownership while playback is in progress.
    if (self.subtitlePiPEnabled) {
        self.captionDrawable = [LGCaptionVideoDrawable new];
        self.captionDrawable.owner = self;
        self.player.drawable = self.captionDrawable;
    } else self.player.drawable = self;
    self.player.delegate = self;
    self.player.media = [self playbackMedia];
    self.discoverers = [NSMutableArray array];
}

- (void)startPlaybackMonitoring {
    self.timer = [NSTimer scheduledTimerWithTimeInterval:.5 target:self selector:@selector(tick:) userInfo:nil repeats:YES];
    [self tick:nil];
}

- (void)observePlaybackPolicy {
    NSNotificationCenter *center = NSNotificationCenter.defaultCenter;
    [center addObserver:self selector:@selector(backgroundNotification:) name:UIApplicationDidEnterBackgroundNotification object:nil];
    [center addObserver:self selector:@selector(foregroundNotification:) name:UIApplicationDidBecomeActiveNotification object:nil];
    [center addObserver:self selector:@selector(protectedData:) name:UIApplicationProtectedDataWillBecomeUnavailable object:nil];
    [center addObserver:self selector:@selector(protectedDataRestored:) name:UIApplicationProtectedDataDidBecomeAvailable object:nil];
    [center addObserver:self selector:@selector(foregroundNotification:) name:UIApplicationProtectedDataDidBecomeAvailable object:nil];
    [center addObserver:self selector:@selector(captureChanged:) name:UIScreenCapturedDidChangeNotification object:nil];
    [center addObserver:self selector:@selector(audioInterrupted:) name:AVAudioSessionInterruptionNotification object:nil];
    [center addObserver:self selector:@selector(audioRouteChanged:) name:AVAudioSessionRouteChangeNotification object:nil];
    self.callObserver = [[CXCallObserver alloc] init];
    [self.callObserver setDelegate:self queue:dispatch_get_main_queue()];
}

- (BOOL)prefersStatusBarHidden { return (self.tabletop || (self.fullscreen && self.systemChromeHidden)) && !self.pipActive; }
- (UIInterfaceOrientationMask)supportedInterfaceOrientations { return UIInterfaceOrientationMaskAll; }
- (BOOL)prefersHomeIndicatorAutoHidden { return (self.tabletop || (self.fullscreen && self.systemChromeHidden)) && !self.pipActive; }
- (UIRectEdge)preferredScreenEdgesDeferringSystemGestures {
    // Allow Control Center and Notification Center with one top-edge swipe,
    // even in immersive fullscreen. Keep bottom-edge protection to avoid
    // accidentally leaving the video during playback gestures.
    return (self.tabletop || (self.fullscreen && self.systemChromeHidden)) && !self.pipActive ? UIRectEdgeBottom : UIRectEdgeNone;
}
- (BOOL)gestureRecognizer:(UIGestureRecognizer *)gesture shouldReceiveTouch:(UITouch *)touch {
    if (gesture == self.menuOutsideTap) {
        UIViewController *menu = self.presentedViewController;
        return [menu isKindOfClass:UIAlertController.class] &&
            !CGRectContainsPoint(menu.view.bounds, [touch locationInView:menu.view]);
    }
    return ![touch.view isDescendantOfView:self.controlsScroll];
}
- (void)setControlsShown:(BOOL)visible {
    if (self.tabletop) visible = YES;
    if (self.controlsLocked) visible = NO;
    self.controlsVisible = visible;
    [self.view setNeedsLayout];
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
        self.systemChromeHidden = self.tabletop;
        [self setNeedsStatusBarAppearanceUpdate];
    }
    if (!hideBar) [self.navigationController setNavigationBarHidden:NO animated:NO];
    [self.view layoutIfNeeded];
    [bar layoutIfNeeded];
    [self updateInlineSubtitles];
    bar.userInteractionEnabled = !hideBar;
    bar.accessibilityElementsHidden = hideBar;
    [UIView animateWithDuration:immediate ? 0 : .2 delay:0
        options:UIViewAnimationOptionBeginFromCurrentState | UIViewAnimationOptionAllowUserInteraction
        animations:^{
            BOOL showBackdrop = shown && !self.tabletop;
            if ((self.controlsBackdrop.effect != nil) != showBackdrop)
                self.controlsBackdrop.effect = showBackdrop ? self.controlsMaterial : nil;
            self.controlsScroll.alpha = shown ? 1 : 0;
            self.videoHeader.alpha = shown ? 1 : 0;
            bar.alpha = hideBar ? 0 : 1;
        } completion:^(BOOL finished) {
            if (generation != self.chromeGeneration) return;
            self.controlsScroll.hidden = !shown;
            self.videoHeader.hidden = !shown;
            [self updateInlineSubtitles];
            // Changing status/navigation visibility earlier shrinks the safe
            // area and moves still-visible controls during their fade.
            self.systemChromeHidden = self.tabletop || !shown;
            [self.navigationController setNavigationBarHidden:hideBar animated:NO];
            [self setNeedsStatusBarAppearanceUpdate];
            [self setNeedsUpdateOfHomeIndicatorAutoHidden];
            [self setNeedsUpdateOfScreenEdgesDeferringSystemGestures];
        }];
    self.bufferOverlay.hidden = self.retired || !self.buffering || self.lockHidden || self.pipActive;
    [self scheduleControls];
}
- (void)scheduleControls {
    BOOL eligible = !self.tabletop && self.fullscreen && self.controlsVisible && !self.pipActive &&
        !self.retired && !self.lockHidden && self.view.window && !self.buffering && self.player.isPlaying && self.observedFrames > 0 && self.startMilliseconds < 0;
    if (!eligible) { [self.controlsTimer invalidate]; self.controlsTimer = nil; return; }
    // Decoder notifications must not continually postpone an existing deadline.
    if (!self.controlsTimer.valid) {
        self.controlsTimer = [NSTimer scheduledTimerWithTimeInterval:3 target:self selector:@selector(hideControls:) userInfo:nil repeats:NO];
    }
}
- (void)hideControls:(NSTimer *)timer {
    self.controlsTimer = nil;
    if (!self.buffering && self.observedFrames > 0 && self.startMilliseconds < 0 && self.player.isPlaying && !self.seek.tracking && !self.presentedViewController &&
        !self.navigationController.presentedViewController && !UIAccessibilityIsVoiceOverRunning())
        [self setControlsShown:NO];
    else [self scheduleControls];
}
- (void)toggleFullscreen:(id)sender {
    self.fullscreen = !self.fullscreen;
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
    [self resetInlineSubtitles];
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
    if (self.externalOutputChanged) self.externalOutputChanged();
}

- (CGSize)externalVideoSize {
    for (VLCMediaPlayerTrack *track in self.player.videoTracks) {
        if (!track.isSelected || !track.video.width || !track.video.height) continue;
        VLCMediaVideoTrack *video = track.video;
        CGFloat width = video.width;
        if (video.sourceAspectRatio && video.sourceAspectRatioDenominator)
            width *= (CGFloat)video.sourceAspectRatio / video.sourceAspectRatioDenominator;
        return video.orientation >= VLCMediaOrientationLeftTop
            ? CGSizeMake(video.height, width) : CGSizeMake(width, video.height);
    }
    return self.player.videoSize;
}
- (void)layoutVideoDrawable {
    if (self.externalVideoHost) {
        CGRect viewport = self.externalVideoHost.bounds;
        CGSize size = [self externalVideoSize];
        self.movie.frame = size.width > 0 && size.height > 0 && !CGRectIsEmpty(viewport)
            ? AVMakeRectWithAspectRatioInsideRect(size, viewport) : viewport;
    }
    for (UIView *surface in self.movie.subviews) surface.frame = self.movie.bounds;
    [self configureVideoDynamicRange:self.movie.layer];
}
- (BOOL)permitsExternalDisplay {
    return !self.retired && !self.restricted && !self.lockHidden && !self.externalVideoRevoked &&
        UIApplication.sharedApplication.protectedDataAvailable &&
        self.externalDisplayAllowed && self.externalDisplayAllowed();
}
- (BOOL)moveVideoToExternalHost:(UIView *)host {
    NSAssert(NSThread.isMainThread, @"Move the video drawable on the UI thread");
    if (host) {
        if ([self hasAirPlay]) return NO;
        if (![self permitsExternalDisplay]) { [self revokeExternalVideo]; return NO; }
        if (!self.surfaceVisible || !host.window || self.casting || self.pipActive) {
            [self moveVideoToExternalHost:nil];
            return NO;
        }
    }
    if (host != self.externalVideoHost) {
        if (host) self.externalDisconnectTime = 0;
        self.externalVideoHost = host;
        UIView *parent = host ?: self.inlineMovie;
        // Keep VLC's renderer, subtitle views and queued/paused frame together.
        // Changing VLC's drawable would take effect only on a new video output.
        [parent addSubview:self.movie];
        self.movie.frame = parent.bounds;
        self.movie.autoresizingMask = host ? UIViewAutoresizingNone
            : UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    }
    [self layoutVideoDrawable];
    [self applyPictureSize];
    [self updateInlineSubtitles];
    return YES;
}
- (void)externalDisplayDisconnected {
    if (![self permitsExternalDisplay]) { [self revokeExternalVideo]; return; }
    // UIKit and AVAudioSession report the same loss independently and can
    // deliver either callback first. Remember a recent detach for the latter.
    self.externalDisconnectTime = NSProcessInfo.processInfo.systemUptime;
    [self moveVideoToExternalHost:nil];
}
- (BOOL)continuesAfterDisplayDisconnect {
    return [self permitsExternalDisplay] && !self.casting && !self.pipActive &&
        (self.externalVideoHost || (self.externalDisconnectTime > 0 &&
         NSProcessInfo.processInfo.systemUptime - self.externalDisconnectTime < 2));
}
- (void)revokeExternalVideo {
    if (!self.externalVideoHost) return;
    self.externalVideoRevoked = YES;
    self.externalDisconnectTime = 0;
    self.movie.hidden = YES;
    [self pause];
    [self clearPausePresentation];
    [self moveVideoToExternalHost:nil];
    if (self.externalOutputChanged) self.externalOutputChanged();
}
- (NSString *)externalDisplayDiagnosticJSON {
    CGRect frame = self.movie.frame;
    CGSize size = [self externalVideoSize];
    AVSampleBufferDisplayLayer *layer = [self sampleBufferLayer:self.movie.layer];
    BOOL ready = self.movie.subviews.count > 0 && !self.movie.hidden;
    if (@available(iOS 17.4, *)) {
        if (layer) ready = layer.readyForDisplay && !self.movie.hidden;
    }
    NSDictionary *value = @{ @"rect": @[@(frame.origin.x), @(frame.origin.y), @(frame.size.width), @(frame.size.height)],
        @"source_size": @[@(size.width), @(size.height)], @"frame_ready": @(ready),
        @"playing": @(self.player.isPlaying), @"position_ms": @([self positionMilliseconds]) };
    return [[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:value options:0 error:nil]
                                 encoding:NSUTF8StringEncoding];
}
- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    CGRect safe = self.view.safeAreaLayoutGuide.layoutFrame;
    NSDictionary *readerLayout = [self playbackOptions][@"reader_layout"];
    CGFloat margin = readerLayout[@"margin"] ? [readerLayout[@"margin"] doubleValue] : 12;
    LGVideoLayout layout = [self resolveVideoLayoutInSafeArea:safe];

    BOOL poseChanged = self.tabletop != layout.tabletop || self.portraitTabletop != layout.portraitTabletop;
    self.tabletop = layout.tabletop;
    self.portraitTabletop = layout.portraitTabletop;
    [self layoutInlineMovieInArea:layout.movieArea];
    // VLCKit installs its surface through VLCDrawable. Resize it explicitly
    // after rotations, folds and bar changes.
    [self layoutVideoDrawable];
    [self layoutControlDeck:layout margin:margin poseChanged:poseChanged];
    [self layoutPlaybackTools];
    [self updateInlineSubtitles];
}

- (void)updateItem:(UIBarButtonItem *)button label:(NSString *)label {
    NSDictionary *symbols = @{@"Playback": @"slider.horizontal.3", @"Audio tracks": @"speaker.wave.2", @"Subtitles": @"captions.bubble", @"Fill view": @"arrow.up.left.and.arrow.down.right",
        @"Fit view": @"arrow.down.right.and.arrow.up.left", @"More playback options": @"ellipsis",
        @"Chapters": @"list.bullet", @"Done": @"xmark"};
    button.image = [UIImage systemImageNamed:symbols[label]];
    if (button == self.pictureButton && self.portraitPictureButton) {
        UIButtonConfiguration *config = self.portraitPictureButton.configuration;
        config.image = button.image;
        config.title = [label isEqualToString:@"Fit view"] ? @"Fit" : @"Fill";
        self.portraitPictureButton.configuration = config;
        self.portraitPictureButton.accessibilityLabel = label;
    }
    if (button == self.pictureButton && self.tabletopPictureButton) {
        UIButtonConfiguration *config = self.tabletopPictureButton.configuration;
        config.image = [UIImage systemImageNamed:symbols[label]];
        config.title = label;
        self.tabletopPictureButton.configuration = config;
        self.tabletopPictureButton.accessibilityLabel = label;
    }
    button.title = label;
    button.accessibilityLabel = label;
    button.accessibilityIdentifier = [@"video." stringByAppendingString:label];
    button.accessibilityHint = [label isEqualToString:@"Done"] ? @"Close video player" : nil;
}

- (void)updatePlayButton {
    NSString *label = self.playRequested ? @"Pause" : @"Play";
    if (![self.playButton.accessibilityLabel isEqualToString:label]) {
        UIButtonConfiguration *config = self.playButton.configuration;
        config.image = [UIImage systemImageNamed:self.playRequested ? @"pause.fill" : @"play.fill"
                              withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:28 weight:UIImageSymbolWeightSemibold]];
        self.playButton.configuration = config;
        self.playButton.accessibilityLabel = label;
    }
}

- (UIButton *)deckButton:(NSString *)label symbol:(NSString *)symbol selector:(SEL)selector primary:(BOOL)primary {
    UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
    UIButtonConfiguration *config = primary ? [UIButtonConfiguration filledButtonConfiguration] : [UIButtonConfiguration tintedButtonConfiguration];
    config.image = [UIImage systemImageNamed:symbol withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:primary ? 28 : 24 weight:UIImageSymbolWeightSemibold]];
    config.baseForegroundColor = primary ? UIColor.blackColor : UIColor.whiteColor;
    config.baseBackgroundColor = primary ? UIColor.whiteColor : [UIColor colorWithWhite:.25 alpha:1];
    config.cornerStyle = UIButtonConfigurationCornerStyleCapsule;
    button.configuration = config;
    button.accessibilityLabel = label;
    button.accessibilityIdentifier = [@"video.deck." stringByAppendingString:label];
    [button.widthAnchor constraintEqualToConstant:primary ? 56 : 48].active = YES;
    [button.heightAnchor constraintEqualToConstant:primary ? 56 : 48].active = YES;
    [button addTarget:self action:selector forControlEvents:UIControlEventTouchUpInside];
    return button;
}

- (UIBarButtonItem *)item:(NSString *)title selector:(SEL)selector {
    UIBarButtonItem *button = [[UIBarButtonItem alloc] initWithImage:nil style:UIBarButtonItemStylePlain target:self action:selector];
    [self updateItem:button label:title];
    if (@available(iOS 27.0, *)) {
        button.visibilityPriority = [title isEqualToString:@"Done"] ? 1000 : 500;
    }
    return button;
}

- (BOOL)protectedDataAvailable { return UIApplication.sharedApplication.protectedDataAvailable; }

- (BOOL)permitsLocalBackgroundAudio {
    return !self.restricted && !self.lockHidden && ![self hasAirPlay] && !self.pipActive &&
        !self.casting && !self.externalVideoHost && !self.externalVideoRevoked &&
        self.backgroundAudioAllowed && self.backgroundAudioAllowed();
}

- (BOOL)canPlay:(BOOL)external {
    if (self.retired || self.interrupted || [self hasActiveCall] || (external && self.restricted)) return NO;
    if (self.restricted && (self.lockHidden || UIApplication.sharedApplication.applicationState == UIApplicationStateBackground)) return NO;
    if (self.localAudioInBackground && (external || ![self permitsLocalBackgroundAudio])) return NO;
    if (![self protectedDataAvailable] && !([self hasEstablishedAirPlay] && [self allowsAirPlay]) &&
        (external || !self.localAudioInBackground || !self.playRequested)) return NO;
    if (self.restricted && (self.view.window.screen.isCaptured || [self hasExternalAudio])) return NO;
    return self.allowed && self.allowed(external);
}

- (void)togglePlay:(id)sender {
    if (self.controlsLocked) return;
    if ([self hasAirPlay]) {
        if (!self.playRequested) [self startAirPlayPlayback];
        else [self pause];
        return;
    }
    if (self.playRequested) [self pause]; else [self startByUser];
}
- (void)seekToMilliseconds:(int64_t)target {
    if ([self hasAirPlay]) { [self seekAirPlay:target]; return; }
    if (self.controlsLocked || ![self canPlay:NO]) return;
    int64_t duration = [self durationMilliseconds];
    if (!self.player.isSeekable && duration <= 0) return;
    target = MAX(0, target);
    if (duration > 0) target = MIN(target, MAX(0, duration - 1));
    if (target > 0) self.aviFromBeginning = NO;
    if (self.audioOnlyInput || [self isDeclaredAudioTail:target]) {
        self.audioOnlyInput = NO; // Every explicit seek gives video another chance.
        self.inputNeedsRestart = YES;
    }
    if (self.inputNeedsRestart || !self.player.isSeekable || self.player.state == VLCMediaPlayerStateError ||
        self.player.state == VLCMediaPlayerStateStopped) {
        // An input stuck opening a saved seek can lose seekability. Keep a
        // known-duration movie recoverable without editing its saved state or
        // forcing playback when the user had paused it.
        BOOL resume = self.playRequested && !self.manualResumeRequired;
        [self cancelAudioSwitch];
        self.ended = NO;
        self.inputNeedsRestart = YES;
        self.startMilliseconds = self.lastPosition = target;
        self.progressSeek = target;
        self.resumeSeekSubmitted = NO;
        [self updateTimeline];
        if (resume) [self startByUser];
        else [self showStatus:@"Position selected. Press Play to retry."];
        return;
    }
    // VLC may retain the old reported clock while paused. Preserve the requested
    // position for controls/checkpoints and apply it again on explicit Play.
    self.ended = NO;
    self.lastPlaybackProgress = self.lastFrameProgress = NSProcessInfo.processInfo.systemUptime;
    self.lastRenderedClock = target;
    if (self.audioSwitchTrack.length) {
        self.audioSwitchPosition = target;
        self.audioSwitchGeneration++;
        self.audioSwitchSawBuffering = self.audioSwitchBuffered = NO;
        self.audioSwitchPlayed = [self playbackStats].playedAudioBuffers;
        self.audioSwitchDecoded = [self playbackStats].decodedAudio;
        self.audioSwitchDeadline = NSProcessInfo.processInfo.systemUptime + 20;
    }
    if (self.networkResumePending) self.bufferPosition = target;
    self.startMilliseconds = target;
    self.resumeSeekSubmitted = self.player.isPlaying;
    self.seekSubmittedAt = NSProcessInfo.processInfo.systemUptime;
    self.seekDeadline = self.seekSubmittedAt + 20;
    self.seekAudioBaseline = [self playbackStats].playedAudioBuffers;
    self.seekFrameBaseline = [self playbackStats].displayedPictures;
    self.progressSeek = target;
    self.player.time = [VLCTime timeWithNumber:@(target)];
}
- (void)skipMilliseconds:(int64_t)offset { [self seekToMilliseconds:[self positionMilliseconds] + offset]; }
- (void)back:(id)sender { [self skipMilliseconds:-10000]; }
- (void)forward:(id)sender { [self skipMilliseconds:10000]; }
- (void)seekChanged:(UISlider *)slider {
    int64_t duration = [self durationMilliseconds];
    if (duration <= 0) return;
    [self seekToMilliseconds:(int64_t)(slider.value * duration)];
    [self.controlsTimer invalidate]; self.controlsTimer = nil;
    [self scheduleControls];
}
- (void)done:(id)sender { if (self.closed) self.closed(); }
- (void)pause {
    self.openDeadline = 0;
    if (self.audioSwitchTrack.length && self.startMilliseconds < 0)
        self.startMilliseconds = self.audioSwitchPosition;
    [self cancelAudioSwitch];
    if ([self hasAirPlay]) {
        [self.airPlayPlayer pause];
        self.playRequested = NO;
        self.airPlayStartDeadline = 0;
        self.airPlaySystemPaused = NO;
        [self updatePlayButton];
        [self setControlsShown:YES];
        return;
    }
    // VLC can report an unavailable audio output as muted before the input
    // opens. Keep user intent separate from that transient decoder state.
    self.audioSuppressed = YES;
    self.player.audio.muted = YES; // Silence the decoder before updating the paused UI.
    self.rateChangePending = NO;
    [self logHDRTransition:@"pause-request"];
    [self holdPausePresentation];
    [self setScreenAwake:NO];
    [self setControlsShown:YES];
    // Capture the displayed position before VLC processes an asynchronous pause.
    // Never use a free-running audio clock as the resume target during a render stall.
    if (self.startMilliseconds < 0) {
        NSTimeInterval age = NSProcessInfo.processInfo.systemUptime - self.lastFrameProgress;
        int64_t position = [self positionMilliseconds];
        if (self.observedFrames > 0 && age >= 2.0 &&
            NSProcessInfo.processInfo.systemUptime - self.lastAudioProgress >= 2.0 &&
            (self.observedAudio == 0 || NSProcessInfo.processInfo.systemUptime - self.lastPlaybackProgress >= 2.0) &&
            self.lastRenderedClock >= 0)
            position = self.lastRenderedClock;
        self.startMilliseconds = MAX(0, position);
    }
    NSLog(@"[VideoPlayback] pause target=%lld waiting=%d frames=%llu", self.startMilliseconds, self.networkWaiting, (unsigned long long)self.observedFrames);
    // VLCKit pause is an explicit pause, but coalesce duplicate OS/lifecycle events.
    self.manualResumeRequired = YES;
    self.playRequested = NO;
    [self updatePlayButton];
    if (self.networkResumePending) self.startMilliseconds = self.bufferPosition;
    self.networkResumePending = NO;
    self.buffering = NO;
    self.bufferOverlay.hidden = YES;
    [self.bufferSpinner stopAnimating];
    if (self.player.isPlaying && !self.pausePending) {
        self.pausePending = YES;
        [self.player pause];
    }
    [self invalidatePiPPlaybackState];
}
- (BOOL)hasExternalAudio {
    for (AVAudioSessionPortDescription *output in AVAudioSession.sharedInstance.currentRoute.outputs) {
        if ([self isExternalAudioPort:output.portType]) return YES;
    }
    return NO;
}
- (BOOL)isExternalAudioPort:(NSString *)type {
    return [type isEqualToString:AVAudioSessionPortAirPlay] ||
        [type isEqualToString:AVAudioSessionPortHDMI] || [type isEqualToString:AVAudioSessionPortDisplayPort];
}
- (BOOL)hasActiveCall {
    for (CXCall *call in self.callObserver.calls) if (!call.hasEnded) return YES;
    return NO;
}
- (BOOL)isDeclaredAudioTail:(int64_t)target {
    NSDictionary *bounds = [self playbackOptions][@"media_bounds"];
    if (![bounds isKindOfClass:NSDictionary.class]) return NO;
    NSArray *video = bounds[@"video"], *audio = bounds[@"audio"];
    if (![video isKindOfClass:NSArray.class] || ![audio isKindOfClass:NSArray.class]) return NO;
    if (target < 0 || !video.count || !audio.count || self.casting || self.pipActive) return NO;
    int64_t videoEnd = 0, audioEnd = INT64_MAX;
    for (NSDictionary *track in video) {
        if (![track isKindOfClass:NSDictionary.class] || ![track[@"end_ms"] isKindOfClass:NSNumber.class]) return NO;
        videoEnd = MAX(videoEnd, [track[@"end_ms"] longLongValue]);
    }
    for (NSDictionary *track in audio) {
        if (![track isKindOfClass:NSDictionary.class] || ![track[@"end_ms"] isKindOfClass:NSNumber.class]) return NO;
        audioEnd = MIN(audioEnd, [track[@"end_ms"] longLongValue]);
    }
    return videoEnd > 0 && target >= videoEnd && target < audioEnd;
}
- (VLCMedia *)playbackMedia {
    self.aviFromBeginning = self.startMilliseconds <= 0 &&
        [[NSURL URLWithString:self.videoURL].pathExtension.lowercaseString isEqualToString:@"avi"];
    if ([self isDeclaredAudioTail:self.startMilliseconds]) {
        self.audioOnlyInput = YES;
    }
    VLCMedia *media = [VLCMedia mediaWithURL:[NSURL URLWithString:self.videoURL]];
    self.openingSeekPending = self.startMilliseconds >= 0;
    self.lastPlaybackStats = (VLCMediaStats){0};
    self.statisticsMedia = nil;
    self.resumeSeekSubmitted = NO;
    self.seekSubmittedAt = 0;
    self.seekDeadline = 0;
    // Indexed MKV seeks must use the embedded cues instead of scanning every
    // preceding cluster over the retained provider's HTTP range transport.
    if ([[NSURL URLWithString:self.videoURL].pathExtension.lowercaseString isEqualToString:@"mkv"])
        [media addOption:@":demux=mkv_trusted,mkv"];
    // Native AVI packetization can send old packed Xvid to VideoToolbox,
    // which starts with badly damaged pictures. FFmpeg's AVI demuxer keeps
    // these inputs on avcodec without changing the audio or display route.
    if (self.usesXvidAVI) {
        [media addOption:@":demux=avformat,avi"];
        [media addOption:@":avformat-format=avi"];
    }
    // VLC 4 start-time clips the timeline and duration. Seek the opening
    // input instead so timestamps and later seeks retain the original origin.
    [media addOption:@":network-caching=6000"];
    // A local audio-only tail can be shorter than the normal file cache.
    // Give VLC time to establish its output clock before the demuxer reaches EOF.
    [media addOption:self.audioOnlyInput ? @":file-caching=250" : @":file-caching=1500"];
    // Cloud starvation makes software-decoded interframe AVI arrive late.
    // Decode complete frames instead of catching up with partial pictures, and
    // retain the last good picture when the decoder flags damaged output.
    [media addOption:@":no-avcodec-hurry-up"];
    [media addOption:@":no-avcodec-corrupted"];
    [media addOption:@":audio-time-stretch"];
    if (self.audioOnlyInput) [media addOption:@":no-video"];
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
- (BOOL)recoverEarlyAudioEnd {
    // VLC can stop at the exhausted video's clock even though the container
    // and decoded audio extend further. Retry only a terminal early end with
    // actual audio output; never disable video on a slow/buffering input.
    if (self.startMilliseconds < 0 || self.audioOnlyInput || !self.playRequested || self.manualResumeRequired ||
        self.transportFailure || self.networkWaiting || self.audioSwitchTrack.length ||
        self.networkResumePending || self.retired || ![self canPlay:NO]) return NO;
    int64_t duration = [self durationMilliseconds];
    int64_t clock = [self nativeTimeMilliseconds];
    int64_t target = self.startMilliseconds >= 0 ? self.startMilliseconds : MAX(0, self.lastPosition);
    if (clock < 0 || duration <= clock + 1000 || target >= duration ||
        [self playbackStats].playedAudioBuffers == 0) return NO;
    self.audioOnlyInput = YES;
    self.inputNeedsRestart = YES;
    self.startMilliseconds = self.lastPosition = target;
    [self startByUser];
    [self showStatus:@"Continuing audio. Seek back to restore video."];
    return YES;
}
- (void)playbackFailed {
    int64_t position = MAX(0, self.lastPosition);
    [self pause];
    self.startMilliseconds = position;
    [self showStatus:self.transportFailure ?: @"Playback stopped unexpectedly. Press Play to retry from this position."];
}
- (BOOL)hasDecodedMedia {
    VLCMediaStats stats = [self playbackStats];
    return stats.decodedVideo > 0 || stats.decodedAudio > 0 ||
        stats.displayedPictures > 0 || stats.playedAudioBuffers > 0;
}
- (void)failOpening:(BOOL)timedOut {
    NSString *message = self.transportFailure;
    if (!message) {
        if (timedOut) message = self.networkWaiting
            ? @"The video source did not respond in time. Check the connection and press Play to retry."
            : @"Playback did not start in time. Press Play to retry or open another copy.";
        else message = [self durationMilliseconds] > 0
            ? @"No playable audio or video was found. Try a supported codec or another copy."
            : @"Could not open this video. Its container or codecs may be unsupported, or the file may be damaged.";
    }
    [self playbackFailed];
    self.inputNeedsRestart = YES;
    [self showStatus:message];
}
- (void)startByUser {
    if ([self hasAirPlay]) { [self startAirPlayPlayback]; return; }
    if ([self holdLocalPlayForAirPlay]) return;
    self.airPlayResumeLocal = NO;
    if (self.externalVideoHost && ![self permitsExternalDisplay]) [self revokeExternalVideo];
    if (!self.restricted && self.externalVideoRevoked &&
        (!self.externalDisplayAllowed || !self.externalDisplayAllowed())) return;
    if (!self.requestPlay || !self.requestPlay() || ![self canPlay:NO]) return;
    NSError *error = nil;
    AVAudioSession *audio = AVAudioSession.sharedInstance;
    if (![audio setCategory:AVAudioSessionCategoryPlayback error:&error] ||
        ![audio setActive:YES error:&error]) return;
    if (![self canPlay:NO] || [self holdLocalPlayForAirPlay]) return; // Activation can change the selected output.
    self.externalVideoRevoked = NO;
    [self revealSurface];
    if (self.externalOutputChanged) self.externalOutputChanged();
    BOOL freshInput = self.ended || self.inputNeedsRestart || self.player.state == VLCMediaPlayerStateError || self.player.state == VLCMediaPlayerStateStopped;
    if (freshInput) {
        if (self.ended) { self.startMilliseconds = 0; self.audioOnlyInput = NO; }
        else if (self.startMilliseconds < 0 && self.hasPlayed) self.startMilliseconds = MAX(0, self.lastPosition);
        self.ended = NO;
        self.hasPlayed = NO;
        self.inputNeedsRestart = NO;
        self.languageSignature = nil;
        self.lastAudioTrackCount = self.lastTextTrackCount = 0;
        self.player.media = [self playbackMedia];
    }
    self.transportFailure = nil;
    self.message.text = @"";
    self.message.hidden = YES;
    self.manualResumeRequired = NO;
    self.pausePending = NO;
    if (self.audioSuppressed) { self.player.audio.muted = self.resumeMuted; self.audioSuppressed = NO; }
    self.playRequested = YES;
    VLCMediaStats stats = [self playbackStats];
    self.openDeadline = stats.displayedPictures > 0 || stats.playedAudioBuffers > 0
        ? 0 : NSProcessInfo.processInfo.systemUptime + 20;
    if (self.startMilliseconds >= 0) self.seekDeadline = NSProcessInfo.processInfo.systemUptime + 20;
    if (self.audioSwitchTrack.length) {
        // Paused preroll can advance VLC's reported clock while the displayed
        // checkpoint stays held. Reflush at that checkpoint on explicit Play.
        self.audioSwitchGeneration++;
        self.audioSwitchSawBuffering = self.audioSwitchBuffered = NO;
        self.audioSwitchDeadline = NSProcessInfo.processInfo.systemUptime + 20;
        self.player.time = [VLCTime timeWithNumber:@([self positionMilliseconds])];
    }
    [self clearPausePresentation];
    // Resume an already-open paused input immediately. Fresh inputs are
    // positioned as soon as the native Opening event arrives.
    if (!freshInput && self.startMilliseconds >= 0 && self.player.isPlaying) {
        self.player.time = [VLCTime timeWithNumber:@(self.startMilliseconds)];
        self.resumeSeekSubmitted = YES;
        self.localAudioNeedsRefresh = NO;
    }
    self.lastPlaybackProgress = self.lastFrameProgress = NSProcessInfo.processInfo.systemUptime;
    [self updatePlayButton];
    self.networkResumePending = NO;
    NSLog(@"[VideoPlayback] play target=%lld current=%lld", self.startMilliseconds, [self nativeTimeMilliseconds]);
    [self logHDRTransition:@"play-request"];
    if (!self.rateChangePending && (freshInput || !self.player.isPlaying)) [self.player play];
    [self tick:nil];
    if ([self.message.text isEqualToString:@"Ready. Press Play to start."]) {
        self.message.text = @"";
        self.message.hidden = YES;
    }
}
// A slow prefetch is only a hint. VLC owns decoder recovery; do not
// pause or seek merely because the producer delivered another chunk.
- (void)setNetworkWaiting:(BOOL)waiting {
    if (self.retired || _networkWaiting == waiting) return;
    _networkWaiting = waiting;
    // HTTP read-ahead availability is not decoded-video readiness. In particular,
    // do not pause VLC or restart it when a single chunk arrives.
    NSLog(@"[VideoPlayback] networkWait=%d clock=%lld frames=%llu", waiting,
          [self nativeTimeMilliseconds], (unsigned long long)self.observedFrames);
}
- (void)updatePlaybackProgress {
    NSTimeInterval now = NSProcessInfo.processInfo.systemUptime;
    int64_t clock = [self nativeTimeMilliseconds];
    VLCMediaStats statistics = [self playbackStats];
    uint64_t frames = statistics.displayedPictures;
    uint64_t audio = statistics.playedAudioBuffers;
    BOOL newAudio = audio > self.observedAudio;
    if (newAudio) self.lastAudioProgress = now;
    self.observedAudio = audio;
    BOOL newFrame = frames > self.observedFrames;
    BOOL statsReset = frames < self.observedFrames;
    if (newFrame) {
        self.lastRenderedClock = clock;
        self.lastFrameProgress = now;
    }
    if (newFrame || clock != self.observedClock) self.lastPlaybackProgress = now;
    if (statsReset) self.lastFrameProgress = now; // New input resets VLC counters.
    self.observedFrames = frames;
    self.observedClock = clock;
    // When VLC does not expose picture stats, fall back to clock progress and
    // transport starvation rather than leaving the spinner stuck forever.
    BOOL missingFrames = frames == 0 && self.observedFrames == 0;
    // A container can legitimately outlast its video track. Fresh audio output
    // is progress too, including an audio-only tail reached by a saved seek.
    BOOL frameStall = !missingFrames && (now - self.lastFrameProgress >= 2.5) &&
        now - self.lastAudioProgress >= 2.5 &&
        (audio == 0 || now - self.lastPlaybackProgress >= 2.5);
    BOOL fallbackStall = missingFrames && now - self.lastAudioProgress >= 3.0 &&
        (now - self.lastPlaybackProgress >= 3.0 ||
         (self.networkWaiting && now - self.lastFrameProgress >= 3.0));
    BOOL switchingAudio = self.audioSwitchTrack.length && self.playRequested;
    BOOL stalled = switchingAudio || (self.playRequested && !self.manualResumeRequired && !self.ended &&
        (!self.pausePending || self.rateChangePending) && (frameStall || fallbackStall));
    self.bufferLabel.text = switchingAudio ? @"Switching audio…" : @"";
    self.bufferLabel.hidden = !switchingAudio;
    self.bufferSpinner.accessibilityLabel = switchingAudio ? @"Switching audio" : @"Buffering video";
    if (stalled && self.transportFailure) { [self playbackFailed]; return; }
    BOOL changed = self.buffering != stalled;
    self.buffering = stalled;
    self.bufferOverlay.hidden = !stalled || self.lockHidden || self.pipActive;
    if (stalled) {
        [self.bufferSpinner startAnimating];
        if (changed) {
            NSLog(@"[VideoPlayback] stalled clock=%lld renderedClock=%lld frames=%llu waiting=%d",
                  clock, self.lastRenderedClock, (unsigned long long)frames, self.networkWaiting);
            [self setControlsShown:YES];
        }
    } else {
        [self.bufferSpinner stopAnimating];
        if (changed) {
            NSLog(@"[VideoPlayback] recovered clock=%lld frames=%llu", clock, (unsigned long long)frames);
            [self scheduleControls];
        }
    }
}
- (void)audioInterrupted:(NSNotification *)notification {
    NSUInteger type = [notification.userInfo[AVAudioSessionInterruptionTypeKey] unsignedIntegerValue];
    self.interrupted = type == AVAudioSessionInterruptionTypeBegan;
    [self traceAirPlay:self.interrupted ? @"interruption-began" : @"interruption-ended"];
    [self pause]; // Ignore ShouldResume, including after an OS-initiated pause.
}
- (void)audioRouteChanged:(NSNotification *)notification {
    NSUInteger reason = [notification.userInfo[AVAudioSessionRouteChangeReasonKey] unsignedIntegerValue];
    AVAudioSessionRouteDescription *previous = notification.userInfo[AVAudioSessionRouteChangePreviousRouteKey];
    dispatch_async(dispatch_get_main_queue(), ^{
        for (AVAudioSessionPortDescription *port in previous.outputs)
            if ([port.portType isEqualToString:AVAudioSessionPortAirPlay]) self.localAudioNeedsRefresh = YES;
        if (self.airPlayAvailable && ([self hasAirPlay] || self.airPlayPreparing ||
            [self hasAirPlayAudioRoute] || self.airPlayResumeLocal || self.airPlayRouteDeadline > 0)) {
            if (reason != AVAudioSessionRouteChangeReasonNoSuitableRouteForCategory) {
                if ([self hasAirPlay]) {
                    [self traceAirPlay:@"audio-route-change"];
                    [self updateAirPlay];
                } else [self updateAirPlayRoute];
                return;
            }
        }
        BOOL lostDisplay = reason == AVAudioSessionRouteChangeReasonOldDeviceUnavailable &&
            previous.outputs.count == 1 && [self isExternalAudioPort:previous.outputs.firstObject.portType] &&
            AVAudioSession.sharedInstance.currentRoute.outputs.count && [self continuesAfterDisplayDisconnect];
        if (!self.retired && ((reason == AVAudioSessionRouteChangeReasonOldDeviceUnavailable && !lostDisplay) ||
            reason == AVAudioSessionRouteChangeReasonNoSuitableRouteForCategory ||
            (self.restricted && [self hasExternalAudio]))) [self pause];
    });
}
- (void)callObserver:(CXCallObserver *)observer callChanged:(CXCall *)call {
    [self pause]; // Ringing banners and Continuity calls need not background a scene.
}
- (void)suspendForLock {
    if (self.lockHidden) return;
    self.lockHidden = YES;
    [self detachAirPlay];
    [self revokeExternalVideo];
    [self.captionPiP stopPictureInPicture];
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
    self.movie.hidden = self.localAudioInBackground || [self hasAirPlay] || self.externalVideoRevoked ||
        (self.restricted && self.view.window.screen.isCaptured);
}
- (BOOL)continueLocalAudioInBackground {
    if (!self.playRequested || self.manualResumeRequired || self.retired || self.interrupted ||
        [self hasActiveCall] || ![self permitsLocalBackgroundAudio] || !self.allowed || !self.allowed(NO)) return NO;
    self.localAudioInBackground = YES;
    // Keep the input and caption tracks attached. The native display layer
    // handles the suspended presentation and flushes on activation.
    self.movie.hidden = YES;
    return YES;
}
- (void)background {
    [self traceAirPlay:@"background"];
    [self setScreenAwake:NO];
    if (self.restricted) [self suspendForLock];
    else if (!self.pipActive && !self.casting && ![self hasEstablishedAirPlay] &&
             ![self continueLocalAudioInBackground]) [self pause];
}
- (void)backgroundNotification:(NSNotification *)notification { [self background]; }
- (void)foregroundNotification:(NSNotification *)notification {
    if ([self hasAirPlay]) {
        [self traceAirPlay:@"foreground"];
        [self updateAirPlay];
    }
    if (!self.localAudioInBackground || UIApplication.sharedApplication.applicationState != UIApplicationStateActive ||
        ![self protectedDataAvailable]) return;
    self.localAudioInBackground = NO;
    if (![self canPlay:NO]) { [self pause]; return; }
    [self revealSurface];
    [self updateScreenAwake];
}
- (void)protectedData:(NSNotification *)notification {
    [self traceAirPlay:@"protected-data-unavailable"];
    if (self.restricted) [self suspendForLock];
    else if ([self hasAirPlay]) {
        // Device lock does not revoke an ordinary movie already playing on TV.
        // Keep checking the source grant; do not start a new handoff while locked.
        if ([self hasEstablishedAirPlay] && [self allowsAirPlay] && [self canPlay:NO]) {
            [self setScreenAwake:NO];
            return;
        }
        [self detachAirPlay];
        [self revealSurface];
    } else {
        [self setScreenAwake:NO];
        if (![self continueLocalAudioInBackground]) [self pause];
    }
}
- (void)protectedDataRestored:(NSNotification *)notification {
    [self traceAirPlay:@"protected-data-available"];
}
- (void)captureChanged:(NSNotification *)notification {
    if (self.restricted && self.view.window.screen.isCaptured) {
        [self pause]; [self clearPausePresentation]; self.movie.hidden = YES;
    } else if (!self.lockHidden && !self.localAudioInBackground && ![self hasAirPlay] &&
               !self.externalVideoRevoked && [self canPlay:NO]) self.movie.hidden = NO;
}
- (int64_t)progressPosition {
    if (self.ended) return 0;
    if ([self hasAirPlay]) return self.airPlayAdvanced && self.airPlaySeekTarget < 0 ?
        self.airPlayConfirmedPosition : -1;
    if (self.audioSwitchTrack.length || self.progressSeek >= 0 || self.networkResumePending ||
        self.resumeSeekSubmitted || self.startMilliseconds >= 0)
        return -1;
    return [self nativeTimeMilliseconds];
}
- (int64_t)positionMilliseconds {
    if (self.ended) return 0;
    if ([self hasAirPlay]) {
        if (self.airPlaySeekTarget >= 0) return self.airPlaySeekTarget;
        if (!self.airPlayWasExternal) return self.airPlayStartPosition;
        int64_t current = [self airPlayTime:self.airPlayPlayer.currentTime];
        return current >= 0 ? current : MAX(0, self.lastPosition);
    }
    if (self.networkResumePending) return self.bufferPosition;
    if (self.startMilliseconds >= 0) return self.startMilliseconds;
    if (self.audioSwitchTrack.length) return self.audioSwitchPosition;
    int64_t value = [self nativeTimeMilliseconds];
    // VLC can reset its clock during teardown before notifying us that it
    // stopped. Keep the last playback position for EOF detection and retry.
    if (value == 0 && (self.player.state == VLCMediaPlayerStateStopping ||
                       self.player.state == VLCMediaPlayerStateStopped)) return self.lastPosition;
    return value >= 0 ? value : self.lastPosition;
}
- (int64_t)declaredMediaEnd {
    NSDictionary *bounds = [self playbackOptions][@"media_bounds"];
    id declared = [bounds isKindOfClass:NSDictionary.class] ? bounds[@"end_ms"] : nil;
    int64_t end = [declared isKindOfClass:NSNumber.class] ? [declared longLongValue] : 0;
    return end > 0 ? end : 0;
}
- (int64_t)durationMilliseconds {
    int64_t end = [self declaredMediaEnd];
    if (end > 0) return end; // Per-A/V declarations exclude subtitle-only container tails.
    int64_t duration = [self hasAirPlay] ? [self airPlayTime:self.airPlayPlayer.currentItem.duration] :
        self.player.media.length.value.longLongValue;
    if (duration > 0) self.knownDuration = duration;
    return MAX(0, self.knownDuration);
}
- (int64_t)nativeTimeMilliseconds {
    // VLCKit's time property can remain at an optimistic seek target while
    // the native clock is still prerolling. UI holds use startMilliseconds.
    __attribute__((objc_precise_lifetime)) VLCMediaPlayer *player = self.player;
    libvlc_media_player_t *instance = [player libVLCMediaPlayer];
    if (!instance) return -1;
    int64_t value = libvlc_media_player_get_time(instance);
    return value >= 0 ? value / 1000 : -1;
}
- (VLCMediaStats)playbackStats {
    // VLCKit's statistics getter ignores the C API's unavailable result.
    // Retain the exact input and only cache a successful, initialized sample.
    __attribute__((objc_precise_lifetime)) VLCMedia *media = self.player.media;
    if (media != self.statisticsMedia) {
        self.lastPlaybackStats = (VLCMediaStats){0};
        self.statisticsMedia = media;
    }
    libvlc_media_stats_t value = {0};
    libvlc_media_t *descriptor = [media libVLCMediaDescriptor];
    if (descriptor && libvlc_media_get_stats(descriptor, &value)) {
        self.lastPlaybackStats = (VLCMediaStats){
            .readBytes = value.i_read_bytes, .inputBitrate = value.f_input_bitrate,
            .demuxReadBytes = value.i_demux_read_bytes, .demuxBitrate = value.f_demux_bitrate,
            .demuxCorrupted = value.i_demux_corrupted, .demuxDiscontinuity = value.i_demux_discontinuity,
            .decodedVideo = value.i_decoded_video, .decodedAudio = value.i_decoded_audio,
            .displayedPictures = value.i_displayed_pictures, .latePictures = value.i_late_pictures,
            .lostPictures = value.i_lost_pictures, .playedAudioBuffers = value.i_played_abuffers,
            .lostAudioBuffers = value.i_lost_abuffers};
    }
    return self.lastPlaybackStats;
}
- (BOOL)completed { return self.ended; }
- (NSString *)playbackDiagnosticJSON {
    VLCMediaStats stats = [self playbackStats];
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
    if ([self hasAirPlay]) {
        [self updateAirPlay];
        [self updateTimeline];
        return;
    }
    [self updateAirPlayRoute];
    if (self.openDeadline > 0) {
        VLCMediaStats stats = [self playbackStats];
        if (stats.displayedPictures > 0 || stats.playedAudioBuffers > 0) self.openDeadline = 0;
        else if (self.playRequested && !self.casting &&
            (self.transportFailure || NSProcessInfo.processInfo.systemUptime >= self.openDeadline)) {
            [self failOpening:YES];
            [self updateTimeline];
            return;
        }
    }
    if ([self declaredMediaEnd] > 0 && self.startMilliseconds < 0 &&
        self.playRequested && [self nativeTimeMilliseconds] >= [self declaredMediaEnd]) {
        [self pause]; [self.player stop]; self.ended = YES;
        [self emitCommand:@"ended" value:@""];
    }
    if (self.localAudioNeedsRefresh && self.playRequested && self.player.isPlaying &&
        self.player.isSeekable && [self canPlay:NO]) {
        // A route return can leave queued audio attached to the former output.
        // Flush it at the held position even when the clocks already agree.
        int64_t position = [self positionMilliseconds];
        self.player.time = [VLCTime timeWithNumber:@(position)];
        self.player.audio.muted = self.resumeMuted;
        self.localAudioNeedsRefresh = NO;
    }
    if (self.externalVideoHost && ![self permitsExternalDisplay]) [self revokeExternalVideo];
    // Keep the resume target visible until the decoder acknowledges that seek.
    // The acknowledgement window measures wall time even at faster playback.
    int64_t seekTolerance = (int64_t)(1500 * MAX(1.f, fabsf(self.player.rate)));
    VLCMediaStats seekStats = [self playbackStats];
    // Replacing a playing VLC input need not emit another Playing event.
    // Submit its held seek once the new media itself has decoded data.
    if (self.openingSeekPending && self.startMilliseconds >= 0 && self.playRequested &&
        self.player.isPlaying && self.player.isSeekable && [self canPlay:NO] &&
        (seekStats.decodedAudio > 0 || seekStats.decodedVideo > 0)) {
        self.openingSeekPending = NO;
        int64_t actual = [self nativeTimeMilliseconds];
        if (actual < self.startMilliseconds || actual > self.startMilliseconds + seekTolerance) {
            self.player.time = [VLCTime timeWithNumber:@(self.startMilliseconds)];
            self.seekSubmittedAt = NSProcessInfo.processInfo.systemUptime;
            self.seekAudioBaseline = seekStats.playedAudioBuffers;
            self.seekFrameBaseline = seekStats.displayedPictures;
        }
        self.resumeSeekSubmitted = YES;
    }
    BOOL freshSeekOutput = [self nativeTimeMilliseconds] >= self.startMilliseconds +
        MIN(100, MAX(0, [self durationMilliseconds] - self.startMilliseconds - 1)) &&
        (self.seekSubmittedAt == 0 || (NSProcessInfo.processInfo.systemUptime - self.seekSubmittedAt >= .5 &&
         (seekStats.displayedPictures > self.seekFrameBaseline || seekStats.playedAudioBuffers > self.seekAudioBaseline)));
    if (self.resumeSeekSubmitted && self.startMilliseconds >= 0 && self.player.isPlaying && freshSeekOutput &&
        (seekStats.displayedPictures > 0 || seekStats.playedAudioBuffers > 0) &&
        llabs([self nativeTimeMilliseconds] - self.startMilliseconds) < seekTolerance) {
        self.startMilliseconds = -1;
        self.resumeSeekSubmitted = NO;
        self.seekDeadline = 0;
        self.progressSeek = -1;
    }
    if (self.startMilliseconds >= 0 && self.playRequested && !self.manualResumeRequired &&
        self.seekDeadline > 0 && NSProcessInfo.processInfo.systemUptime >= self.seekDeadline) {
        self.lastPosition = self.startMilliseconds;
        [self playbackFailed];
        [self showStatus:@"Could not reach this position. Choose another time or press Play to retry."];
    }
    if (![self canPlay:NO]) [self pause];
    if (self.progressSeek >= 0 && self.startMilliseconds < 0 && [self nativeTimeMilliseconds] >= 0) {
        int64_t position = [self nativeTimeMilliseconds];
        if (position >= 0 && llabs(position - self.progressSeek) <= 750) {
            self.progressSeek = -1;
            [self emitCommand:@"progress" value:[NSString stringWithFormat:@"%lld", position]];
        }
    }
    NSUInteger audioCount = self.player.audioTracks.count, textCount = self.player.textTracks.count;
    if (audioCount != self.lastAudioTrackCount || textCount != self.lastTextTrackCount) {
        self.lastAudioTrackCount = audioCount;
        self.lastTextTrackCount = textCount;
        [self applyPlaybackOptions];
    }
    [self updateAudioSwitch];
    [self updatePlaybackProgress];
    // Some inputs keep delivering audio while VLC's master clock stops at
    // the declared last picture. Reopen only at that known video endpoint,
    // with recent real audio and a stalled picture, never at a mid-file stall.
    int64_t nativeClock = [self nativeTimeMilliseconds];
    NSTimeInterval now = NSProcessInfo.processInfo.systemUptime;
    if (!self.audioOnlyInput && self.startMilliseconds < 0 && self.playRequested &&
        !self.manualResumeRequired && !self.networkWaiting && !self.networkResumePending &&
        !self.transportFailure && !self.audioSwitchTrack.length && [self canPlay:NO] &&
        [self isDeclaredAudioTail:nativeClock + 100] &&
        seekStats.playedAudioBuffers > 0 && now - self.lastAudioProgress < .5 &&
        now - self.lastFrameProgress >= 1.5 && now - self.lastPlaybackProgress >= 1.5) {
        self.audioOnlyInput = YES;
        self.inputNeedsRestart = YES;
        self.startMilliseconds = self.lastPosition = MAX(0, nativeClock);
        [self startByUser];
        [self showStatus:@"Continuing audio. Seek back to restore video."];
    }
    // Playing can arrive before the first frame/seek acknowledgement. Revisit
    // eligibility once those arrive without postponing an existing deadline.
    [self scheduleControls];
    CGSize videoSize = self.player.videoSize;
    if (fabs(videoSize.width - self.lastVideoSize.width) > 0.5 ||
        fabs(videoSize.height - self.lastVideoSize.height) > 0.5) {
        self.lastVideoSize = videoSize;
        [self.view setNeedsLayout];
    }
    if (self.externalVideoHost) [self layoutVideoDrawable];
    [self applyPictureSize];
    if (self.controlsLocked) [self.view bringSubviewToFront:self.unlockButton];
    [self updateScreenAwake];
    [self updateTimeline];
}

- (void)updateTimeline {
    int64_t position = [self positionMilliseconds];
    int64_t duration = [self durationMilliseconds];
    if (!self.seek.tracking && duration > 0) self.seek.value = (float)position / duration;
    self.seek.hidden = NO;
    // Known-duration inputs remain recoverable even after a failed saved seek
    // makes VLC nonseekable. seekToMilliseconds queues a fresh input in that case.
    self.seek.enabled = duration > 0 && !self.controlsLocked && [self canPlay:NO];
    NSString *(^time)(int64_t) = ^NSString *(int64_t value) {
        int64_t seconds = MAX(0, value / 1000);
        return [NSString stringWithFormat:@"%lld:%02lld:%02lld", seconds / 3600, seconds / 60 % 60, seconds % 60];
    };
    [self.view bringSubviewToFront:self.controlsScroll];
    [self.view bringSubviewToFront:self.bufferOverlay];
    self.timeLabel.text = [NSString stringWithFormat:@"%@ / %@%@", time(position), duration > 0 ? time(duration) : @"Duration unknown", self.cacheApproximate ? @" · Cache ≈" : @""];
    self.timeLabel.accessibilityValue = self.timeLabel.text;
    self.seek.accessibilityValue = self.timeLabel.text;
    [self updateChapterMarkers:duration];
    self.lastPosition = position;
    [self updatePlayButton];
}
- (void)mediaPlayerStateChanged:(VLCMediaPlayerState)state {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (self.retired || [self hasAirPlay]) return;
        if (state == VLCMediaPlayerStateStopped || state == VLCMediaPlayerStateError) [self cancelAudioSwitch];
        [self logHDRTransition:[NSString stringWithFormat:@"state-%ld", (long)state]];
        if (state != VLCMediaPlayerStatePlaying) self.pausePending = NO;
        if (state == VLCMediaPlayerStatePaused && self.player.state == VLCMediaPlayerStatePaused &&
            !self.player.isPlaying) {
            self.rateChangePending = NO;
            [self applyPlaybackRate];
        } else if (state == VLCMediaPlayerStateStopped || state == VLCMediaPlayerStateError) {
            self.rateChangePending = NO;
        }
        // A blocked input can complete an earlier Pause after Play was queued.
        // Reconcile that completion with current intent, never with read-ahead.
        if (state == VLCMediaPlayerStatePaused && self.player.state == VLCMediaPlayerStatePaused &&
            !self.player.isPlaying && self.playRequested &&
            !self.manualResumeRequired && !self.networkResumePending &&
            [self canPlay:self.casting || self.pipActive]) [self.player play];
        if (state == VLCMediaPlayerStateOpening && self.startMilliseconds > 0) {
            self.player.time = [VLCTime timeWithNumber:@(self.startMilliseconds)];
        }
        if (state == VLCMediaPlayerStatePlaying) {
            self.hasPlayed = YES;
            [self applyPlaybackOptions];
            if (self.manualResumeRequired || ![self canPlay:NO]) { [self pause]; return; }
            self.player.audio.muted = self.resumeMuted;
            if (self.startMilliseconds >= 0) {
                int64_t seekTolerance = (int64_t)(1500 * MAX(1.f, fabsf(self.player.rate)));
                if (llabs([self nativeTimeMilliseconds] - self.startMilliseconds) >= seekTolerance)
                    self.player.time = [VLCTime timeWithNumber:@(self.startMilliseconds)];
                self.resumeSeekSubmitted = YES;
            }
            self.ended = NO;
            [self scheduleControls];
        }
        int64_t duration = [self durationMilliseconds];
        if (self.playRequested && !self.casting && self.player.state == state &&
            (state == VLCMediaPlayerStateStopped || state == VLCMediaPlayerStateError)) {
            if (self.openDeadline > 0 && ![self hasDecodedMedia]) {
                [self failOpening:NO];
                [self updateTimeline];
                return;
            }
            if (self.aviFromBeginning && !self.audioOnlyInput && !self.transportFailure) {
                VLCMediaStats stats = [self playbackStats];
                if (stats.decodedAudio > 0 && stats.decodedVideo == 0 && stats.displayedPictures == 0 &&
                    self.player.media.videoTracks.count > 0) {
                    [self playbackFailed];
                    self.inputNeedsRestart = YES;
                    [self showStatus:@"The video track could not be decoded. Try another copy or a supported video codec."];
                    [self updateTimeline];
                    return;
                }
            }
        }
        if (state == VLCMediaPlayerStateStopped && self.player.state == VLCMediaPlayerStateStopped &&
            [self recoverEarlyAudioEnd]) return;
        if (state == VLCMediaPlayerStateStopped && (self.player.position >= .999 ||
            (duration > 0 && self.lastPosition >= duration - 1000))) {
            BOOL notify = !self.ended;
            self.ended = YES;
            self.playRequested = NO;
            if (notify) [self emitCommand:@"ended" value:@""];
            [self setControlsShown:YES];
        }
        if (!self.playRequested || state == VLCMediaPlayerStateError || state == VLCMediaPlayerStateStopped) {
            self.buffering = NO; self.bufferOverlay.hidden = YES;
            [self.bufferSpinner stopAnimating];
        }
        if ((state == VLCMediaPlayerStateError && self.player.state == VLCMediaPlayerStateError) ||
            (state == VLCMediaPlayerStateStopped && self.player.state == VLCMediaPlayerStateStopped &&
             self.hasPlayed && self.playRequested && !self.ended)) [self playbackFailed];
        if (state == VLCMediaPlayerStatePlaying) [self updateScreenAwake];
        else [self setScreenAwake:NO];
        [self invalidatePiPPlaybackState];
    });
}
- (void)mediaPlayerLengthChanged:(int64_t)length { [self invalidatePiPPlaybackState]; }

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
    return menu;
}
- (NSDictionary<NSNumber *, NSString *> *)chapterRows {
    if (self.chaptersInvalidated || self.retired || ![self canPlay:NO]) return @{};
    if ([self hasAirPlay]) return self.airPlayChapters.count ? self.airPlayChapters : self.localChapters;
    NSInteger title = self.player.currentTitleIndex;
    if (title != self.chapterTitleIndex) {
        self.chapterTitleIndex = title;
        self.localChapters = nil;
        self.nextChapterLookup = 0;
    }
    NSTimeInterval now = NSProcessInfo.processInfo.systemUptime;
    if (self.localChapters.count || now < self.nextChapterLookup) return self.localChapters;
    self.nextChapterLookup = now + 1;
    NSArray<VLCMediaPlayerChapterDescription *> *rows = [self.player chapterDescriptionsOfTitle:(int)title];
    NSMutableDictionary<NSNumber *, NSString *> *chapters = [NSMutableDictionary dictionary];
    for (NSUInteger index = 0; index < rows.count; index++) {
        VLCMediaPlayerChapterDescription *chapter = rows[index];
        int64_t offset = chapter.timeOffset.value.longLongValue;
        if (offset < 0) continue;
        NSString *name = chapter.name.length ? chapter.name : [NSString stringWithFormat:@"Chapter %lu", (unsigned long)index + 1];
        chapters[@(offset)] = name;
    }
    self.localChapters = chapters;
    return self.localChapters;
}
- (NSArray<NSNumber *> *)chapterStarts:(NSDictionary<NSNumber *, NSString *> *)rows duration:(int64_t)duration {
    NSMutableArray<NSNumber *> *starts = [NSMutableArray array];
    for (NSNumber *start in rows) if (start.longLongValue < duration) [starts addObject:start];
    return [starts sortedArrayUsingSelector:@selector(compare:)];
}
- (void)updateChapterMarkers:(int64_t)duration {
    NSMutableArray<NSNumber *> *fractions = [NSMutableArray array];
    for (NSNumber *start in [self chapterStarts:[self chapterRows] duration:duration]) {
        [fractions addObject:@(start.doubleValue / duration)];
    }
    self.seek.chapterFractions = fractions;
}
- (NSNumber *)chapterTarget:(NSArray<NSNumber *> *)starts next:(BOOL)next {
    int64_t position = self.ended ? [self durationMilliseconds] : [self positionMilliseconds];
    NSNumber *previous = nil, *current = nil;
    for (NSNumber *start in starts) {
        if (start.longLongValue > position) {
            if (next) return start;
            break;
        }
        previous = current;
        current = start;
    }
    if (next || !current) return nil;
    return position - current.longLongValue < LGVideoChapterRestartMilliseconds ? previous : current;
}
- (void)seekChapter:(NSNumber *)start {
    if (!start || self.controlsLocked || ![self chapterRows][start] ||
        start.longLongValue >= [self durationMilliseconds]) return;
    if ([self hasAirPlay]) [self seekAirPlay:start.longLongValue chapter:YES];
    else [self seekToMilliseconds:start.longLongValue];
}
- (void)skipChapter:(BOOL)next {
    NSArray *starts = [self chapterStarts:[self chapterRows] duration:[self durationMilliseconds]];
    [self seekChapter:[self chapterTarget:starts next:next]];
}
- (void)invalidateChapters {
    self.chaptersInvalidated = YES;
    self.localChapters = self.airPlayChapters = nil;
    self.seek.chapterFractions = @[];
    UIViewController *presented = self.presentedViewController;
    if (presented == self.chapterDialog || ([presented isKindOfClass:LGVideoDeckSettings.class] &&
        ((LGVideoDeckSettings *)presented).dialog == self.chapterDialog)) {
        [presented dismissViewControllerAnimated:YES completion:^{ [self scheduleControls]; }];
    }
}
- (void)chapters:(id)sender {
    if (self.controlsLocked || ![self canPlay:NO]) return;
    [self setControlsShown:YES];
    UIAlertController *menu = [self menu:@"Chapters" sender:sender];
    NSDictionary *rows = [self chapterRows];
    NSArray<NSNumber *> *starts = [self chapterStarts:rows duration:[self durationMilliseconds]];
    if (starts.count) {
        for (NSNumber *direction in @[@NO, @YES]) {
            BOOL next = direction.boolValue;
            UIAlertAction *skip = [UIAlertAction lg_videoActionWithTitle:next ? @"Next chapter" : @"Previous chapter"
                style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self skipChapter:next]; }];
            skip.enabled = [self chapterTarget:starts next:next] != nil;
            [menu lg_videoAddAction:skip];
        }
        int64_t position = self.ended ? [self durationMilliseconds] : [self positionMilliseconds];
        NSNumber *current = nil;
        for (NSNumber *start in starts) if (start.longLongValue <= position) current = start;
        for (NSNumber *start in starts) {
            int64_t offset = start.longLongValue;
            NSString *label = [NSString stringWithFormat:@"%@%lld:%02lld:%02lld · %@", [start isEqual:current] ? @"✓ " : @"",
                offset / 3600000, offset / 60000 % 60, offset / 1000 % 60, rows[start]];
            [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:label style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
                [self seekChapter:start];
            }]];
        }
    } else {
        menu.message = self.chaptersInvalidated ? @"The video changed. Reopen it to see its chapters." :
            rows.count ? @"Chapter positions are unavailable for the current timeline." : @"This video has no embedded chapters.";
    }
    self.chapterDialog = menu;
    [self presentPlaybackDialog:menu];
}
- (void)audioTracks:(id)sender { [self tracks:sender subtitles:NO]; }
- (void)subtitleTracks:(id)sender { [self tracks:sender subtitles:YES]; }
- (NSString *)trackKey:(VLCMediaPlayerTrack *)track {
    NSArray *fields = @[@"ios-vlc", track.language ?: @"", track.trackDescription ?: @"",
                        [track codecName] ?: @"", track.trackName ?: @""];
    NSData *data = [NSJSONSerialization dataWithJSONObject:fields options:0 error:nil];
    return [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"";
}
- (void)selectTrack:(NSString *)field index:(NSInteger)index key:(NSString *)key {
    NSMutableDictionary *options = [[self playbackOptions] mutableCopy];
    options[field] = @(index);
    options[[field stringByAppendingString:@"_key"]] = key;
    if ([field isEqualToString:@"subtitle_track"]) options[@"subtitle_file"] = @"";
    NSData *data = [NSJSONSerialization dataWithJSONObject:options options:0 error:nil];
    if (!data) return;
    self.optionsJSON = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    NSDictionary *update = @{field: @(index), [field stringByAppendingString:@"_key"]: key};
    data = [NSJSONSerialization dataWithJSONObject:update options:0 error:nil];
    [self emitCommand:@"settings" value:[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding]];
}
- (NSString *)trackLabel:(VLCMediaPlayerTrack *)track index:(NSUInteger)index {
    if (track.audio) {
        NSString *language = track.language.length && ![track.language isEqualToString:@"und"] ?
            ([NSLocale.currentLocale localizedStringForLanguageCode:track.language] ?: track.language) : @"";
        NSString *label = LGVideoAudioLabel(index + 1, @[language, track.trackName ?: @"", track.trackDescription ?: @""],
            [track codecName], track.audio.channelsNumber, track.audio.rate);
        return track.isSelected ? [@"✓ " stringByAppendingString:label] : label;
    }
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
    if ([self hasAirPlay]) { [self showAirPlayTracks:sender subtitles:text]; return; }
    // The timer defers hiding while a menu is presented and resumes afterward.
    [self setControlsShown:YES];
    UIAlertController *menu = [self menu:text ? @"Subtitles" : @"Audio tracks" sender:sender];
    if (text) [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:@"Subtitles off" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        if ([self canPlay:NO]) { [self.player deselectAllTextTracks]; [self selectTrack:@"subtitle_track" index:-1 key:@""]; }
    }]];
    NSArray<VLCMediaPlayerTrack *> *tracks = text ? self.player.textTracks : self.player.audioTracks;
    for (NSUInteger index = 0; index < tracks.count; index++) {
        VLCMediaPlayerTrack *track = tracks[index];
        [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:[self trackLabel:track index:index] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
            if ([self canPlay:NO]) {
                if (text) track.selectedExclusively = YES;
                else if (![self switchAudioTrack:track]) return;
                [self selectTrack:text ? @"subtitle_track" : @"audio_track" index:(NSInteger)index key:[self trackKey:track]];
            }
        }]];
    }
    if (text) {
        NSArray *subtitles = [NSJSONSerialization JSONObjectWithData:[self.subtitleJSON dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
        for (NSDictionary *subtitle in subtitles) {
            [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:subtitle[@"name"] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
                [self emitCommand:@"subtitleSelect" value:subtitle[@"name"]];
            }]];
        }
    }
    if (!tracks.count) menu.message = @"No embedded tracks available yet. Start playback to discover tracks.";
    [self presentPlaybackDialog:menu];
}
- (void)mediaPlayerBufferingChanged:(float)progress {
    // Keep callbacks queued before a replacement selection/seek from completing it.
    NSUInteger generation = self.audioSwitchGeneration;
    dispatch_async(dispatch_get_main_queue(), ^{
        if (!self.audioSwitchTrack.length || self.retired || generation != self.audioSwitchGeneration) return;
        if (progress <= 0) self.audioSwitchSawBuffering = YES;
        if (progress >= 1 && self.audioSwitchSawBuffering && !self.audioSwitchBuffered) {
            self.audioSwitchBuffered = YES;
            // Anything counted before this post-flush event could belong to
            // the old output queue. Require another real output buffer.
            self.audioSwitchPlayed = [self playbackStats].playedAudioBuffers;
            self.audioSwitchClock = self.audioSwitchDecodeClock = [self nativeTimeMilliseconds];
            self.audioSwitchDecoded = [self playbackStats].decodedAudio;

        }
        [self updateAudioSwitch];
    });
    // Ordinary decoder prebuffering still belongs to the render watchdog.
}
- (void)cast:(id)sender {
    if ([self hasAirPlay] || self.airPlayPreparing || (self.airPlayAvailable && [self hasAirPlayAudioRoute])) {
        [self showStatus:@"Use the AirPlay picker to change the current output."];
        return;
    }
    if (![self canPlay:YES]) return;
    if (self.discoverers.count == 0) {
        for (VLCRendererDiscovererDescription *description in [VLCRendererDiscoverer list]) {
            VLCRendererDiscoverer *discoverer = [[VLCRendererDiscoverer alloc] initWithName:description.name];
            if (discoverer) { [self.discoverers addObject:discoverer]; [discoverer start]; }
        }
    }
    UIAlertController *menu = [self menu:@"Cast video" sender:sender];
    [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:@"This device" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        [self selectRenderer:nil];
    }]];
    NSUInteger count = 0;
    for (VLCRendererDiscoverer *discoverer in self.discoverers) {
        for (VLCRendererItem *renderer in discoverer.renderers) {
            count++;
            [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:renderer.name style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
                [self selectRenderer:renderer];
            }]];
        }
    }
    if (count == 0) menu.message = @"Looking for receivers. Open Cast again in a few seconds.";
    [self presentPlaybackDialog:menu];
}
- (void)selectRenderer:(VLCRendererItem *)renderer {
    if ([self hasAirPlay] || ![self canPlay:YES]) return;
    if (self.pipActive) {
        [self showStatus:@"Close Picture in Picture before changing Cast output."];
        return;
    }
    self.startMilliseconds = [self positionMilliseconds];
    [self cancelAudioSwitch];
    [self.player stop];
    self.casting = [self.player setRendererItem:renderer] && renderer != nil;
    if (self.casting) [self moveVideoToExternalHost:nil];
    [self updateScreenAwake];
    [self startByUser];
    if (self.externalOutputChanged) self.externalOutputChanged();
}
- (void)pip:(id)sender {
    if ([self hasAirPlay]) { [self showStatus:@"Choose this device in AirPlay to use Picture in Picture."]; return; }
    if (![self canPlay:YES]) return;
    if (self.externalVideoHost || self.casting) {
        [self showStatus:@"Disconnect the external display or Cast to use Picture in Picture."];
        return;
    }
    if (self.subtitlePiPEnabled) {
        if (!self.captionPiP) self.captionPiP = LGCreateCaptionPiP(self);
        if (self.captionPiP) [self.captionPiP startPictureInPicture];
        else [self showStatus:@"Picture in picture is unavailable on this device."];
    } else if (self.pipController) [self.pipController startPictureInPicture];
    else [self showStatus:@"Picture in picture is not ready. Start playback first."];
}
- (void)invalidatePiPPlaybackState {
    [self.pipController invalidatePlaybackState];
    [self.captionPiP invalidatePlaybackState];
}
- (id<VLCPictureInPictureMediaControlling>)mediaController { return self; }
- (void (^)(id<VLCPictureInPictureWindowControlling>))pictureInPictureReady {
    __weak LGVideoController *owner = self;
    return ^(id<VLCPictureInPictureWindowControlling> controller) {
        if (owner.restricted || owner.retired) return;
        owner.pipController = controller;
        controller.stateChangeEventHandler = ^(BOOL active) {
            if (owner.captionPiP || owner.retired) return;
            if (active && (owner.externalVideoHost || owner.casting)) { [owner.pipController stopPictureInPicture]; return; }
            owner.pipActive = active;
            [owner updateScreenAwake];
            [owner setControlsShown:YES];
            if (owner.externalOutputChanged) owner.externalOutputChanged();
        };
    };
}
- (void)addSubview:(UIView *)view {
    if (self.retired) return;
    view.frame = self.movie.bounds;
    view.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    [self.movie addSubview:view];
    [self configureVideoDynamicRange:view.layer];
    [self updateInlineSubtitles];
}
- (void)configureVideoDynamicRange:(CALayer *)layer {
    // This changes only the requested display headroom, never the source HDR metadata.
    // System-managed HDR is the default on iOS 26; the old forced mode is available
    // through Playback for A/B comparison without changing decoder or video output.
    if ([layer isKindOfClass:AVSampleBufferDisplayLayer.class]) {
        // Apple's native output has its own framing policy; VLC crop alone
        // does not change its default aspect-fit presentation.
        AVSampleBufferDisplayLayer *videoLayer = (AVSampleBufferDisplayLayer *)layer;
        AVLayerVideoGravity gravity = !self.externalVideoHost && [[self playbackOptions][@"aspect"] isEqualToString:@"fill"]
            ? AVLayerVideoGravityResizeAspectFill : AVLayerVideoGravityResizeAspect;
        if (![videoLayer.videoGravity isEqualToString:gravity]) videoLayer.videoGravity = gravity;
        if (@available(iOS 26.0, *)) {
            layer.preferredDynamicRange = self.forceMaximumHDR ? CADynamicRangeHigh : CADynamicRangeAutomatic;
        } else if (@available(iOS 17.0, *)) {
            // Older systems lack the new automatic selector. Preserve HDR output.
            layer.wantsExtendedDynamicRangeContent = YES;
        }
    }
    for (CALayer *child in layer.sublayers) [self configureVideoDynamicRange:child];
}
- (void)setForcedMaximumHDRForSession:(BOOL)forced {
    if (self.forceMaximumHDR == forced) return;
    self.forceMaximumHDR = forced;
    // VLCKit may insert or recreate the sample-buffer layer at runtime.
    [CATransaction begin];
    [CATransaction setDisableActions:YES];
    [self configureVideoDynamicRange:self.movie.layer];
    [CATransaction commit];
    [self logHDRTransition:@"mode-change"];
    NSLog(@"[VideoHDR] requestedMode=%@ (effective on iOS 26+)", forced ? @"high" : @"automatic");
}
- (CGRect)bounds { return self.movie.bounds; }
- (void)play { if ([self canPlay:YES]) [self startByUser]; }
- (void)seekBy:(int64_t)offset completion:(dispatch_block_t)completion {
    // Use the same bounded millisecond seek as the on-screen controls. VLC's
    // relative helper uses a 32-bit clock and may never complete a boundary
    // seek, leaving the system's PiP skip controls waiting indefinitely.
    if ([self canPlay:YES]) [self skipMilliseconds:offset];
    [self invalidatePiPPlaybackState];
    // Always release the system request, including denied/nonseekable seeks.
    if (completion) dispatch_async(dispatch_get_main_queue(), completion);
}
- (int64_t)mediaLength { return [self durationMilliseconds]; }
- (int64_t)mediaTime { return [self positionMilliseconds]; }
- (BOOL)isMediaSeekable { return !self.controlsLocked && [self canPlay:YES] && [self durationMilliseconds] > 0; }
- (BOOL)isMediaPlaying { return self.player.isPlaying; }
- (void)retireWithCompletion:(dispatch_block_t)completion {
    NSAssert(NSThread.isMainThread, @"Retire video on the UI thread");
    if (self.retirementComplete) { if (completion) completion(); return; }
    if (!self.retirementCallbacks) self.retirementCallbacks = [NSMutableArray array];
    if (completion) [self.retirementCallbacks addObject:[completion copy]];
    if (self.retired) return;
    [self setScreenAwake:NO];
    // Remove the movie before releasing its source. Leave the empty AVPlayer
    // available for another explicit AirPlay request in this window.
    self.retired = YES;
    self.buffering = NO;
    [self cancelAudioSwitch];
    // A closed video must not leave the window's reusable AVPlayer opted into
    // external playback while browsing or opening a protected document.
    [self detachAirPlay];
    self.airPlayAllowed = nil;
    self.airPlaySourceTrace = nil;
    self.backgroundAudioAllowed = nil;
    self.rateChangePending = NO;
    [self clearPausePresentation];
    self.command = nil;
    self.bufferOverlay.hidden = YES;
    [self.bufferSpinner stopAnimating];
    self.movie.hidden = YES;
    self.player.audio.muted = YES;
    [self moveVideoToExternalHost:nil];
    self.fullscreen = NO;
    [self setControlsShown:YES];
    [self.timer invalidate]; self.timer = nil;
    [NSNotificationCenter.defaultCenter removeObserver:self];
    [self.callObserver setDelegate:nil queue:NULL]; self.callObserver = nil;
    [self.captionPiP stopPictureInPicture]; self.captionPiP = nil;
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
    self.externalDisplayAllowed = nil; self.externalOutputChanged = nil;
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

@implementation LGVideoController (VideoChrome)

- (void)configureVideoView {
    self.view.backgroundColor = UIColor.blackColor;
    self.edgesForExtendedLayout = UIRectEdgeAll;
    self.extendedLayoutIncludesOpaqueBars = YES;
    self.navigationItem.largeTitleDisplayMode = UINavigationItemLargeTitleDisplayModeNever;
}

- (void)installVideoChrome {
    [self installInlineMovie];
    [self installControlsContainer];
    [self installTimeline];
    [self installNavigationItems];
    [self installTransport];
    [self installTabletopUtilities];
    [self installBufferOverlay];
    [self activateChromeConstraints];
    [self installChromeInteractions];
}

- (void)installInlineMovie {
    self.inlineMovie = [[UIView alloc] init];
    self.inlineMovie.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.inlineMovie];
    self.movie = [[UIView alloc] initWithFrame:self.inlineMovie.bounds];
    self.movie.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    self.movie.clipsToBounds = YES;
    // VLC installs rendering subviews after presentation. Keep them out of hit
    // testing so the controller tap recognizer always receives video touches.
    self.movie.userInteractionEnabled = NO;
    self.inlineMovie.userInteractionEnabled = NO;
    self.inlineMovie.isAccessibilityElement = YES;
    self.inlineMovie.accessibilityLabel = @"Video";
    self.inlineMovie.accessibilityCustomActions = @[
        [[UIAccessibilityCustomAction alloc] initWithName:@"Show video controls" target:self selector:@selector(showControlsForAccessibility)]
    ];
    [self.inlineMovie addSubview:self.movie];
}

- (void)installControlsContainer {
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
    if (@available(iOS 26.0, *)) {
        self.controlsMaterial = [UIGlassEffect effectWithStyle:UIGlassEffectStyleRegular];
    } else {
        self.controlsMaterial = [UIBlurEffect effectWithStyle:UIBlurEffectStyleSystemThinMaterialDark];
    }
    // Keep the effect behind the scroll view at full alpha while controls fade.
    self.controlsBackdrop = [[UIVisualEffectView alloc] initWithEffect:self.controlsMaterial];
    self.controlsBackdrop.overrideUserInterfaceStyle = UIUserInterfaceStyleDark;
    self.controlsBackdrop.userInteractionEnabled = NO;
    self.controlsBackdrop.translatesAutoresizingMaskIntoConstraints = NO;
    if (@available(iOS 26.0, *)) {
        self.controlsBackdrop.cornerConfiguration =
            [UICornerConfiguration configurationWithUniformRadius:[UICornerRadius fixedRadius:20]];
    } else {
        self.controlsBackdrop.layer.cornerRadius = 20;
        self.controlsBackdrop.clipsToBounds = YES;
    }
    [self.view insertSubview:self.controlsBackdrop belowSubview:self.controlsScroll];
}

- (void)installTimeline {
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
    self.seek = [[LGVideoTimeline alloc] init];
    self.seek.minimumTrackTintColor = UIColor.whiteColor;
    self.seek.maximumTrackTintColor = [UIColor colorWithWhite:.65 alpha:1];
    self.seek.thumbTintColor = UIColor.whiteColor;
    self.seek.accessibilityLabel = @"Video position";
    NSNumber *seekExtent = [self playbackOptions][@"reader_layout"][@"extent"];
    [self.seek.heightAnchor constraintGreaterThanOrEqualToConstant:seekExtent ? seekExtent.doubleValue : 48].active = YES;
    [self.seek addTarget:self action:@selector(seekChanged:) forControlEvents:UIControlEventTouchUpInside | UIControlEventTouchUpOutside];
    [self.controls addArrangedSubview:self.seek];
}

- (void)installNavigationItems {
    UIBarButtonItem *close = [self item:@"Done" selector:@selector(done:)];
    self.pictureButton = [self item:@"Fill view" selector:@selector(togglePictureSize:)];
    UIBarButtonItem *picture = self.pictureButton;
    UIBarButtonItem *chapters = [self item:@"Chapters" selector:@selector(chapters:)];
    UIBarButtonItem *audio = [self item:@"Audio tracks" selector:@selector(audioTracks:)];
    UIBarButtonItem *subtitles = [self item:@"Subtitles" selector:@selector(subtitleTracks:)];
    UIBarButtonItem *tools = [self item:@"Playback" selector:@selector(playbackTools:)];
    NSMutableArray<UIBarButtonItem *> *utilities = [NSMutableArray arrayWithArray:@[picture, audio, subtitles, chapters, tools]];
    if (!self.restricted) {
        UIBarButtonItem *more = [self item:@"More playback options" selector:NULL];
        __weak LGVideoController *owner = self;
        __weak UIBarButtonItem *anchor = more;
        more.menu = [UIMenu menuWithChildren:@[
            [UIAction actionWithTitle:@"Show in folder" image:[UIImage systemImageNamed:@"folder"] identifier:nil handler:^(UIAction *action) { [owner emitCommand:@"showInFolder" value:@""]; }],
            [UIAction actionWithTitle:@"Favourite file" image:[UIImage systemImageNamed:@"star"] identifier:nil handler:^(UIAction *action) { [owner emitCommand:@"favourite" value:@""]; }],
            [UIAction actionWithTitle:@"Picture in picture" image:[UIImage systemImageNamed:@"pip"] identifier:nil handler:^(UIAction *action) { [owner pip:anchor]; }],
            [UIAction actionWithTitle:@"VLC Cast…" image:[UIImage systemImageNamed:@"tv"] identifier:nil handler:^(UIAction *action) { [owner cast:anchor]; }]
        ]];
        [utilities addObject:more];
    }
    if (@available(iOS 16.0, *)) {
        self.navigationItem.leadingItemGroups = @[[[UIBarButtonItemGroup alloc] initWithBarButtonItems:@[close] representativeItem:nil]];
        self.navigationItem.trailingItemGroups = @[
            [[UIBarButtonItemGroup alloc] initWithBarButtonItems:@[picture, tools, audio, subtitles, chapters] representativeItem:nil]
        ];
        if (!self.restricted) {
            UIMenu *externalMenu = utilities.lastObject.menu;
            self.navigationItem.additionalOverflowItems = [UIDeferredMenuElement elementWithUncachedProvider:^(void (^completion)(NSArray<UIMenuElement *> *)) {
                completion(externalMenu.children);
            }];
        }
    } else {
        self.navigationItem.leftBarButtonItem = close;
        self.navigationItem.rightBarButtonItems = utilities;
    }
}

- (void)installTransport {
    self.transport = [[UIStackView alloc] init];
    self.transport.axis = UILayoutConstraintAxisHorizontal;
    self.transport.alignment = UIStackViewAlignmentCenter;
    self.transport.distribution = UIStackViewDistributionEqualCentering;
    self.transport.spacing = 28;
    [self.transport addArrangedSubview:[self deckButton:@"Back 10 seconds" symbol:@"gobackward.10" selector:@selector(back:) primary:NO]];
    self.playButton = [self deckButton:@"Play" symbol:@"play.fill" selector:@selector(togglePlay:) primary:YES];
    [self.transport addArrangedSubview:self.playButton];
    [self.transport addArrangedSubview:[self deckButton:@"Forward 10 seconds" symbol:@"goforward.10" selector:@selector(forward:) primary:NO]];
    [self.controls addArrangedSubview:self.transport];
    if (self.airPlayAvailable) [self installAirPlayControls];
}

- (void)installTabletopUtilities {
    self.tabletopUtilities = [[UIStackView alloc] init];
    self.tabletopUtilities.axis = UILayoutConstraintAxisVertical;
    self.tabletopUtilities.spacing = 4;
    UIStackView *utilityRow = nil;
    NSUInteger utilityIndex = 0;
    for (NSArray *entry in @[@[@"Speed", @"speedometer", @"speedOptions:"],
                            @[@"Fill view", @"arrow.up.left.and.arrow.down.right", @"togglePictureSize:"],
                            @[@"Audio", @"speaker.wave.2", @"audioTracks:"],
                            @[@"Subtitles", @"captions.bubble", @"subtitleTracks:"],
                            @[@"Chapters", @"list.bullet", @"chapters:"],
                            @[@"Go to time", @"clock", @"goToTime:"],
                            @[@"Playback", @"slider.horizontal.3", @"playbackTools:"],
                            @[@"Done", @"xmark", @"done:"]]) {
        if (utilityIndex++ % 4 == 0) {
            utilityRow = [[UIStackView alloc] init];
            utilityRow.distribution = UIStackViewDistributionFillEqually;
            [self.tabletopUtilities addArrangedSubview:utilityRow];
        }
        UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
        UIButtonConfiguration *config = [UIButtonConfiguration plainButtonConfiguration];
        config.image = [UIImage systemImageNamed:entry[1]];
        config.title = entry[0]; config.imagePlacement = NSDirectionalRectEdgeTop;
        config.imagePadding = 3;
        config.contentInsets = NSDirectionalEdgeInsetsMake(2, 2, 2, 2); config.baseForegroundColor = UIColor.whiteColor;
        config.titleLineBreakMode = NSLineBreakByTruncatingTail;
        config.titleTextAttributesTransformer = ^NSDictionary<NSAttributedStringKey,id> *(NSDictionary<NSAttributedStringKey,id> *attributes) {
            NSMutableDictionary *result = [attributes mutableCopy];
            result[NSFontAttributeName] = [UIFont preferredFontForTextStyle:UIFontTextStyleCaption1];
            return result;
        };
        button.configuration = config;
        if ([entry[2] isEqualToString:@"togglePictureSize:"]) self.tabletopPictureButton = button;
        button.accessibilityLabel = entry[0];
        [button addTarget:self action:NSSelectorFromString(entry[2]) forControlEvents:UIControlEventTouchUpInside];
        [button.heightAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;
        [utilityRow addArrangedSubview:button];
    }
    [self.controls addArrangedSubview:self.tabletopUtilities];
    self.tabletopUtilities.hidden = YES;
}

- (void)installBufferOverlay {
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
}

- (void)activateChromeConstraints {
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
    // Size VLC's drawable to the fitted picture, rather than asking VLC to
    // letterbox internally (where it can draw subtitles outside the image).
    self.movieWidth = [self.inlineMovie.widthAnchor constraintEqualToConstant:0];
    self.movieHeight = [self.inlineMovie.heightAnchor constraintEqualToConstant:0];
    self.movieCenterY = [self.inlineMovie.centerYAnchor constraintEqualToAnchor:self.view.topAnchor];
    [NSLayoutConstraint activateConstraints:@[
        [self.inlineMovie.centerXAnchor constraintEqualToAnchor:self.view.centerXAnchor],
        self.movieCenterY, self.movieWidth, self.movieHeight,
        self.controlsLeading, self.controlsTrailing, self.controlsBottom, self.controlsTop,
        naturalHeight,
        [self.controlsBackdrop.leadingAnchor constraintEqualToAnchor:self.controlsScroll.leadingAnchor],
        [self.controlsBackdrop.trailingAnchor constraintEqualToAnchor:self.controlsScroll.trailingAnchor],
        [self.controlsBackdrop.topAnchor constraintEqualToAnchor:self.controlsScroll.topAnchor],
        [self.controlsBackdrop.bottomAnchor constraintEqualToAnchor:self.controlsScroll.bottomAnchor],
        self.bufferCenterX, self.bufferCenterY,
        [self.controls.leadingAnchor constraintEqualToAnchor:self.controlsScroll.contentLayoutGuide.leadingAnchor],
        [self.controls.trailingAnchor constraintEqualToAnchor:self.controlsScroll.contentLayoutGuide.trailingAnchor],
        [self.controls.topAnchor constraintEqualToAnchor:self.controlsScroll.contentLayoutGuide.topAnchor],
        [self.controls.bottomAnchor constraintEqualToAnchor:self.controlsScroll.contentLayoutGuide.bottomAnchor],
        [self.controls.widthAnchor constraintEqualToAnchor:self.controlsScroll.frameLayoutGuide.widthAnchor]
    ]];
}

- (void)installChromeInteractions {
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
}

- (LGVideoLayout)resolveVideoLayoutInSafeArea:(CGRect)safe {
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
    BOOL portrait = tabletop && self.view.bounds.size.height > self.view.bounds.size.width;
    return (LGVideoLayout){.safeArea = safe, .controlsArea = available, .movieArea = movieArea,
                           .tabletop = tabletop, .portraitTabletop = portrait};
}

- (void)layoutInlineMovieInArea:(CGRect)movieArea {
    // Fit the drawable itself to the decoded image, with letterboxing supplied
    // by our black parent view. VLC subtitles then have the image's bounds as
    // their layout surface. Fill keeps the viewport bounds for cropping;
    // unsupported legacy modes use Fit.
    CGSize viewport = movieArea.size;
    CGSize decoded = self.player.videoSize;
    NSString *pictureMode = [self playbackOptions][@"aspect"] ?: @"fit";
    BOOL fit = ![pictureMode isEqualToString:@"fill"];
    if (fit && decoded.width > 0 && decoded.height > 0 &&
        isfinite(decoded.width) && isfinite(decoded.height) &&
        viewport.width > 0 && viewport.height > 0) {
        CGFloat factor = MIN(viewport.width / decoded.width, viewport.height / decoded.height);
        viewport = CGSizeMake(decoded.width * factor, decoded.height * factor);
    }
    CGFloat centerY = CGRectGetMidY(movieArea);
    if (fabs(self.movieWidth.constant - viewport.width) > 0.5 ||
        fabs(self.movieHeight.constant - viewport.height) > 0.5 ||
        fabs(self.movieCenterY.constant - centerY) > 0.5) {
        self.movieWidth.constant = viewport.width;
        self.movieHeight.constant = viewport.height;
        self.movieCenterY.constant = centerY;
        // VLC's drawable subviews are managed by the VLCDrawable callback.
        // The next layout pass updates them after Auto Layout sizes movie.
        [self.view setNeedsLayout];
    }
}

- (CGRect)tabletopControlsAreaFromArea:(CGRect)available {
    if (!self.view.window) return available;
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
    return available;
}

- (void)layoutControlDeck:(LGVideoLayout)layout margin:(CGFloat)margin poseChanged:(BOOL)poseChanged {
    BOOL tabletop = layout.tabletop;
    BOOL portrait = layout.portraitTabletop;
    CGRect safe = layout.safeArea;
    CGRect available = layout.controlsArea;
    self.tabletopUtilities.hidden = !tabletop || portrait;
    self.timeLabel.textAlignment = tabletop ? NSTextAlignmentNatural : NSTextAlignmentCenter;
    self.controls.spacing = portrait ? (available.size.height >= 380 ? 10 : 4) : tabletop ? 2 : 4;
    self.controls.layoutMarginsRelativeArrangement = YES;
    self.controls.layoutMargins = portrait ? UIEdgeInsetsMake(8, 16, 8, 16) : UIEdgeInsetsMake(4, 12, 6, 12);
    CGFloat transportInset = tabletop ? 0 : MAX(0, (available.size.width - 2 * margin - 24 - 260) / 2);
    self.transport.spacing = tabletop ? 28 : 12;
    self.transport.layoutMarginsRelativeArrangement = !tabletop;
    self.transport.layoutMargins = UIEdgeInsetsMake(0, transportInset, 0, transportInset);
    if (tabletop) available = [self tabletopControlsAreaFromArea:available];
    self.tabletopArea = available;
    self.portraitDeckHeight.active = portrait;
    self.portraitDeckHeight.constant = MAX(44, available.size.height - 16);
    [self layoutPortraitDeck];
    self.controlsScroll.backgroundColor = tabletop ? [UIColor colorWithWhite:.08 alpha:1] : UIColor.clearColor;
    self.controlsScroll.layer.cornerRadius = portrait ? 0 : 20;
    if (poseChanged) [self setControlsShown:YES];
    // In laptop posture the upper panel owns the movie and the lower panel
    // owns persistent controls. The movie never spans the horizontal hinge.
    CGRect spinnerArea = tabletop ? layout.movieArea : available;
    self.controlsBottom.active = !tabletop;
    self.deckCenterY.active = tabletop;
    self.deckCenterY.constant = CGRectGetMidY(available) - CGRectGetMidY(safe);
    self.controlsHeightLimit.constant = MAX(44, available.size.height - (tabletop ? 8 : 24));
    self.controlsLeading.constant = margin + CGRectGetMinX(available) - CGRectGetMinX(safe);
    self.controlsTrailing.constant = -margin + CGRectGetMaxX(available) - CGRectGetMaxX(safe);
    self.controlsTop.constant = 8 + CGRectGetMinY(available) - CGRectGetMinY(safe);
    self.controlsBottom.constant = CGRectGetMaxY(available) - CGRectGetMaxY(safe) - 6;
    self.bufferCenterX.constant = CGRectGetMidX(spinnerArea) - CGRectGetMidX(safe);
    self.bufferCenterY.constant = CGRectGetMidY(spinnerArea) - CGRectGetMidY(safe);
}

@end

#import "PlaybackControls.m"

#import "HDRDiagnostics.m"
#import "PausePresentation.m"
#import "InlineSubtitles.m"
#import "AudioSwitch.m"

#import "CaptionPictureInPicture.m"
#import "AirPlayVideo.m"
#import "MKVRemux.m"

@implementation LGCaptionVideoDrawable
- (void)addSubview:(UIView *)view { [self.owner addSubview:view]; }
- (CGRect)bounds { return [self.owner bounds]; }
@end
