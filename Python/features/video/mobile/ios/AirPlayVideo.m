// Keep the Logistics deck in front of AVKit so the phone and Siri Remote
// control the same playback clock during native AirPlay.
@implementation LGVideoController (AirPlay)
- (void)installAirPlayControls {
    UIStackView *row = [UIStackView new];
    row.alignment = UIStackViewAlignmentCenter;
    row.spacing = 4;
    self.airPlayLabel = [UILabel new];
    self.airPlayLabel.text = @"AirPlay";
    self.airPlayLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleFootnote];
    self.airPlayLabel.adjustsFontForContentSizeCategory = YES;
    self.airPlayLabel.textColor = UIColor.whiteColor;
    [row addArrangedSubview:self.airPlayLabel];
    self.airPlayPicker = [[AVRoutePickerView alloc] initWithFrame:CGRectZero];
    self.airPlayPicker.prioritizesVideoDevices = YES;
    self.airPlayPicker.tintColor = UIColor.whiteColor;
    self.airPlayPicker.delegate = self;
    self.airPlayPicker.accessibilityIdentifier = @"video.AirPlay";
    [self.airPlayPicker.widthAnchor constraintEqualToConstant:44].active = YES;
    [self.airPlayPicker.heightAnchor constraintEqualToConstant:44].active = YES;
    [row addArrangedSubview:self.airPlayPicker];
    UIStackView *centered = [[UIStackView alloc] initWithArrangedSubviews:@[row]];
    centered.axis = UILayoutConstraintAxisVertical;
    centered.alignment = UIStackViewAlignmentCenter;
    [self.controls addArrangedSubview:centered];
}

- (BOOL)hasAirPlayAudioRoute {
    for (AVAudioSessionPortDescription *port in AVAudioSession.sharedInstance.currentRoute.outputs) {
        if ([port.portType isEqualToString:AVAudioSessionPortAirPlay]) return YES;
    }
    return NO;
}

- (BOOL)holdLocalPlayForAirPlay {
    if (!self.airPlayAvailable || self.casting || ![self hasAirPlayAudioRoute]) return NO;
    self.airPlayResumeLocal = YES;
    [self showStatus:@"Choose this device in AirPlay to continue here."];
    return YES;
}

- (void)routePickerViewWillBeginPresentingRoutes:(AVRoutePickerView *)picker {
    self.airPlayPickerOpen = YES;
    self.airPlayRouteDeadline = 0;
    [self setControlsShown:YES];
}

- (void)routePickerViewDidEndPresentingRoutes:(AVRoutePickerView *)picker {
    self.airPlayPickerOpen = NO;
    if ([self hasAirPlay]) {
        [self updateAirPlay];
        return;
    }
    // The audio route notification can arrive after the route sheet closes.
    self.airPlayRouteDeadline = NSProcessInfo.processInfo.systemUptime + 3;
    [self updateAirPlayRoute];
}

- (void)updateAirPlayRoute {
    if (!self.airPlayAvailable || self.retired || self.casting || self.pipActive) return;
    BOOL external = [self hasAirPlayAudioRoute];
    if (external && self.playRequested) {
        [self pause];
        self.airPlayResumeLocal = YES;
    }
    if (!external && self.airPlayResumeLocal && !self.airPlayPickerOpen && !self.airPlayPreparing &&
        [self canPlay:NO]) {
        self.airPlayResumeLocal = NO;
        [self showStatus:@""];
        [self startByUser];
    }
    if (self.airPlayRouteDeadline <= 0) return;
    if (NSProcessInfo.processInfo.systemUptime > self.airPlayRouteDeadline) {
        self.airPlayRouteDeadline = 0;
        return;
    }
    if (external && !self.airPlayPreparing && [self allowsAirPlay] && [self canPlay:NO]) {
        self.airPlayRouteDeadline = 0;
        self.airPlayPreparing = YES;
        [self emitCommand:@"airplay" value:@""];
    }
}

- (void)airPlayPreparationFailed:(NSString *)message {
    self.airPlayPreparing = NO;
    if ([self hasAirPlayAudioRoute])
        message = [message stringByAppendingString:@" Choose this device in AirPlay to continue here."];
    [self showStatus:message];
    [self updateAirPlayRoute];
}

- (BOOL)hasAirPlay { return self.airPlayPlayer != nil; }

