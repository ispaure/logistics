#import <math.h>
// Feature-owned controls layered over the decoder/lifecycle controller.
@interface LGVideoCachedRanges : UIView
@property(nonatomic, strong) NSArray *ranges;
@end
@implementation LGVideoCachedRanges
- (void)drawRect:(CGRect)rect {
    CGFloat width = MAX(0, self.bounds.size.width);
    [[UIColor colorWithWhite:.48 alpha:.80] setFill];
    UIRectFill(CGRectMake(0, 0, width, self.bounds.size.height));
    [UIColor.systemGreenColor setFill];
    for (NSArray *range in self.ranges) {
        if (![range isKindOfClass:NSArray.class] || range.count != 2) continue;
        if (![range[0] respondsToSelector:@selector(doubleValue)] || ![range[1] respondsToSelector:@selector(doubleValue)]) continue;
        CGFloat rawStart = [range[0] doubleValue], rawStop = [range[1] doubleValue];
        if (!isfinite(rawStart) || !isfinite(rawStop) || rawStop < rawStart) continue;
        CGFloat start = MAX(0, MIN(1, rawStart));
        CGFloat stop = MAX(start, MIN(1, rawStop));
        UIRectFill(CGRectMake(start * width, 0, MAX(0, (stop-start) * width), self.bounds.size.height));
    }
}
@end

