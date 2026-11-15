// A newly selected decoder starts at the demuxer's read-ahead position. Seeking
// back to the displayed time flushes those queues and lets VLC preroll audio and
// video together, rather than playing several seconds of silent queued video.
@implementation LGVideoController (AudioSwitch)
- (BOOL)switchAudioTrack:(VLCMediaPlayerTrack *)track {
    if (self.retired || ![self canPlay:NO] || [self hasAirPlay]) return NO;
    if ([self.audioSwitchTrack isEqual:track.trackId] || (track.isSelected && !self.audioSwitchTrack.length)) return YES;
    if (self.hasPlayed && !self.player.isSeekable) {
        [self showStatus:@"Audio switching is unavailable until this video can seek."];
        return NO;
    }
    int64_t position = [self positionMilliseconds];
    [self cancelAudioSwitch];
    self.audioSwitchDecoded = [self playbackStats].decodedAudio;
    self.audioSwitchFrames = [self playbackStats].displayedPictures;
    track.selectedExclusively = YES;
    if (!self.hasPlayed) return YES; // Initial discovery is already prerolling.
    self.audioSwitchTrack = track.trackId;
    self.audioSwitchPlayed = [self playbackStats].playedAudioBuffers;
    self.audioSwitchDeadline = NSProcessInfo.processInfo.systemUptime + 20;
    // Do not pause the decoder: seek preroll owns the shared output clock. A
    // paused input remains paused; choosing a language never grants autoplay.
    self.player.time = [VLCTime timeWithNumber:@(MAX(0, position))];
    [self updatePlaybackProgress];
    [self setControlsShown:YES];
    return YES;
}
- (void)cancelAudioSwitch {
    self.audioSwitchGeneration++;
    self.audioOutputMissing = NO;
    if ([self.message.text isEqualToString:@"Audio has not started here. Video continues."]) [self showStatus:@""];
    self.audioSwitchTrack = nil;
    self.audioSwitchSawBuffering = self.audioSwitchBuffered = NO;
    self.audioSwitchDeadline = 0;
    self.bufferLabel.hidden = YES;
}
- (void)updateAudioSwitch {
    if (self.retired) return;
    if (self.audioOutputMissing && [self playbackStats].playedAudioBuffers > self.audioMissingPlayed) {
        self.audioOutputMissing = NO;
        if ([self.message.text isEqualToString:@"Audio has not started here. Video continues."]) [self showStatus:@""];
    }
    if (!self.audioSwitchTrack.length) return;
    BOOL selected = NO;
    for (VLCMediaPlayerTrack *track in self.player.audioTracks)
        if ([track.trackId isEqual:self.audioSwitchTrack] && track.isSelected) selected = YES;
    // Selection alone only acknowledges a command. Require the post-seek
    // buffering cycle AND newly played audio, including silent audio samples.
    // Cast decodes at the receiver, so local audio counters cannot attest to
    // its speaker. Use post-preroll sender clock progress for that existing path.
    BOOL outputReady = self.casting ? [self nativeTimeMilliseconds] > self.audioSwitchClock :
        [self playbackStats].playedAudioBuffers > self.audioSwitchPlayed;
    if (selected && self.audioSwitchBuffered && outputReady) {
        [self cancelAudioSwitch];
        return;
    }
    VLCMediaStats stats = [self playbackStats];
    if (stats.decodedAudio != self.audioSwitchDecoded) {
        self.audioSwitchDecoded = stats.decodedAudio;
        self.audioSwitchDecodeClock = [self nativeTimeMilliseconds];
    }
    // An ended/empty audio track cannot produce a new audio buffer. Native
    // video output and its advancing clock prove that the shared preroll has
    // completed, but do not prove audio is audible or permanently exhausted.
    // Report that distinct outcome instead of blocking otherwise valid video.
    if (selected && self.audioSwitchBuffered && self.playRequested && !self.networkWaiting &&
        !self.transportFailure && stats.displayedPictures > self.audioSwitchFrames &&
        [self nativeTimeMilliseconds] - MAX(self.audioSwitchClock, self.audioSwitchDecodeClock) >= 1250) {
        [self cancelAudioSwitch];
        self.audioOutputMissing = YES;
        self.audioMissingPlayed = stats.playedAudioBuffers;
        [self showStatus:@"Audio has not started here. Video continues."];
        return;
    }
    if (!self.playRequested) {
        self.audioSwitchDeadline = NSProcessInfo.processInfo.systemUptime + 20;
        return;
    }
    if (NSProcessInfo.processInfo.systemUptime >= self.audioSwitchDeadline) {
        [self pause];
        [self showStatus:@"Audio did not become ready. Choose another track or press Play to retry."];
    }
}
@end