- (BOOL)allowsAirPlay {
    return !self.retired && !self.restricted && !self.lockHidden &&
        UIApplication.sharedApplication.protectedDataAvailable && self.airPlayAllowed && self.airPlayAllowed();
}

- (int64_t)airPlayTime:(CMTime)time {
    double seconds = CMTimeGetSeconds(time);
    return isfinite(seconds) && seconds >= 0 && seconds < 1e7 ? llround(seconds * 1000) : -1;
}

- (BOOL)beginAirPlay:(AVPlayer *)player URL:(NSURL *)url title:(NSString *)title {
    self.airPlayPreparing = NO;
    if ([self hasAirPlay] || ![self allowsAirPlay] || ![self canPlay:NO] ||
        self.pipActive || self.casting || ![self hasAirPlayAudioRoute]) return NO;
    int64_t position = [self positionMilliseconds];
    self.airPlayResumeLocal |= self.playRequested;
    [self pause];  // Silence VLC before handing the same timeline to AVKit.
    [self moveVideoToExternalHost:nil];
    [self clearPausePresentation];
    self.movie.hidden = YES;
    self.ended = NO;
    self.airPlayStartPosition = position;
    self.airPlaySeekTarget = position > 0 ? position : -1;
    self.airPlayConnectionDeadline = 0;
    self.airPlayWasExternal = NO;

    AVMutableMetadataItem *name = [AVMutableMetadataItem new];
    name.identifier = AVMetadataCommonIdentifierTitle;
    name.value = title;
    AVURLAsset *asset = [AVURLAsset URLAssetWithURL:url
        options:@{AVURLAssetReferenceRestrictionsKey: @(AVAssetReferenceRestrictionForbidAll)}];
    AVPlayerItem *item = [AVPlayerItem playerItemWithAsset:asset];
    item.externalMetadata = @[name];
    self.airPlayPlayer = player;
    self.airPlayPlayer.allowsExternalPlayback = YES;
    self.airPlayPlayer.muted = YES;
    if (@available(iOS 15.0, *)) self.airPlayPlayer.audiovisualBackgroundPlaybackPolicy =
        AVPlayerAudiovisualBackgroundPlaybackPolicyContinuesIfPossible;
    [self.airPlayPlayer replaceCurrentItemWithPlayerItem:item];
    self.airPlayController = [AVPlayerViewController new];
    self.airPlayController.showsPlaybackControls = NO;
    self.airPlayController.allowsPictureInPicturePlayback = NO;
    self.airPlayController.player = player;
    [self addChildViewController:self.airPlayController];
    UIView *surface = self.airPlayController.view;
    surface.userInteractionEnabled = NO;
    surface.alpha = 0;
    surface.accessibilityElementsHidden = YES;
    surface.frame = self.inlineMovie.bounds;
    surface.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    [self.inlineMovie addSubview:surface];
    [self.airPlayController didMoveToParentViewController:self];

    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(airPlayEnded:)
        name:AVPlayerItemDidPlayToEndTimeNotification object:item];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(airPlayFailed:)
        name:AVPlayerItemFailedToPlayToEndTimeNotification object:item];
    [self applyPictureSize];
    [self showStatus:@"Connecting to TV…"];
    [self startAirPlayPlayback];
    return YES;
}

- (void)startAirPlayPlayback {
    if (self.controlsLocked || ![self allowsAirPlay] || ![self canPlay:NO] ||
        !self.requestPlay || !self.requestPlay() || ![self canPlay:NO]) return;
    self.playRequested = YES;
    if (!self.airPlayPlayer.externalPlaybackActive)
        self.airPlayConnectionDeadline = NSProcessInfo.processInfo.systemUptime + 12;
    if (self.ended) [self seekAirPlay:0];
    else if (self.airPlaySeekTarget < 0) [self playAirPlayAtRequestedRate];
    [self updatePlayButton];
}

- (void)seekAirPlay:(int64_t)target {
    if (self.controlsLocked || ![self allowsAirPlay] || ![self canPlay:NO]) return;
    int64_t duration = [self durationMilliseconds];
    self.airPlaySeekTarget = duration > 0 ? MIN(MAX(0, target), duration - 1) : MAX(0, target);
    if (!self.airPlayWasExternal) self.airPlayStartPosition = self.airPlaySeekTarget;
    self.ended = NO;
    if (self.airPlayPlayer.currentItem.status == AVPlayerItemStatusReadyToPlay) [self submitAirPlaySeek];
}

