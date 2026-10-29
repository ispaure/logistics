// Hold the visible frame and clock immediately while VLC acknowledges Pause.
// The render-server snapshot is volatile and is discarded on privacy/lifetime edges.
@implementation LGVideoController (PausePresentation)
- (void)holdPausePresentation {
    if (self.pauseSnapshot || !self.player.isPlaying || !self.surfaceVisible ||
        self.lockHidden || self.movie.hidden || self.pipActive || self.casting ||
        UIApplication.sharedApplication.applicationState != UIApplicationStateActive || ![self canPlay:NO]) return;
    self.startMilliseconds = [self positionMilliseconds];
    self.lastPosition = self.startMilliseconds;
    UIView *snapshot = [self.movie snapshotViewAfterScreenUpdates:NO];
    if (!snapshot) return;
    snapshot.userInteractionEnabled = NO;
    snapshot.isAccessibilityElement = NO;
    snapshot.frame = self.movie.frame;
    snapshot.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    [self.view insertSubview:snapshot aboveSubview:self.movie];
    self.pauseSnapshot = snapshot;
}
- (void)clearPausePresentation {
    [self.pauseSnapshot removeFromSuperview]; self.pauseSnapshot = nil;
}
@end
