// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

#import <os/log.h>

// Keep the Logistics deck in front of AVKit so the phone and Siri Remote
// control the same playback clock during native AirPlay.
@implementation LGVideoController (AirPlay)
- (void)installAirPlayControls {
    self.airPlayPicker = [[AVRoutePickerView alloc] initWithFrame:CGRectZero];
    self.airPlayPicker.prioritizesVideoDevices = YES;
    self.airPlayPicker.tintColor = UIColor.whiteColor;
    self.airPlayPicker.delegate = self;
    self.airPlayPicker.accessibilityIdentifier = @"video.AirPlay";
    self.airPlayPicker.accessibilityLabel = @"AirPlay";
    [self.airPlayPicker.widthAnchor constraintEqualToConstant:48].active = YES;
    [self.airPlayPicker.heightAnchor constraintEqualToConstant:48].active = YES;
    [self.transport addArrangedSubview:self.airPlayPicker];
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
    // Route notifications can arrive after the sheet closes.
    self.airPlayRouteDeadline = NSProcessInfo.processInfo.systemUptime + 3;
    if ([self hasAirPlay]) {
        [self updateAirPlay];
        return;
    }
    [self updateAirPlayRoute];
}

- (void)updateAirPlayRoute {
    if (!self.airPlayAvailable || self.retired || self.casting || self.pipActive) return;
    BOOL external = [self hasAirPlayAudioRoute];
    if (external) self.localAudioNeedsRefresh = YES;
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
    if (external && !self.airPlayPreparing && [self allowsAirPlay] && [self canPlay:NO] &&
        UIApplication.sharedApplication.applicationState == UIApplicationStateActive) {
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

- (BOOL)hasEstablishedAirPlay {
    return self.airPlayPlayer && (self.airPlayWasExternal || self.airPlayPlayer.externalPlaybackActive);
}

- (BOOL)allowsAirPlay {
    return !self.retired && !self.restricted && !self.lockHidden &&
        ([self protectedDataAvailable] || [self hasEstablishedAirPlay]) &&
        self.airPlayAllowed && self.airPlayAllowed();
}

- (int64_t)airPlayTime:(CMTime)time {
    double seconds = CMTimeGetSeconds(time);
    return isfinite(seconds) && seconds >= 0 && seconds < 1e7 ? llround(seconds * 1000) : -1;
}

- (BOOL)beginAirPlay:(AVPlayer *)player URL:(NSURL *)url title:(NSString *)title {
    self.airPlayPreparing = NO;
    if ([self hasAirPlay] || ![self protectedDataAvailable] ||
        UIApplication.sharedApplication.applicationState != UIApplicationStateActive ||
        ![self allowsAirPlay] || ![self canPlay:NO] ||
        self.pipActive || self.casting || ![self hasAirPlayAudioRoute]) return NO;
    int64_t position = [self positionMilliseconds];
    self.airPlayChapters = [self chapterRows];
    self.airPlayRecovered = NO;
    self.airPlayResumeLocal |= self.playRequested;
    [self pause];  // Silence VLC before handing the same timeline to AVKit.
    [self moveVideoToExternalHost:nil];
    [self clearPausePresentation];
    self.movie.hidden = YES;
    self.ended = NO;
    AVMutableMetadataItem *name = [AVMutableMetadataItem new];
    name.identifier = AVMetadataCommonIdentifierTitle;
    name.value = title;
    self.airPlayPlayer = player;
    self.airPlayPlayer.allowsExternalPlayback = YES;
    if (@available(iOS 15.0, *)) self.airPlayPlayer.audiovisualBackgroundPlaybackPolicy =
        AVPlayerAudiovisualBackgroundPlaybackPolicyContinuesIfPossible;
    [self installAirPlayItemAtURL:url metadata:@[name] position:position];
    self.airPlayController = [AVPlayerViewController new];
    // The AVKit surface is concealed locally below; keep its system playback
    // controls enabled for native transport and media-selection integration.
    self.airPlayController.showsPlaybackControls = YES;
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

    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(airPlayRateChanged:)
        name:AVPlayerRateDidChangeNotification object:player];
    [self applyPictureSize];
    [self showStatus:@"Connecting to TV…"];
    [self startAirPlayPlayback];
    if (self.playRequested) return YES;
    [self detachAirPlay];
    [self revealSurface];
    return NO;
}

- (void)installAirPlayItemAtURL:(NSURL *)url metadata:(NSArray<AVMetadataItem *> *)metadata
                      position:(int64_t)position {
    self.airPlayStartPosition = self.airPlayConfirmedPosition = self.airPlayClock = position;
    self.airPlaySeekTarget = position > 0 ? position : -1;
    self.airPlaySeekDeadline = self.airPlayRouteLossDeadline = 0;
    self.airPlayStartDeadline = 0;
    self.airPlaySeekPending = self.airPlayChapterSeek = NO;
    self.airPlayItemFailed = self.airPlayLockPlaybackIntent = NO;
    self.airPlayAdvanced = self.airPlayWasExternal = self.airPlaySystemPaused = self.airPlaySawTransport = NO;
    self.airPlayLastProgress = self.airPlayLastPoll = NSProcessInfo.processInfo.systemUptime;
    self.airPlayStallGraceUntil = 0;
    self.airPlayTraceState = nil;
    AVURLAsset *asset = [AVURLAsset URLAssetWithURL:url
        options:@{AVURLAssetReferenceRestrictionsKey: @(AVAssetReferenceRestrictionForbidAll)}];
    AVPlayerItem *item = [AVPlayerItem playerItemWithAsset:asset];
    item.externalMetadata = metadata;
    self.airPlayPlayer.muted = YES;
    [self.airPlayPlayer replaceCurrentItemWithPlayerItem:item];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(airPlayEnded:)
        name:AVPlayerItemDidPlayToEndTimeNotification object:item];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(airPlayFailed:)
        name:AVPlayerItemFailedToPlayToEndTimeNotification object:item];
    if (!self.airPlayChapters.count && !self.chaptersInvalidated) {
        __weak LGVideoController *owner = self;
        __weak AVPlayerItem *routeItem = item;
        [asset loadChapterMetadataGroupsBestMatchingPreferredLanguages:NSLocale.preferredLanguages
            completionHandler:^(NSArray<AVTimedMetadataGroup *> *groups, NSError *error) {
            dispatch_async(dispatch_get_main_queue(), ^{
                AVPlayerItem *current = routeItem;
                LGVideoController *controller = owner;
                if (!current || controller.retired || controller.chaptersInvalidated ||
                    controller.airPlayPlayer.currentItem != current) return;
                NSMutableDictionary *chapters = [NSMutableDictionary dictionary];
                for (AVTimedMetadataGroup *group in groups) {
                    int64_t start = [controller airPlayTime:group.timeRange.start];
                    if (start < 0) continue;
                    NSString *title = [AVMetadataItem metadataItemsFromArray:group.items
                        filteredByIdentifier:AVMetadataCommonIdentifierTitle].firstObject.stringValue;
                    chapters[@(start)] = title.length ? title :
                        [NSString stringWithFormat:@"Chapter %lu", (unsigned long)chapters.count + 1];
                }
                controller.airPlayChapters = chapters;
                [controller updateChapterMarkers:[controller durationMilliseconds]];
            });
        }];
    }
}