@implementation LGVideoController (PlaybackControls)
- (void)presentPlaybackDialog:(UIAlertController *)dialog {
    if (self.retired || self.lockHidden || ![self canPlay:NO]) return;
    if (self.portraitTabletop) { [self presentPortraitMenu:dialog]; return; }
    UIViewController *presented = self.presentedViewController;
    if (presented) {
        if (![presented isKindOfClass:UIAlertController.class]) return;
        [presented dismissViewControllerAnimated:NO completion:^{ [self presentPlaybackDialog:dialog]; }];
    } else {
        [self.menuOutsideTap.view removeGestureRecognizer:self.menuOutsideTap];
        self.menuOutsideTap = nil;
        [self presentViewController:dialog animated:YES completion:^{
            // Text-entry dialogs retain explicit Apply/Cancel. Selection menus
            // dismiss from the backdrop, including compact scrollable alerts.
            if (dialog.textFields.count || self.presentedViewController != dialog) return;
            self.menuOutsideTap = [[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(dismissPlaybackMenu:)];
            self.menuOutsideTap.delegate = self;
            self.menuOutsideTap.cancelsTouchesInView = NO;
            [dialog.presentationController.containerView addGestureRecognizer:self.menuOutsideTap];
        }];
    }
}
- (void)dismissPlaybackMenu:(id)sender {
    [self.menuOutsideTap.view removeGestureRecognizer:self.menuOutsideTap];
    self.menuOutsideTap = nil;
    [self.presentedViewController dismissViewControllerAnimated:YES completion:^{ [self scheduleControls]; }];
}
- (void)emitCommand:(NSString *)name value:(NSString *)value {
    if (!self.retired && !self.lockHidden && [self canPlay:NO] && self.command) self.command(name, value ?: @"");
}
- (NSDictionary *)playbackOptions {
    NSData *data = [self.optionsJSON dataUsingEncoding:NSUTF8StringEncoding];
    id value = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
    return [value isKindOfClass:NSDictionary.class] ? value : @{};
}
- (void)configurePlayback:(NSString *)settings queue:(NSString *)queue {
    self.optionsJSON = settings; self.queueJSON = queue;
    [self applyPlaybackOptions];
    [self updateVideoHeader];
}
- (void)applyPlaybackOptions {
    if (!self.player || self.retired) return;
    if (self.pendingSubtitleURL.length) [self attachSubtitleURL:self.pendingSubtitleURL];
    NSDictionary *options = [self playbackOptions];
    float rate = [options[@"rate"] floatValue];
    UIButtonConfiguration *speed = self.portraitSpeedButton.configuration;
    speed.title = [NSString stringWithFormat:@"%g×", rate >= .5 && rate <= 2. ? rate : 1.];
    self.portraitSpeedButton.configuration = speed;
    self.player.currentVideoSubTitleDelay = [options[@"subtitle_delay_ms"] longLongValue] * 1000;
    self.player.currentAudioPlaybackDelay = [options[@"audio_delay_ms"] longLongValue] * 1000;
    // A session subtitle-menu adjustment wins over later settings refreshes.
    // A new controller starts with zero and therefore uses the configured default.
    // 20/22 is approximately two points smaller than the former 22 pt
    // baseline. VLCKit exposes a *relative scale*, not a point-size setter.
    float configuredScale = options[@"subtitle_scale"] ? [options[@"subtitle_scale"] floatValue] : 1.f;
    if (!isfinite(configuredScale) || configuredScale <= 0) configuredScale = 1.f;
    float subtitleScale = self.sessionSubtitleScale > 0 ? self.sessionSubtitleScale : configuredScale * (20.f / 22.f);
    self.player.currentSubTitleFontScale = MAX(.5f, MIN(3.f, subtitleScale));
    [self.view setNeedsLayout];
    [self.view layoutIfNeeded];
    [self applyPictureSize];
    NSString *audio = options[@"audio_language"] ?: @"", *subtitle = options[@"subtitle_language"] ?: @"";
    NSString *signature = [NSString stringWithFormat:@"%@:%@:%lu:%lu", audio, subtitle, (unsigned long)self.player.audioTracks.count, (unsigned long)self.player.textTracks.count];
    if (![self.languageSignature isEqualToString:signature]) {
        self.languageSignature = signature;
        for (NSArray *entry in @[@[audio, self.player.audioTracks ?: @[]], @[subtitle, self.player.textTracks ?: @[]]]) {
            NSString *preferred = entry[0];
            if (!preferred.length) continue;
            for (VLCMediaPlayerTrack *track in entry[1])
                if (track.language.length && [track.language caseInsensitiveCompare:preferred] == NSOrderedSame) { track.selectedExclusively = YES; break; }
        }
    }
    for (NSString *key in @[@"audio_track", @"subtitle_track"]) {
        NSNumber *selected = options[key];
        if (![selected isKindOfClass:NSNumber.class]) continue;
        BOOL text = [key isEqualToString:@"subtitle_track"];
        NSArray *tracks = text ? self.player.textTracks : self.player.audioTracks;
        NSInteger index = selected.integerValue;
        if (text && index == -1) [self.player deselectAllTextTracks];
        else if (index >= 0 && index < (NSInteger)tracks.count) {
            VLCMediaPlayerTrack *track = tracks[index];
            if (!track.isSelected) track.selectedExclusively = YES;
        }
    }
    // Apply requested speed after the other output and track preferences.
    [self applyPlaybackRate];
}
- (void)applyPlaybackRate {
    if (!self.player || self.retired || self.rateChangePending) return;
    float rate = [[self playbackOptions][@"rate"] floatValue];
    if (rate < .5 || rate > 2. || !isfinite(rate) || fabsf(self.player.rate - rate) < .001f) return;
    if (self.player.state == VLCMediaPlayerStatePaused && !self.player.isPlaying) {
        int64_t position = [self positionMilliseconds];
        self.player.rate = rate;
        // Discard pictures/audio queued at the previous rate without moving
        // the user's timeline checkpoint or adding an Undo seek entry.
        if (position >= 0 && self.player.isSeekable) {
            self.startMilliseconds = position;
            self.resumeSeekSubmitted = YES;
            self.player.time = [VLCTime timeWithNumber:@(position)];
        }
    } else if (self.player.isPlaying) {
        // A live request can update VLCKit's rate getter without changing its
        // clock. Apply after native Pause acknowledges it, then reconcile the
        // latest Play intent. User/OS Pause cancels that automatic resume.
        self.rateChangePending = YES;
        if (!self.pausePending) {
            self.pausePending = YES;
            [self.player pause];
        }
    }
    // Opening/Stopped inputs receive the preference from the Playing callback.
}
- (void)applyPictureSize {
    if (!self.player || !self.movie) return;
    NSString *aspect = [[self playbackOptions][@"aspect"] isEqualToString:@"fill"] ? @"fill" : @"fit";
    NSString *label = [aspect isEqualToString:@"fill"] ? @"Fit view" : @"Fill view";
    if (![self.pictureButton.accessibilityLabel isEqualToString:label]) [self updateItem:self.pictureButton label:label];
    CGRect bounds = self.movie.bounds;
    NSString *geometry = [NSString stringWithFormat:@"%@:%g:%g", aspect, bounds.size.width, bounds.size.height];
    if ([self.pictureGeometry isEqualToString:geometry]) return;
    self.pictureGeometry = geometry;
    [self configureVideoDynamicRange:self.movie.layer];
    self.player.scaleFactor = 0.f;
    if ([aspect isEqualToString:@"fill"] && bounds.size.width > 0 && bounds.size.height > 0)
        [self.player setCropRatioWithNumerator:(unsigned)bounds.size.width denominator:(unsigned)bounds.size.height];
    else [self.player setCropRatioWithNumerator:0 denominator:0];
}
- (void)setting:(NSString *)key value:(id)value {
    NSMutableDictionary *options = [[self playbackOptions] mutableCopy]; options[key] = value;
    NSData *data = [NSJSONSerialization dataWithJSONObject:options options:0 error:nil];
    self.optionsJSON = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    [self applyPlaybackOptions];
    [self emitCommand:@"settings" value:self.optionsJSON];
}
- (void)promptValue:(NSString *)title key:(NSString *)key numeric:(BOOL)numeric {
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:title message:nil preferredStyle:UIAlertControllerStyleAlert];
    [alert addTextFieldWithConfigurationHandler:^(UITextField *field) {
        field.text = [[self playbackOptions][key] description];
        if (numeric) field.keyboardType = UIKeyboardTypeNumbersAndPunctuation;
    }];
    UITextField *input = alert.textFields.firstObject;
    [alert lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    [alert lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:@"Apply" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        NSString *text = input.text ?: @"";
        if (numeric) {
            NSScanner *scan = [NSScanner scannerWithString:text]; long long value;
            if (![scan scanLongLong:&value] || !scan.isAtEnd || llabs(value) > 600000) { [self showStatus:@"Enter a delay within ±600000 ms."]; return; }
            [self setting:key value:@(value)];
        } else [self emitCommand:@"settings" value:({
            NSMutableDictionary *settings = [[self playbackOptions] mutableCopy]; settings[key] = text;
            [[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:settings options:0 error:nil] encoding:NSUTF8StringEncoding];
        })];
    }]];
    [self presentPlaybackDialog:alert];
}
- (void)goToTime:(id)sender {
    if (![self canPlay:NO] || self.controlsLocked) return;
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"Go to time" message:@"Seconds, MM:SS or HH:MM:SS" preferredStyle:UIAlertControllerStyleAlert];
    [alert addTextFieldWithConfigurationHandler:^(UITextField *field) { field.placeholder = @"12:34"; field.keyboardType = UIKeyboardTypeNumbersAndPunctuation; }];
    UITextField *input = alert.textFields.firstObject;
    [alert lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    [alert lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:@"Go" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self emitCommand:@"seek" value:input.text]; }]];
    [self presentPlaybackDialog:alert];
}
- (void)undoSeek:(id)sender {
    if (NSProcessInfo.processInfo.systemUptime > self.undoUntil) return;
    int64_t position = self.undoMilliseconds;
    self.undoUntil = 0;
    [self seekToMilliseconds:position];
    self.undoUntil = 0; self.undoSeekButton.hidden = YES;
}
- (void)toggleMute:(id)sender {
    if (![self canPlay:NO] || self.controlsLocked) return;
    BOOL muted = self.audioSuppressed ? self.resumeMuted : self.player.audio.muted;
    if (self.audioSuppressed) self.resumeMuted = !muted;
    else self.player.audio.muted = !muted;
    [self showStatus:muted ? @"Sound on" : @"Muted"];
}
- (void)toggleControlLock:(id)sender {
    if (![self canPlay:NO]) return;
    self.controlsLocked = !self.controlsLocked;
    self.unlockButton.hidden = !self.controlsLocked;
    self.seek.enabled = !self.controlsLocked;
    [self setControlsShown:!self.controlsLocked];
    [self.view bringSubviewToFront:self.unlockButton];
}
- (void)doubleTapVideo:(UITapGestureRecognizer *)tap {
    if (self.controlsLocked || ![self canPlay:NO]) return;
    CGFloat x = [tap locationInView:self.movie].x, width = self.movie.bounds.size.width;
    if (x < width * .4) [self skipMilliseconds:-10000];
    else if (x > width * .6) [self skipMilliseconds:10000];
    else [self togglePlay:tap];
}
- (BOOL)canBecomeFirstResponder { return YES; }
- (NSArray<UIKeyCommand *> *)keyCommands {
    NSMutableArray *result = [NSMutableArray array];
    for (NSArray *entry in @[@[@" ", @"togglePlay:"], @[UIKeyInputLeftArrow, @"back:"],
        @[UIKeyInputRightArrow, @"forward:"], @[@"m", @"toggleMute:"], @[@"f", @"toggleFullscreen:"],
        @[@"g", @"goToTime:"], @[@"n", @"nextVideo:"], @[@"p", @"previousVideo:"],
        @[UIKeyInputEscape, @"escapePlayback:"]]) {
        if (self.controlsLocked && ![entry[1] isEqualToString:@"escapePlayback:"]) continue;
        [result addObject:[UIKeyCommand keyCommandWithInput:entry[0] modifierFlags:0 action:NSSelectorFromString(entry[1])]];
    }
    return result;
}
- (void)escapePlayback:(id)sender {
    if (self.controlsLocked) [self toggleControlLock:sender];
    else if (self.fullscreen) [self toggleFullscreen:sender];
}
- (void)nextVideo:(id)sender { if (!self.controlsLocked) [self emitCommand:@"next" value:@""]; }
- (void)previousVideo:(id)sender { if (!self.controlsLocked) [self emitCommand:@"previous" value:@""]; }
- (void)queueVideos:(id)sender {
    UIAlertController *menu = [self menu:@"Current folder" sender:sender];
    NSArray *rows = [NSJSONSerialization JSONObjectWithData:[self.queueJSON dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
    for (NSDictionary *row in rows) {
        NSString *title = [NSString stringWithFormat:@"%@%@", [row[@"current"] boolValue] ? @"✓ " : @"", row[@"name"]];
        [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:title style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self emitCommand:@"queue" value:row[@"path"]]; }]];
    }
    [self presentPlaybackDialog:menu];
}
- (void)togglePictureSize:(id)sender {
    BOOL filled = [[self playbackOptions][@"aspect"] isEqualToString:@"fill"];
    [self setting:@"aspect" value:filled ? @"fit" : @"fill"];
}
- (void)speedOptions:(id)sender {
    UIAlertController *menu = [self menu:@"Speed · pitch preserved" sender:sender];
    for (NSNumber *rate in @[@.5,@.75,@1.,@1.25,@1.5,@1.75,@2.])
        [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:[NSString stringWithFormat:@"%@×",rate] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self setting:@"rate" value:rate]; }]];
    [self presentPlaybackDialog:menu];
}
- (void)subtitleOptions:(id)sender {
    UIAlertController *menu = [self menu:@"Subtitles and audio" sender:sender];
    [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:@"Choose subtitle file…" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self emitCommand:@"subtitleBrowse" value:@""]; }]];
    for (NSArray *entry in @[@[@"Subtitle delay (ms; positive = later)", @"subtitle_delay_ms"], @[@"Audio delay (ms; positive = later)", @"audio_delay_ms"], @[@"Preferred audio language (e.g. fr)", @"audio_language"], @[@"Preferred subtitle language (e.g. en)", @"subtitle_language"]])
        [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:entry[0] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self promptValue:entry[0] key:entry[1] numeric:[entry[1] hasSuffix:@"_ms"]]; }]];
    [self presentPlaybackDialog:menu];
}
- (void)subtitleSizeOptions:(id)sender {
    UIAlertController *menu = [self menu:@"Subtitle size · current session" sender:sender];
    for (NSNumber *scale in @[@.75,@1.,@1.25,@1.5,@2.]) {
        [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:[NSString stringWithFormat:@"Subtitle size %@× (session)",scale] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
            self.sessionSubtitleScale = MAX(.5f, MIN(3.f, scale.floatValue * (20.f / 22.f)));
            self.player.currentSubTitleFontScale = self.sessionSubtitleScale;
            [self showStatus:[NSString stringWithFormat:@"Subtitle size %.0f%% (session)", self.sessionSubtitleScale * 100]];
        }]];
    }
    [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:@"Reset subtitle size (session)" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        self.sessionSubtitleScale = 0;
        [self applyPlaybackOptions];
        [self showStatus:@"Subtitle size reset"];
    }]];
    [self presentPlaybackDialog:menu];
}
- (void)hdrDisplayOptions:(id)sender {
    if (![self canPlay:NO]) return;
    UIAlertController *menu = [self menu:@"HDR display mode (session)" sender:sender];
    if (@available(iOS 26.0, *)) {
        BOOL forced = self.forceMaximumHDR;
        [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:forced ? @"System-managed HDR" : @"✓ System-managed HDR"
            style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
                [self setForcedMaximumHDRForSession:NO];
                [self showStatus:@"HDR: system-managed (session)"];
            }]];
        [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:forced ? @"✓ Maximum HDR (previous behavior)" : @"Maximum HDR (previous behavior)"
            style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
                [self setForcedMaximumHDRForSession:YES];
                [self showStatus:@"HDR: maximum (session)"];
            }]];
    } else {
        menu.message = @"This iOS version does not support the system-managed HDR selector. The existing HDR output remains enabled.";
    }
    [self presentPlaybackDialog:menu];
}
- (void)playbackTools:(id)sender {
    if (![self canPlay:NO] || self.controlsLocked) return;
    UIAlertController *menu = [self menu:@"Playback" sender:sender];
    for (NSArray *entry in @[@[@"Go to time…", @"goToTime:"], @[@"Speed…", @"speedOptions:"],
        @[@"HDR display mode…", @"hdrDisplayOptions:"], @[@"Subtitle size…", @"subtitleSizeOptions:"], @[@"Subtitles and audio…", @"subtitleOptions:"],
        @[@"Show in folder", @"showInFolder:"], @[@"Favourite file", @"favouriteFile:"], @[@"Current folder…", @"queueVideos:"], @[@"Previous episode", @"previousVideo:"],
        @[@"Next episode", @"nextVideo:"], @[@"Mute / unmute", @"toggleMute:"], @[@"Lock controls", @"toggleControlLock:"]]) {
        [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:entry[0] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
            SEL selector = NSSelectorFromString(entry[1]);
            void (*invoke)(id, SEL, id) = (void (*)(id, SEL, id))[self methodForSelector:selector]; invoke(self,selector,sender);
        }]];
    }
    [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:@"Start over" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self seekToMilliseconds:0]; }]];
    BOOL autoNext = [[self playbackOptions][@"autoplay_next"] boolValue];
    [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:autoNext ? @"✓ Play next automatically" : @"Play next automatically" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self setting:@"autoplay_next" value:@(!autoNext)]; }]];
    [self presentPlaybackDialog:menu];
}
- (void)attachSubtitleURL:(NSString *)url {
    self.pendingSubtitleURL = url;
    if ([self canPlay:NO] && self.player.isPlaying &&
        [self.player addPlaybackSlave:[NSURL URLWithString:url] type:VLCMediaPlaybackSlaveTypeSubtitle enforce:YES])
        self.pendingSubtitleURL = nil;
}
- (void)showSubtitleBrowser:(NSString *)json {
    if (![self canPlay:NO]) return;
    NSArray *rows = [NSJSONSerialization JSONObjectWithData:[json dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
    UIAlertController *menu = [self menu:@"Choose subtitles · current source" sender:self.playButton];
    for (NSDictionary *row in rows) {
        NSString *label = [NSString stringWithFormat:@"%@%@", [row[@"directory"] boolValue] ? @"▸ " : @"", row[@"name"]];
        [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:label style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self emitCommand:[row[@"directory"] boolValue] ? @"subtitleBrowse" : @"subtitleAttach" value:row[@"path"]]; }]];
    }
    [self presentPlaybackDialog:menu];
}
- (void)showCachedRanges:(NSString *)json {
    if (![self canPlay:NO]) return;
    NSDictionary *value = [NSJSONSerialization JSONObjectWithData:[json dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
    if (![value isKindOfClass:NSDictionary.class]) return;
    self.cacheApproximate = [value[@"approximate"] boolValue];
    LGVideoCachedRanges *strip = (LGVideoCachedRanges *)self.cacheStrip;
    id suppliedRanges = value[@"ranges"];
    strip.ranges = [value[@"local"] boolValue] ? @[@[@0,@1]] : ([suppliedRanges isKindOfClass:NSArray.class] ? suppliedRanges : @[]);
    strip.accessibilityLabel = [value[@"approximate"] boolValue] ? @"Approximate cached file ranges" : @"Timestamp indexed cached ranges";
    [strip setNeedsDisplay];
}
- (void)showInFolder:(id)sender { [self emitCommand:@"showInFolder" value:@""]; }
- (void)favouriteFile:(id)sender { [self emitCommand:@"favourite" value:@""]; }
- (void)updateVideoHeader {
    NSDictionary *options = [self playbackOptions];
    self.videoTitle.text = options[@"video_title"] ?: @"";
    self.sourceLabel.text = options[@"source_label"] ?: @"";
    self.sourceIcon.image = [UIImage systemImageNamed:[options[@"source_remote"] boolValue] ? @"cloud" : @"internaldrive"];
    self.sourceIcon.accessibilityLabel = self.sourceLabel.text;
}
- (void)showVideoLocation:(UILongPressGestureRecognizer *)gesture {
    if (gesture.state != UIGestureRecognizerStateBegan || ![self canPlay:NO]) return;
    UIAlertController *dialog = [UIAlertController alertControllerWithTitle:@"Document location"
        message:[self playbackOptions][@"video_path"] preferredStyle:UIAlertControllerStyleAlert];
    [dialog lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:nil]];
    [self presentPlaybackDialog:dialog];
}
- (void)installPlaybackTools {
    UIVisualEffect *effect;
    if (@available(iOS 26.0, *)) effect = [UIGlassEffect effectWithStyle:UIGlassEffectStyleRegular];
    else effect = [UIBlurEffect effectWithStyle:UIBlurEffectStyleSystemThinMaterialDark];
    UIVisualEffectView *header = [[UIVisualEffectView alloc] initWithEffect:effect];
    header.frame = CGRectMake(0, 0, 320, 48);
    [header addGestureRecognizer:[[UILongPressGestureRecognizer alloc] initWithTarget:self action:@selector(showVideoLocation:)]];
    header.overrideUserInterfaceStyle = UIUserInterfaceStyleDark;
    header.layer.cornerRadius = 16;
    header.clipsToBounds = YES;
    self.videoHeader = header;
    self.deckHeaderHeight = [header.heightAnchor constraintEqualToConstant:44];
    UIStackView *identity = [[UIStackView alloc] init];
    self.videoIdentity = identity;
    identity.axis = UILayoutConstraintAxisVertical;
    identity.alignment = UIStackViewAlignmentCenter;
    identity.spacing = 2;
    identity.translatesAutoresizingMaskIntoConstraints = NO;
    [header.contentView addSubview:identity];
    [NSLayoutConstraint activateConstraints:@[
        [identity.leadingAnchor constraintEqualToAnchor:header.contentView.leadingAnchor constant:12],
        [identity.trailingAnchor constraintEqualToAnchor:header.contentView.trailingAnchor constant:-12],
        [identity.centerYAnchor constraintEqualToAnchor:header.contentView.centerYAnchor]]];
    Class titleClass = NSClassFromString(@"CommonUtilsPanningTitle") ?: UILabel.class;
    self.videoTitle = [[titleClass alloc] init];
    self.videoTitle.textColor = UIColor.whiteColor;
    self.videoTitle.font = [UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];
    self.videoTitle.adjustsFontForContentSizeCategory = YES;
    self.videoTitle.lineBreakMode = NSLineBreakByTruncatingMiddle;
    self.videoTitle.textAlignment = NSTextAlignmentCenter;
    [identity addArrangedSubview:self.videoTitle];
    [self.videoTitle.widthAnchor constraintLessThanOrEqualToAnchor:identity.widthAnchor].active = YES;
    self.sourceIcon = [[UIImageView alloc] init];
    self.sourceIcon.tintColor = UIColor.whiteColor;
    self.sourceIcon.contentMode = UIViewContentModeScaleAspectFit;
    [self.sourceIcon.widthAnchor constraintEqualToConstant:18].active = YES;
    [self.sourceIcon.heightAnchor constraintEqualToConstant:18].active = YES;
    self.sourceIcon.isAccessibilityElement = NO;
    self.sourceLabel = [[UILabel alloc] init];
    self.sourceLabel.textColor = UIColor.whiteColor;
    self.sourceLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleCaption1];
    self.sourceLabel.adjustsFontForContentSizeCategory = YES;
    UIStackView *source = [[UIStackView alloc] initWithArrangedSubviews:@[self.sourceIcon, self.sourceLabel]];
    source.spacing = 6;
    source.alignment = UIStackViewAlignmentCenter;
    [identity addArrangedSubview:source];
    self.navigationItem.titleView = header;
    [self updateVideoHeader];
    LGVideoCachedRanges *strip = [[LGVideoCachedRanges alloc] init];
    strip.backgroundColor = UIColor.clearColor;
    strip.userInteractionEnabled = NO;
    strip.isAccessibilityElement = YES;
    strip.accessibilityLabel = @"Approximate cached byte ranges; variable bitrate can shift time mapping";
    self.cacheStrip = strip;
    [self.seek insertSubview:strip atIndex:0];
    self.undoSeekButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.undoSeekButton setTitle:@"Undo seek" forState:UIControlStateNormal];
    [self.undoSeekButton addTarget:self action:@selector(undoSeek:) forControlEvents:UIControlEventTouchUpInside];
    [self.controls addArrangedSubview:self.undoSeekButton]; self.undoSeekButton.hidden = YES;
    self.unlockButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.unlockButton setTitle:@"Unlock controls" forState:UIControlStateNormal];
    self.unlockButton.backgroundColor = [UIColor colorWithWhite:0 alpha:.8];
    self.unlockButton.translatesAutoresizingMaskIntoConstraints = NO;
    [self.unlockButton addTarget:self action:@selector(toggleControlLock:) forControlEvents:UIControlEventTouchUpInside];
    [self.view addSubview:self.unlockButton];
    [NSLayoutConstraint activateConstraints:@[
        [self.unlockButton.trailingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.trailingAnchor constant:-16],
        [self.unlockButton.bottomAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.bottomAnchor constant:-12],
        [self.unlockButton.heightAnchor constraintGreaterThanOrEqualToConstant:48],
        [self.unlockButton.widthAnchor constraintGreaterThanOrEqualToConstant:140]]];
    self.unlockButton.hidden = YES;
    UITapGestureRecognizer *doubleTap = [[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(doubleTapVideo:)];
    doubleTap.numberOfTapsRequired = 2; doubleTap.delegate = self;
    for (UIGestureRecognizer *gesture in self.view.gestureRecognizers)
        if ([gesture isKindOfClass:UITapGestureRecognizer.class]) [gesture requireGestureRecognizerToFail:doubleTap];
    [self.view addGestureRecognizer:doubleTap];

}
- (void)layoutPlaybackTools {
    // The centre of the thumb (not its edge) defines the timeline endpoints.
    // UIKit's trackRect and thumbRect incorporate the platform's thumb inset.
    CGRect track = [self.seek trackRectForBounds:self.seek.bounds];
    CGRect low = [self.seek thumbRectForBounds:self.seek.bounds trackRect:track value:self.seek.minimumValue];
    CGRect high = [self.seek thumbRectForBounds:self.seek.bounds trackRect:track value:self.seek.maximumValue];
    CGFloat left = CGRectGetMidX(low), right = CGRectGetMidX(high);
    if (right <= left) { left = CGRectGetMinX(track); right = CGRectGetMaxX(track); }
    // Remain inside the UISlider bounds (rather than drawing below and risking clipping).
    CGFloat y = MIN(MAX(0, CGRectGetMaxY(track) + 3), MAX(0, self.seek.bounds.size.height - 4));
    self.cacheStrip.frame = CGRectMake(left, y, MAX(0, right-left), 4);
    [self.seek sendSubviewToBack:self.cacheStrip];
    [self.cacheStrip setNeedsDisplay];
    if (self.portraitTabletop) return;
    if (self.tabletop || self.view.bounds.size.width < 500 ||
        self.traitCollection.verticalSizeClass == UIUserInterfaceSizeClassCompact) {
        // On narrow or short phone windows keep the title above playback controls, away from navigation actions.
        // Keep the upper display for video. Identity belongs with the controls
        // on the lower panel, independent of the hidden navigation rail's inset.
        if (self.videoHeader.superview != self.controls) {
            self.navigationItem.titleView = nil;
            [self.videoHeader removeFromSuperview];
            self.videoHeader.translatesAutoresizingMaskIntoConstraints = NO;
            [self.controls insertArrangedSubview:self.videoHeader atIndex:0];
            self.deckHeaderHeight.active = YES;
        }
        return;
    }
    if (self.videoHeader.superview == self.controls) {
        [self.controls removeArrangedSubview:self.videoHeader];
        [self.videoHeader removeFromSuperview];
        self.deckHeaderHeight.active = NO;
        self.videoHeader.translatesAutoresizingMaskIntoConstraints = YES;
        self.videoHeader.frame = CGRectMake(0, 0, 320, 48);
    }
    UINavigationBar *bar = self.navigationController.navigationBar;
    if (bar.bounds.size.width > bar.bounds.size.height && self.view.bounds.size.width < 500) {
        // UIKit omits titleView entirely beside compact transport groups.
        // Use their remaining top-row gap without moving the native buttons.
        if (self.videoHeader.superview != self.view) {
            self.navigationItem.titleView = nil;
            [self.view addSubview:self.videoHeader];
        }
        CGRect barFrame = [bar convertRect:bar.bounds toView:self.view];
        CGRect safe = self.view.safeAreaLayoutGuide.layoutFrame;
        self.videoHeader.frame = CGRectMake(CGRectGetMinX(safe) + 68,
            CGRectGetMidY(barFrame) - 24, MAX(44, safe.size.width - 304), 48);
        return;
    }
    if (self.navigationItem.titleView != self.videoHeader) {
        [self.videoHeader removeFromSuperview];
        self.navigationItem.titleView = self.videoHeader;
    }
    if (bar.bounds.size.height > bar.bounds.size.width && self.videoHeader.superview && self.view.window) {
        // A side rail still leaves a horizontal title area above the movie.
        // Align it to the top row, as for the other mobile document viewers.
        UIWindow *window = self.view.window;
        CGPoint center = [self.videoHeader.superview convertPoint:
            CGPointMake(CGRectGetMidX(window.bounds), window.safeAreaInsets.top + 6 + self.videoHeader.bounds.size.height / 2)
            fromView:window];
        self.videoHeader.center = CGPointMake(self.videoHeader.center.x, center.y);
    }
}
@end
