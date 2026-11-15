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
    track.selectedExclusively = YES;
    if (!self.hasPlayed) return YES; // Initial discovery is already prerolling.
    self.audioSwitchTrack = track.trackId;
    self.audioSwitchPlayed = self.player.media.statistics.playedAudioBuffers;
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
    self.audioSwitchTrack = nil;
    self.audioSwitchSawBuffering = self.audioSwitchBuffered = NO;
    self.audioSwitchDeadline = 0;
    self.bufferLabel.hidden = YES;
}
- (void)updateAudioSwitch {
    if (!self.audioSwitchTrack.length || self.retired) return;
    BOOL selected = NO;
    for (VLCMediaPlayerTrack *track in self.player.audioTracks)
        if ([track.trackId isEqual:self.audioSwitchTrack] && track.isSelected) selected = YES;
    // Selection alone only acknowledges a command. Require the post-seek
    // buffering cycle AND newly played audio, including silent audio samples.
    // Cast decodes at the receiver, so local audio counters cannot attest to
    // its speaker. Use post-preroll sender clock progress for that existing path.
    BOOL outputReady = self.casting ? self.player.time.value.longLongValue > self.audioSwitchClock :
        self.player.media.statistics.playedAudioBuffers > self.audioSwitchPlayed;
    if (selected && self.audioSwitchBuffered && outputReady) {
        [self cancelAudioSwitch];
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