- (void)removeAirPlayItemObservers {
    AVPlayerItem *item = self.airPlayPlayer.currentItem;
    if (!item) return;
    self.airPlaySeekGeneration++;
    [NSNotificationCenter.defaultCenter removeObserver:self name:AVPlayerItemDidPlayToEndTimeNotification object:item];
    [NSNotificationCenter.defaultCenter removeObserver:self name:AVPlayerItemFailedToPlayToEndTimeNotification object:item];
    [item cancelPendingSeeks];
}

- (void)startAirPlayPlayback {
    if (self.controlsLocked || ![self allowsAirPlay] || ![self canPlay:NO] ||
        !self.requestPlay || !self.requestPlay() || ![self canPlay:NO]) return;
    self.playRequested = YES;
    if (![self protectedDataAvailable]) self.airPlayLockPlaybackIntent = YES;
    self.airPlaySystemPaused = NO;
    self.airPlayLastProgress = NSProcessInfo.processInfo.systemUptime;
    if (!self.airPlayAdvanced) self.airPlayStartDeadline = self.airPlayLastProgress + 45;
    if (self.ended) [self seekAirPlay:0];
    // Starting playback initiates the receiver handoff. Waiting for the resume
    // seek first can deadlock that handoff on large HLS inputs. Pending seeks
    // keep output muted until AVKit has positioned the receiver.
    [self playAirPlayAtRequestedRate];
    [self updatePlayButton];
}