- (void)submitAirPlaySeek {
    int64_t target = self.airPlaySeekTarget;
    self.airPlaySeekPending = YES;
    NSUInteger generation = ++self.airPlaySeekGeneration;
    __weak LGVideoController *owner = self;
    [self.airPlayPlayer seekToTime:CMTimeMake(target, 1000) toleranceBefore:kCMTimeZero
        toleranceAfter:kCMTimeZero completionHandler:^(BOOL finished) {
        dispatch_async(dispatch_get_main_queue(), ^{
            if (!owner.airPlayPlayer || owner.airPlaySeekGeneration != generation) return;
            owner.airPlaySeekPending = NO;
            owner.airPlaySeekTarget = -1;
            if (finished && owner.playRequested && [owner allowsAirPlay] && [owner canPlay:NO])
                [owner playAirPlayAtRequestedRate];
        });
    }];
}

- (void)showAirPlayTracks:(id)sender subtitles:(BOOL)text {
    if (self.controlsLocked || ![self allowsAirPlay] || ![self canPlay:NO]) return;
    AVPlayerItem *item = self.airPlayPlayer.currentItem;
    if (item.status != AVPlayerItemStatusReadyToPlay) {
        [self showStatus:@"AirPlay is loading tracks. Try again in a moment."];
        return;
    }
    [self setControlsShown:YES];
    AVMediaCharacteristic characteristic = text ? AVMediaCharacteristicLegible : AVMediaCharacteristicAudible;
    __weak LGVideoController *owner = self;
    [item.asset loadMediaSelectionGroupForMediaCharacteristic:characteristic
        completionHandler:^(AVMediaSelectionGroup *group, NSError *error) {
            dispatch_async(dispatch_get_main_queue(), ^{
                LGVideoController *controller = owner;
                if (!controller || item != controller.airPlayPlayer.currentItem ||
                    controller.controlsLocked || ![controller allowsAirPlay] || ![controller canPlay:NO]) return;
                UIAlertController *menu = [controller menu:text ? @"TV subtitles" : @"TV audio tracks" sender:sender];
                AVMediaSelectionOption *selected = group ? [item.currentMediaSelection selectedMediaOptionInMediaSelectionGroup:group] : nil;
                if (text && group.allowsEmptySelection) {
                    NSString *label = selected ? @"Subtitles off" : @"✓ Subtitles off";
                    [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:label style:UIAlertActionStyleDefault
                        handler:^(UIAlertAction *action) {
                            if (item == owner.airPlayPlayer.currentItem && !owner.controlsLocked &&
                                [owner allowsAirPlay] && [owner canPlay:NO])
                                [item selectMediaOption:nil inMediaSelectionGroup:group];
                        }]];
                }
                NSArray *playable = [AVMediaSelectionGroup playableMediaSelectionOptionsFromArray:group.options ?: @[]];
                for (AVMediaSelectionOption *option in playable) {
                    NSString *label = [option isEqual:selected] ? [@"✓ " stringByAppendingString:option.displayName] : option.displayName;
                    [menu lg_videoAddAction:[UIAlertAction lg_videoActionWithTitle:label style:UIAlertActionStyleDefault
                        handler:^(UIAlertAction *action) {
                            if (item == owner.airPlayPlayer.currentItem && !owner.controlsLocked &&
                                [owner allowsAirPlay] && [owner canPlay:NO])
                                [item selectMediaOption:option inMediaSelectionGroup:group];
                        }]];
                }
                if (!playable.count) menu.message = error ? @"AirPlay couldn’t load the tracks." :
                    (text ? @"No compatible text subtitles are available for this video." : @"No alternate compatible audio tracks are available.");
                [controller presentPlaybackDialog:menu];
            });
        }];
}

- (void)airPlayEnded:(NSNotification *)note {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (note.object != self.airPlayPlayer.currentItem) return;
        self.ended = YES;
        self.playRequested = NO;
        [self emitCommand:@"ended" value:@""];
    });
}

- (void)airPlayFailed:(NSNotification *)note {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (note.object == self.airPlayPlayer.currentItem)
            [self finishAirPlayWithMessage:@"AirPlay couldn’t play this video."];
    });
}

