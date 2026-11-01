// On-demand diagnostics only: never copy pixels on the playback timer.
@implementation LGVideoController (HDRDiagnostics)
- (AVSampleBufferDisplayLayer *)sampleBufferLayer:(CALayer *)layer {
    if ([layer isKindOfClass:AVSampleBufferDisplayLayer.class]) return (id)layer;
    for (CALayer *child in layer.sublayers) {
        AVSampleBufferDisplayLayer *found = [self sampleBufferLayer:child];
        if (found) return found;
    }
    return nil;
}
- (NSDictionary *)hdrPresentationState {
    AVSampleBufferDisplayLayer *layer = [self sampleBufferLayer:self.movie.layer];
    NSMutableDictionary *state = [@{
        @"uptime": @(NSProcessInfo.processInfo.systemUptime),
        @"clock": self.player.time.value ?: @(-1),
        @"state": @((NSInteger)self.player.state),
        @"requestedMode": self.forceMaximumHDR ? @"high" : @"automatic",
        @"snapshotOverlay": @(self.pauseSnapshot != nil),
        @"sampleBufferLayer": layer ? [NSString stringWithFormat:@"%p", layer] : @"absent",
        @"libvlcVersion": self.player.libraryInstance.version ?: @"unknown",
        @"libvlcChangeset": self.player.libraryInstance.changeset ?: @"unknown"
    } mutableCopy];
    NSMutableArray *tracks = [NSMutableArray array];
    for (VLCMediaPlayerTrack *track in self.player.videoTracks) {
        if (track.isSelected) [tracks addObject:@{@"codec": track.codecName ?: @"unknown",
            @"codecIdentifier": @(track.codec), @"profile": @(track.profile), @"level": @(track.level)}];
    }
    state[@"selectedVideoTracks"] = tracks;
    if (@available(iOS 16.0, *)) {
        UIScreen *screen = self.view.window.screen;
        state[@"currentEDRHeadroom"] = @(screen.currentEDRHeadroom);
        state[@"potentialEDRHeadroom"] = @(screen.potentialEDRHeadroom);
    }
    if (layer) {
        state[@"status"] = @(layer.status);
        if (@available(iOS 26.0, *)) state[@"dynamicRange"] = layer.preferredDynamicRange;
        else if (@available(iOS 17.0, *)) state[@"extendedRange"] = @(layer.wantsExtendedDynamicRangeContent);
        if (@available(iOS 17.4, *)) {
            state[@"ready"] = @(layer.readyForDisplay);
            CVPixelBufferRef pixels = [layer.sampleBufferRenderer copyDisplayedPixelBuffer];
            if (pixels) {
                OSType format = CVPixelBufferGetPixelFormatType(pixels);
                state[@"pixelFormat"] = [NSString stringWithFormat:@"%c%c%c%c", (int)(format >> 24),
                    (int)((format >> 16) & 255), (int)((format >> 8) & 255), (int)(format & 255)];
                // Allowlisted color metadata only; never log media URLs or image bytes.
                NSMutableDictionary *attachments = [NSMutableDictionary dictionary];
                for (NSString *key in @[(__bridge NSString *)kCVImageBufferColorPrimariesKey,
                     (__bridge NSString *)kCVImageBufferTransferFunctionKey,
                     (__bridge NSString *)kCVImageBufferYCbCrMatrixKey,
                     (__bridge NSString *)kCVImageBufferMasteringDisplayColorVolumeKey,
                     (__bridge NSString *)kCVImageBufferContentLightLevelInfoKey,
                     (__bridge NSString *)kCVImageBufferAmbientViewingEnvironmentKey]) {
                    CFTypeRef value = CVBufferCopyAttachment(pixels, (__bridge CFStringRef)key, NULL);
                    if (value) { attachments[key] = [(__bridge id)value description]; CFRelease(value); }
                }
                state[@"pixelAttachments"] = attachments;
                CVPixelBufferRelease(pixels);
            }
        }
    }
    return state;
}
- (void)logHDRTransition:(NSString *)event {
    if (![NSProcessInfo.processInfo.environment[@"LOGISTICS_VIDEO_HDR_DIAGNOSTICS"] boolValue] &&
        ![[NSBundle.mainBundle objectForInfoDictionaryKey:@"LGVideoHDRDiagnostics"] boolValue]) return;
    NSLog(@"[VideoHDR] event=%@ presentation=%@", event, [self hdrPresentationState]);
}
@end