- (void)seekAirPlay:(int64_t)target {
    [self seekAirPlay:target chapter:NO];
}

- (void)seekAirPlay:(int64_t)target chapter:(BOOL)chapter {
    if (self.controlsLocked || ![self allowsAirPlay] || ![self canPlay:NO]) return;
    int64_t duration = [self durationMilliseconds];
    self.airPlaySeekTarget = duration > 0 ? MIN(MAX(0, target), duration - 1) : MAX(0, target);
    self.airPlayChapterSeek = chapter;
    if (!self.airPlayWasExternal) self.airPlayStartPosition = self.airPlaySeekTarget;
    self.ended = NO;
    self.airPlaySeekDeadline = NSProcessInfo.processInfo.systemUptime + 20;
    if (self.airPlayPlayer.currentItem.status == AVPlayerItemStatusReadyToPlay) {
        [self submitAirPlaySeek];
    } else if (self.airPlaySeekPending) {
        self.airPlaySeekGeneration++;
        self.airPlaySeekPending = NO;
        [self.airPlayPlayer.currentItem cancelPendingSeeks];
    }
}

- (void)submitAirPlaySeek {
    int64_t target = self.airPlaySeekTarget;
    self.airPlaySeekPending = YES;
    if (self.airPlaySeekDeadline <= 0) self.airPlaySeekDeadline = NSProcessInfo.processInfo.systemUptime + 20;
    NSUInteger generation = ++self.airPlaySeekGeneration;
    __weak LGVideoController *owner = self;
    CMTime toleranceBefore = self.airPlayChapterSeek ? kCMTimeZero : CMTimeMake(250, 1000);
    [self.airPlayPlayer seekToTime:CMTimeMake(target, 1000) toleranceBefore:toleranceBefore
        toleranceAfter:CMTimeMake(250, 1000) completionHandler:^(BOOL finished) {
        dispatch_async(dispatch_get_main_queue(), ^{
            if (!owner.airPlayPlayer || owner.airPlaySeekGeneration != generation) return;
            owner.airPlaySeekPending = NO;
            owner.airPlaySeekDeadline = 0;
            owner.airPlaySeekTarget = -1;
            // AVKit/receiver controls pause AVPlayer directly. A seek can finish
            // before the next timeline tick observes that pause; never replay it
            // from stale phone-side intent (including an interrupted seek).
            if (owner.airPlayPlayer.timeControlStatus == AVPlayerTimeControlStatusPaused &&
                !owner.airPlaySystemPaused)
                owner.playRequested = NO;
            if (!finished && owner.playRequested && owner.airPlayPlayer.externalPlaybackActive &&
                !owner.airPlayAdvanced && target == owner.airPlayStartPosition) {
                owner.airPlaySeekTarget = target;
                owner.airPlaySeekDeadline = NSProcessInfo.processInfo.systemUptime;
                [owner recoverAirPlay:@"initial-seek-failed"];
                return;
            }
            int64_t current = [owner airPlayTime:owner.airPlayPlayer.currentTime];
            if (finished && current >= 0) owner.airPlayConfirmedPosition = current;
            owner.airPlayClock = current;
            owner.airPlayLastProgress = NSProcessInfo.processInfo.systemUptime;
            if (finished && owner.airPlayStartDeadline > 0)
                owner.airPlayStartDeadline = MAX(owner.airPlayStartDeadline, owner.airPlayLastProgress + 15);
            if (!finished) [owner showStatus:@"The TV couldn’t seek to that position. Try the timeline again."];
            if (owner.playRequested && !owner.airPlaySystemPaused && [owner allowsAirPlay] && [owner canPlay:NO])
                [owner playAirPlayAtRequestedRate];
            [owner updatePlayButton];
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
                NSUInteger number = 0;
                for (AVMediaSelectionOption *option in playable) {
                    number++;
                    NSString *label = option.displayName;
                    // MKV rendition names already include compact codec/channel
                    // details. Other AVKit assets expose language and subtype.
                    if (!text && [label rangeOfString:@"^#[0-9]+ · " options:NSRegularExpressionSearch].location == NSNotFound) {
                        NSString *code = option.extendedLanguageTag ?: option.locale.languageCode ?: @"";
                        NSString *language = code.length && ![code isEqualToString:@"und"] ?
                            ([NSLocale.currentLocale localizedStringForLanguageCode:code] ?: code) : @"";
                        uint32_t subtype = [option.mediaSubTypes.firstObject unsignedIntValue];
                        char fourcc[] = {(char)(subtype >> 24), (char)(subtype >> 16), (char)(subtype >> 8), (char)subtype, 0};
                        NSString *codec = subtype ? [NSString stringWithUTF8String:fourcc] : @"";
                        label = LGVideoAudioLabel(number, @[language, label ?: @""], codec, 0, 0);
                    }
                    if ([option isEqual:selected]) label = [@"✓ " stringByAppendingString:label];
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

- (void)traceAirPlay:(NSString *)event {
    AVPlayer *player = self.airPlayPlayer;
    if (!player) return;
    AVPlayerItem *item = player.currentItem;
    UIWindowScene *scene = self.viewIfLoaded.window.windowScene;
    NSTimeInterval now = NSProcessInfo.processInfo.systemUptime;
    NSString *state = [NSString stringWithFormat:
        @"control=%ld waiting=%@ item=%ld external=%d audioRoute=%d empty=%d likely=%d seeking=%d requested=%d app=%ld scene=%ld protectedData=%d",
        (long)player.timeControlStatus, player.reasonForWaitingToPlay ?: @"none", (long)item.status,
        player.externalPlaybackActive, [self hasAirPlayAudioRoute], item.playbackBufferEmpty,
        item.playbackLikelyToKeepUp, self.airPlaySeekTarget >= 0, self.playRequested,
        (long)UIApplication.sharedApplication.applicationState, scene ? (long)scene.activationState : -1L,
        [self protectedDataAvailable]];
    if (!event && [self.airPlayTraceState isEqualToString:state] && now - self.airPlayLastTrace < 30) return;
    self.airPlayTraceState = state;
    self.airPlayLastTrace = now;
    // These diagnostics contain playback state without media or receiver identifiers.
    os_log(OS_LOG_DEFAULT, "[VideoAirPlay] %{public}@ uptime=%.1f clock=%lld confirmed=%lld lastAdvanceAge=%.1f %{public}@",
        event ?: @"sample", now, [self airPlayTime:player.currentTime], self.airPlayConfirmedPosition,
        now - self.airPlayLastProgress, state);
    if (self.airPlaySourceTrace) self.airPlaySourceTrace();
}

- (void)logAirPlaySource:(NSString *)diagnostics {
    os_log(OS_LOG_DEFAULT, "[VideoAirPlay] HLS %{public}@", diagnostics);
}

- (void)airPlayRateChanged:(NSNotification *)note {
    AVPlayer *player = note.object;
    AVPlayerItem *item = player.currentItem;
    NSString *reason = note.userInfo[AVPlayerRateDidChangeReasonKey];
    dispatch_async(dispatch_get_main_queue(), ^{
        if (player != self.airPlayPlayer || item != player.currentItem) return;
        if ([reason isEqualToString:AVPlayerRateDidChangeReasonAppBackgrounded] ||
            [reason isEqualToString:AVPlayerRateDidChangeReasonSetRateFailed]) {
            self.airPlaySystemPaused = self.playRequested;
        } else if ([reason isEqualToString:AVPlayerRateDidChangeReasonSetRateCalled]) {
            self.airPlaySystemPaused = NO;
            if (player.externalPlaybackActive && player.timeControlStatus == AVPlayerTimeControlStatusPaused) {
                self.airPlaySawTransport = YES; // An explicit rate change can pause before the first frame.
                self.airPlayLockPlaybackIntent = NO;
            }
        }
        [self traceAirPlay:[@"rate-change " stringByAppendingString:reason ?: @"unspecified"]];
    });
}

- (void)airPlayEnded:(NSNotification *)note {
    dispatch_async(dispatch_get_main_queue(), ^{
        AVPlayerItem *item = self.airPlayPlayer.currentItem;
        if (note.object != item || self.airPlayItemFailed || item.status == AVPlayerItemStatusFailed) return;
        self.ended = YES;
        self.playRequested = NO;
        self.airPlayStartDeadline = 0;
        [self traceAirPlay:@"ended"];
        [self emitCommand:@"ended" value:@""];
    });
}

- (void)airPlayFailed:(NSNotification *)note {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (note.object != self.airPlayPlayer.currentItem) return;
        NSError *error = note.userInfo[AVPlayerItemFailedToPlayToEndTimeErrorKey];
        NSError *underlying = error.userInfo[NSUnderlyingErrorKey];
        NSLog(@"[VideoAirPlay] playback failed domain=%@ code=%ld underlying=%@/%ld",
            error.domain, (long)error.code, underlying.domain, (long)underlying.code);
        // AVKit can follow this failure with an end event while the item remains
        // ready. Keep the confirmed position and play intent until wake.
        self.airPlayItemFailed = YES;
        self.airPlaySeekGeneration++;
        if (![self protectedDataAvailable] && self.airPlayLockPlaybackIntent && !self.ended)
            self.playRequested = YES;
        [self recoverAirPlay:@"item-failed"];
    });
}

- (void)updateAirPlay {
    AVPlayer *player = self.airPlayPlayer;
    if (![self allowsAirPlay]) {
        [self stopAirPlayForAccessChange];
        return;
    }
    if (![self canPlay:NO]) {
        if (self.playRequested) [self pause];
        return;
    }
    if (self.airPlayItemFailed) {
        [self recoverAirPlay:@"item-failed"];
        return;
    }

    NSTimeInterval now = NSProcessInfo.processInfo.systemUptime;
    if (self.airPlayAdvanced && self.airPlayLastPoll > 0 && now - self.airPlayLastPoll > 3) {
        // AVKit may need a fresh sample after this process was suspended.
        self.airPlayStallGraceUntil = now + 5;
        self.airPlayRouteLossDeadline = 0;
    }
    self.airPlayLastPoll = now;
    BOOL external = player.externalPlaybackActive;
    BOOL audioRoute = [self hasAirPlayAudioRoute];
    [self traceAirPlay:nil];
    if (!external) {
        player.muted = YES;
        if (self.airPlayWasExternal && !audioRoute &&
            (self.airPlayPickerOpen || self.airPlayRouteDeadline > now)) {
            [self finishAirPlayWithMessage:nil]; // User switched to this device in the picker.
            return;
        }
        if (self.airPlayWasExternal || !audioRoute) {
            if (self.airPlayRouteLossDeadline <= 0) self.airPlayRouteLossDeadline = now + 3;
            if (now >= self.airPlayRouteLossDeadline) [self recoverAirPlay:@"route-lost"];
            return;
        }
    }
    self.airPlayRouteLossDeadline = 0;
    if (player.status == AVPlayerStatusFailed || player.currentItem.status == AVPlayerItemStatusFailed) {
        NSError *error = player.currentItem.error ?: player.error;
        NSLog(@"[VideoAirPlay] failed domain=%@ code=%ld", error.domain, (long)error.code);
        [self recoverAirPlay:@"player-or-item-failed"];
        return;
    }

    BOOL itemReady = player.currentItem.status == AVPlayerItemStatusReadyToPlay;
    BOOL ready = external && itemReady;
    if (ready && !self.airPlayWasExternal) {
        self.airPlayWasExternal = YES;
        [self applyAirPlayPlaybackOptions];
        if (self.airPlaySeekTarget < 0 &&
            llabs([self airPlayTime:player.currentTime] - self.airPlayStartPosition) > 250)
            [self seekAirPlay:self.airPlayStartPosition];
    }
    if (ready && !self.ended) {
        if (player.timeControlStatus == AVPlayerTimeControlStatusPaused) {
            if (!self.airPlaySystemPaused && self.airPlaySawTransport) {
                self.playRequested = NO;
                self.airPlayStartDeadline = 0;
            }
        } else {
            self.airPlaySawTransport = YES;
            self.airPlaySystemPaused = NO;
            if (!self.playRequested) {
                self.airPlayLastProgress = now;
                if (!self.airPlayAdvanced) self.airPlayStartDeadline = now + 45;
            }
            self.playRequested = YES;
        }
    } else if (ready && self.ended && player.timeControlStatus == AVPlayerTimeControlStatusPlaying &&
               [self airPlayTime:player.currentTime] < self.airPlayConfirmedPosition) {
        self.ended = NO; // Replay from the receiver's transport.
        self.playRequested = YES;
        self.airPlayLastProgress = now;
    }
    if (self.airPlaySeekDeadline > 0 && now >= self.airPlaySeekDeadline) {
        [self recoverAirPlay:@"seek-timeout"];
        return;
    }
    if (self.airPlaySeekTarget >= 0 && !self.airPlaySeekPending && itemReady) [self submitAirPlaySeek];

    if (ready && self.airPlaySeekTarget < 0 && self.playRequested &&
        player.timeControlStatus == AVPlayerTimeControlStatusPlaying) {
        int64_t current = [self airPlayTime:player.currentTime];
        if (current >= 0 && current > self.airPlayClock && self.airPlayClock >= 0) {
            if (!self.airPlayAdvanced) {
                self.airPlayPicker.accessibilityValue = @"Playing on TV";
                [self showStatus:@""];
            }
            self.airPlayAdvanced = YES;
            self.airPlayStartDeadline = 0;
            self.airPlayLastProgress = now;
            self.airPlayConfirmedPosition = current;
            if (![self protectedDataAvailable]) self.airPlayLockPlaybackIntent = YES;
        }
        if (current >= 0) self.airPlayClock = current;
    }
    if (self.playRequested && !self.ended && self.airPlaySeekTarget < 0 &&
        ((self.airPlayStartDeadline > 0 && now >= self.airPlayStartDeadline) ||
         (self.airPlayAdvanced && now - self.airPlayLastProgress >= 15 && now >= self.airPlayStallGraceUntil))) {
        [self recoverAirPlay:self.airPlayAdvanced ? @"playhead-stalled" : @"start-timeout"];
        return;
    }
    player.muted = !ready || self.airPlaySeekTarget >= 0 || self.resumeMuted;
    [self updatePlayButton];
}

- (void)stopAirPlayForAccessChange {
    [self traceAirPlay:@"access-revoked"];
    if (self.restricted) {
        [self suspendForLock];
    } else {
        [self detachAirPlay];
        [self revealSurface];
        [self showStatus:@"AirPlay access changed. Press Play to continue on this device."];
    }
}

- (void)recoverAirPlay:(NSString *)reason {
    if (![self allowsAirPlay]) {
        [self stopAirPlayForAccessChange];
        return;
    }
    // The OS can suspend the app. Keep the established item through a lock and
    // evaluate a new handoff when the app can present controls again.
    if ([self hasEstablishedAirPlay] && (self.airPlayItemFailed || self.airPlayPlayer.externalPlaybackActive || [self hasAirPlayAudioRoute]) &&
        (![self protectedDataAvailable] || UIApplication.sharedApplication.applicationState != UIApplicationStateActive)) return;

    [self traceAirPlay:reason];
    AVPlayer *player = self.airPlayPlayer;
    AVPlayerItem *item = player.currentItem;
    AVURLAsset *asset = [item.asset isKindOfClass:AVURLAsset.class] ? (AVURLAsset *)item.asset : nil;
    if (!self.airPlayRecovered && self.playRequested && !self.ended && !self.airPlayPickerOpen &&
        [self protectedDataAvailable] && UIApplication.sharedApplication.applicationState == UIApplicationStateActive &&
        [self canPlay:NO] && (player.externalPlaybackActive || [self hasAirPlayAudioRoute]) &&
        player.status != AVPlayerStatusFailed && asset.URL) {
        self.airPlayRecovered = YES;
        int64_t position = self.airPlayConfirmedPosition;
        [self removeAirPlayItemObservers];
        self.playRequested = NO;
        player.muted = YES;
        [player pause];
        // Keep the selected route and the authorized source alive for one
        // fresh item. An explicit retry after teardown also rebuilds the source.
        [self installAirPlayItemAtURL:asset.URL metadata:item.externalMetadata position:position];
        self.airPlayPicker.accessibilityValue = @"Connecting";
        [self showStatus:@"Reconnecting to TV…"];
        [self startAirPlayPlayback];
        if (self.playRequested) return;
    }
    [self finishAirPlayWithMessage:@"AirPlay stopped. Select the TV in AirPlay to retry."];
}

- (void)finishAirPlayWithMessage:(NSString *)message {
    BOOL resume = !message && (self.airPlayWasExternal ? self.playRequested : self.airPlayResumeLocal);
    [self detachAirPlay];
    self.airPlayResumeLocal = resume;
    [self revealSurface];
    if ([self hasAirPlayAudioRoute]) {
        NSString *choose = @"Choose this device in AirPlay to play here.";
        [self showStatus:message.length ? [NSString stringWithFormat:@"%@ %@", message, choose] : choose];
    } else {
        [self updateAirPlayRoute];
        if (message.length)
            [self showStatus:[message stringByAppendingString:@" Press Play to continue on this device."]];
    }
}

- (void)detachAirPlay {
    self.airPlayPreparing = NO;
    self.airPlayRouteDeadline = 0;
    self.airPlayResumeLocal = NO;
    AVPlayer *player = self.airPlayPlayer;
    if (!player) return;
    self.startMilliseconds = self.ended ? 0 : self.airPlayConfirmedPosition;
    self.lastPosition = self.startMilliseconds;
    [self removeAirPlayItemObservers];
    self.airPlaySeekPending = NO;
    self.airPlayItemFailed = self.airPlayLockPlaybackIntent = NO;
    self.airPlaySeekTarget = -1;
    self.airPlaySeekDeadline = self.airPlayStartDeadline = self.airPlayRouteLossDeadline = 0;
    [NSNotificationCenter.defaultCenter removeObserver:self name:AVPlayerRateDidChangeNotification object:player];
    player.muted = YES;
    [player pause];
    self.airPlayController.player = nil;
    [self.airPlayController willMoveToParentViewController:nil];
    [self.airPlayController.view removeFromSuperview];
    [self.airPlayController removeFromParentViewController];
    self.airPlayController = nil;
    player.allowsExternalPlayback = NO;
    [player replaceCurrentItemWithPlayerItem:nil];
    self.airPlayPlayer = nil;
    self.airPlayChapters = nil;
    self.airPlayPicker.accessibilityValue = nil;
    self.localAudioNeedsRefresh = YES;
    self.playRequested = NO;
    if (!self.retired) {
        [self showStatus:@""];
        [self emitCommand:@"airplayDetached" value:@""];
    }
}
@end