- (void)updateAirPlay {
    AVPlayer *player = self.airPlayPlayer;
    if (![self allowsAirPlay]) {
        [self detachAirPlayKeepingRoute:NO];
        [self revealSurface];
        [self showStatus:@"AirPlay access changed. Press Play to continue on this device."];
        return;
    }
    if (![self canPlay:NO]) { [self pause]; return; }
    if (![self hasAirPlayAudioRoute] && !player.externalPlaybackActive) {
        [self finishAirPlayWithMessage:nil];
        return;
    }
    if (player.status == AVPlayerStatusFailed || player.currentItem.status == AVPlayerItemStatusFailed) {
        [self finishAirPlayWithMessage:@"AirPlay couldn’t play this video."];
        return;
    }
    if (self.airPlaySeekTarget >= 0 && !self.airPlaySeekPending &&
        player.currentItem.status == AVPlayerItemStatusReadyToPlay) [self submitAirPlaySeek];
    if (player.externalPlaybackActive) {
        self.airPlayConnectionDeadline = 0;
        if (!self.airPlayWasExternal) {
            self.airPlayWasExternal = YES;
            [self applyAirPlayPlaybackOptions];
            if (self.airPlaySeekTarget < 0 &&
                llabs([self airPlayTime:player.currentTime] - self.airPlayStartPosition) > 250)
                [self seekAirPlay:self.airPlayStartPosition];
            self.airPlayLabel.text = @"Playing on TV";
            [self showStatus:@""];
        } else if (![self.airPlayLabel.text isEqualToString:@"Playing on TV"]) {
            self.airPlayLabel.text = @"Playing on TV";
        }
        player.muted = self.airPlaySeekTarget >= 0 || self.resumeMuted;
    } else {
        player.muted = YES;
        if (self.airPlayWasExternal) {
            self.airPlayLabel.text = @"AirPlay";
            if (self.airPlayConnectionDeadline <= 0)
                self.airPlayConnectionDeadline = NSProcessInfo.processInfo.systemUptime + 3;
        }
        if (self.airPlayConnectionDeadline > 0 &&
            NSProcessInfo.processInfo.systemUptime >= self.airPlayConnectionDeadline) {
            [self finishAirPlayWithMessage:@"AirPlay couldn’t connect to the TV."];
            return;
        }
    }
    if (self.airPlaySeekTarget < 0) {
        self.playRequested = player.timeControlStatus != AVPlayerTimeControlStatusPaused;
        if (self.playRequested && self.ended) self.ended = NO;
    }
    [self updatePlayButton];
}

- (void)finishAirPlayWithMessage:(NSString *)message {
    BOOL resume = self.airPlayWasExternal ? self.playRequested : self.airPlayResumeLocal;
    [self detachAirPlayKeepingRoute:[self allowsAirPlay]];
    self.airPlayResumeLocal = resume;
    [self revealSurface];
    if ([self hasAirPlayAudioRoute]) {
        NSString *choose = @"Choose this device in AirPlay to continue here.";
        [self showStatus:message.length ? [NSString stringWithFormat:@"%@ %@", message, choose] : choose];
    } else {
        [self updateAirPlayRoute];
        if (message.length) [self showStatus:message];
    }
}

- (void)detachAirPlayKeepingRoute:(BOOL)keepRoute {
    AVPlayer *player = self.airPlayPlayer;
    if (!player) return;
    self.startMilliseconds = [self positionMilliseconds];
    self.lastPosition = self.startMilliseconds;
    self.airPlaySeekGeneration++;
    self.airPlaySeekPending = NO;
    self.airPlayConnectionDeadline = 0;
    [player pause];
    player.muted = YES;
    [NSNotificationCenter.defaultCenter removeObserver:self name:AVPlayerItemDidPlayToEndTimeNotification
        object:player.currentItem];
    [NSNotificationCenter.defaultCenter removeObserver:self name:AVPlayerItemFailedToPlayToEndTimeNotification
        object:player.currentItem];
    [player.currentItem cancelPendingSeeks];
    self.airPlayController.player = nil;
    [self.airPlayController willMoveToParentViewController:nil];
    [self.airPlayController.view removeFromSuperview];
    [self.airPlayController removeFromParentViewController];
    self.airPlayController = nil;
    if (!keepRoute) player.allowsExternalPlayback = NO;
    [player replaceCurrentItemWithPlayerItem:nil];
    self.airPlayPlayer = nil;
    self.airPlayLabel.text = @"AirPlay";
    self.airPlayPreparing = NO;
    self.playRequested = NO;
    if (!self.retired) {
        [self showStatus:@""];
        [self emitCommand:@"airplayDetached" value:@""];
    }
}
@end
