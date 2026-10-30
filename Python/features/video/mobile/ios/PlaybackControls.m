// Feature-owned controls layered over the decoder/lifecycle controller.
@interface LGVideoCachedRanges : UIView
@property(nonatomic, strong) NSArray *ranges;
@end
@implementation LGVideoCachedRanges
- (void)drawRect:(CGRect)rect {
    [UIColor.systemMintColor setFill];
    CGFloat width = MAX(0, self.bounds.size.width - 32);
    for (NSArray *range in self.ranges) {
        if (![range isKindOfClass:NSArray.class] || range.count != 2) continue;
        CGFloat start = [range[0] doubleValue], stop = [range[1] doubleValue];
        UIRectFill(CGRectMake(16 + start * width, 0, MAX(0, (stop-start) * width), 3));
    }
}
@end

@implementation LGVideoController (PlaybackControls)
- (void)presentPlaybackDialog:(UIAlertController *)dialog {
    if (self.retired || self.lockHidden || ![self canPlay:NO]) return;
    UIViewController *presented = self.presentedViewController;
    if (presented) {
        if (![presented isKindOfClass:UIAlertController.class]) return;
        [presented dismissViewControllerAnimated:NO completion:^{ [self presentPlaybackDialog:dialog]; }];
    } else [self presentViewController:dialog animated:YES completion:nil];
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
    NSDictionary *options = [self playbackOptions];
    float rate = [options[@"rate"] floatValue];
    if (rate >= .5 && rate <= 2.) self.player.rate = rate;
    self.player.currentVideoSubTitleDelay = [options[@"subtitle_delay_ms"] longLongValue] * 1000;
    self.player.currentAudioPlaybackDelay = [options[@"audio_delay_ms"] longLongValue] * 1000;
    if (options[@"subtitle_scale"]) self.player.currentSubTitleFontScale = [options[@"subtitle_scale"] floatValue];
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
}
- (void)applyPictureSize {
    if (!self.player || !self.movie) return;
    NSString *aspect = [self playbackOptions][@"aspect"] ?: @"fit";
    CGRect bounds = self.movie.bounds;
    NSString *geometry = [NSString stringWithFormat:@"%@:%g:%g", aspect, bounds.size.width, bounds.size.height];
    if ([self.pictureGeometry isEqualToString:geometry]) return;
    self.pictureGeometry = geometry;
    self.player.scaleFactor = [aspect isEqualToString:@"original"] ? 1.f : 0.f;
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
    [alert addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    [alert addAction:[UIAlertAction actionWithTitle:@"Apply" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        NSString *text = alert.textFields.firstObject.text ?: @"";
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
    [alert addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    [alert addAction:[UIAlertAction actionWithTitle:@"Go" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self emitCommand:@"seek" value:alert.textFields.firstObject.text]; }]];
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
        [menu addAction:[UIAlertAction actionWithTitle:title style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self emitCommand:@"queue" value:row[@"path"]]; }]];
    }
    [self presentPlaybackDialog:menu];
}
- (void)pictureOptions:(id)sender {
    UIAlertController *menu = [self menu:@"Picture size" sender:sender];
    NSArray *keys = @[@"fit", @"fill", @"original"], *labels = @[@"Fit", @"Fill (crop edges)", @"Original size"];
    for (NSUInteger i=0;i<keys.count;i++) {
        NSString *key = keys[i];
        [menu addAction:[UIAlertAction actionWithTitle:labels[i] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self setting:@"aspect" value:key]; }]];
    }
    [self presentPlaybackDialog:menu];
}
- (void)speedOptions:(id)sender {
    UIAlertController *menu = [self menu:@"Speed · pitch preserved" sender:sender];
    for (NSNumber *rate in @[@.5,@.75,@1.,@1.25,@1.5,@1.75,@2.])
        [menu addAction:[UIAlertAction actionWithTitle:[NSString stringWithFormat:@"%@×",rate] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self setting:@"rate" value:rate]; }]];
    [self presentPlaybackDialog:menu];
}
- (void)subtitleOptions:(id)sender {
    UIAlertController *menu = [self menu:@"Subtitles and audio" sender:sender];
    [menu addAction:[UIAlertAction actionWithTitle:@"Choose subtitle file…" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self emitCommand:@"subtitleBrowse" value:@""]; }]];
    for (NSArray *entry in @[@[@"Subtitle delay (ms; positive = later)", @"subtitle_delay_ms"], @[@"Audio delay (ms; positive = later)", @"audio_delay_ms"], @[@"Preferred audio language (e.g. fr)", @"audio_language"], @[@"Preferred subtitle language (e.g. en)", @"subtitle_language"]])
        [menu addAction:[UIAlertAction actionWithTitle:entry[0] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self promptValue:entry[0] key:entry[1] numeric:[entry[1] hasSuffix:@"_ms"]]; }]];
    for (NSNumber *scale in @[@.75,@1.,@1.25,@1.5,@2.])
        [menu addAction:[UIAlertAction actionWithTitle:[NSString stringWithFormat:@"Subtitle size %@×",scale] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self setting:@"subtitle_scale" value:scale]; }]];
    [self presentPlaybackDialog:menu];
}
- (void)playbackTools:(id)sender {
    if (![self canPlay:NO] || self.controlsLocked) return;
    UIAlertController *menu = [self menu:@"Playback" sender:sender];
    for (NSArray *entry in @[@[@"Go to time…", @"goToTime:"], @[@"Speed…", @"speedOptions:"],
        @[@"Picture size…", @"pictureOptions:"], @[@"Subtitles and audio…", @"subtitleOptions:"],
        @[@"Show in folder", @"showInFolder:"], @[@"Current folder…", @"queueVideos:"], @[@"Previous episode", @"previousVideo:"],
        @[@"Next episode", @"nextVideo:"], @[@"Mute / unmute", @"toggleMute:"], @[@"Lock controls", @"toggleControlLock:"]]) {
        [menu addAction:[UIAlertAction actionWithTitle:entry[0] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
            SEL selector = NSSelectorFromString(entry[1]);
            void (*invoke)(id, SEL, id) = (void (*)(id, SEL, id))[self methodForSelector:selector]; invoke(self,selector,sender);
        }]];
    }
    [menu addAction:[UIAlertAction actionWithTitle:@"Start over" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self seekToMilliseconds:0]; }]];
    BOOL autoNext = [[self playbackOptions][@"autoplay_next"] boolValue];
    [menu addAction:[UIAlertAction actionWithTitle:autoNext ? @"✓ Play next automatically" : @"Play next automatically" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self setting:@"autoplay_next" value:@(!autoNext)]; }]];
    [self presentPlaybackDialog:menu];
}
- (void)attachSubtitleURL:(NSString *)url { if ([self canPlay:NO]) [self.player addPlaybackSlave:[NSURL URLWithString:url] type:VLCMediaPlaybackSlaveTypeSubtitle enforce:YES]; }
- (void)showSubtitleBrowser:(NSString *)json {
    if (![self canPlay:NO]) return;
    NSArray *rows = [NSJSONSerialization JSONObjectWithData:[json dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
    UIAlertController *menu = [self menu:@"Choose subtitles · current source" sender:self.playButton];
    for (NSDictionary *row in rows) {
        NSString *label = [NSString stringWithFormat:@"%@%@", [row[@"directory"] boolValue] ? @"▸ " : @"", row[@"name"]];
        [menu addAction:[UIAlertAction actionWithTitle:label style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) { [self emitCommand:[row[@"directory"] boolValue] ? @"subtitleBrowse" : @"subtitleAttach" value:row[@"path"]]; }]];
    }
    [self presentPlaybackDialog:menu];
}
- (void)showCachedRanges:(NSString *)json {
    if (![self canPlay:NO]) return;
    NSDictionary *value = [NSJSONSerialization JSONObjectWithData:[json dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
    self.cacheApproximate = ![value[@"local"] boolValue];
    LGVideoCachedRanges *strip = (LGVideoCachedRanges *)self.cacheStrip;
    strip.ranges = [value[@"local"] boolValue] ? @[@[@0,@1]] : value[@"ranges"];
    [strip setNeedsDisplay];
}
- (void)showInFolder:(id)sender { [self emitCommand:@"showInFolder" value:@""]; }
- (void)updateVideoHeader {
    NSDictionary *options = [self playbackOptions];
    self.videoTitle.text = options[@"video_title"] ?: @"";
    self.sourceLabel.text = options[@"source_label"] ?: @"";
    self.sourceIcon.image = [UIImage systemImageNamed:[options[@"source_remote"] boolValue] ? @"cloud" : @"internaldrive"];
    self.sourceIcon.accessibilityLabel = self.sourceLabel.text;
}
- (void)installPlaybackTools {
    self.videoHeader = [[UIStackView alloc] init];
    self.videoHeader.axis = UILayoutConstraintAxisVertical;
    self.videoHeader.spacing = 4;
    self.videoHeader.layoutMarginsRelativeArrangement = YES;
    self.videoHeader.layoutMargins = UIEdgeInsetsMake(8, 12, 8, 12);
    self.videoHeader.backgroundColor = [UIColor colorWithWhite:0 alpha:.65];
    self.videoHeader.layer.cornerRadius = 8;
    self.videoHeader.translatesAutoresizingMaskIntoConstraints = NO;
    self.videoTitle = [[UILabel alloc] init];
    self.videoTitle.textColor = UIColor.whiteColor;
    self.videoTitle.font = [UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];
    self.videoTitle.adjustsFontForContentSizeCategory = YES;
    self.videoTitle.lineBreakMode = NSLineBreakByTruncatingMiddle;
    [self.videoHeader addArrangedSubview:self.videoTitle];
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
    [self.videoHeader addArrangedSubview:source];
    [self.view addSubview:self.videoHeader];
    [NSLayoutConstraint activateConstraints:@[
        [self.videoHeader.leadingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.leadingAnchor constant:12],
        [self.videoHeader.trailingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.trailingAnchor constant:-12],
        [self.videoHeader.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor constant:8]]];
    [self updateVideoHeader];
    LGVideoCachedRanges *strip = [[LGVideoCachedRanges alloc] init];
    strip.backgroundColor = UIColor.clearColor; strip.translatesAutoresizingMaskIntoConstraints = NO;
    strip.isAccessibilityElement = YES;
    strip.accessibilityLabel = @"Approximate cached byte ranges; variable bitrate can shift time mapping";
    [strip.heightAnchor constraintEqualToConstant:3].active = YES;
    self.cacheStrip = strip;
    [self.controls addArrangedSubview:strip];
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
@end
