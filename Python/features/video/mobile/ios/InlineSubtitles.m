// The pinned sample-buffer output draws VLC's subpictures in a transparent
// view next to the video layer. The OpenGL fallback blends them into the video.
static UIView *LGSubtitleSurface(UIView *container) {
    Class subtitleClass = NSClassFromString(@"VLCSampleBufferSubpictureView");
    if (!subtitleClass) return nil;
    for (UIView *child in container.subviews) {
        if ([child isKindOfClass:subtitleClass]) return child;
        UIView *nested = LGSubtitleSurface(child);
        if (nested) return nested;
    }
    return nil;
}

static BOOL LGHasPlainTextSubtitle(VLCMediaPlayer *player) {
    BOOL found = NO;
    for (VLCMediaPlayerTrack *track in player.textTracks) {
        if (!track.isSelected) continue;
        // VLC_CODEC_SUBT and VLC_CODEC_TX3G, represented as VLC's little-endian FourCC.
        if (track.codec != 0x74627573 && track.codec != 0x67337874) return NO;
        found = YES;
    }
    return found;
}

static CGRect LGRenderedSubtitleBounds(UIView *surface) {
    CGRect bounds = surface.bounds;
    size_t width = (size_t)ceil(CGRectGetWidth(bounds));
    size_t height = (size_t)ceil(CGRectGetHeight(bounds));
    CGContextRef alpha = CGBitmapContextCreate(NULL, width, height, 8, 0, NULL,
                                               (CGBitmapInfo)kCGImageAlphaOnly);
    if (!alpha) return CGRectNull;
    CGContextTranslateCTM(alpha, -bounds.origin.x, height + bounds.origin.y);
    CGContextScaleCTM(alpha, 1, -1);
    [surface.layer displayIfNeeded];
    [surface.layer renderInContext:alpha];

    const uint8_t *pixels = CGBitmapContextGetData(alpha);
    size_t stride = CGBitmapContextGetBytesPerRow(alpha);
    size_t left = width, top = height, right = 0, bottom = 0;
    for (size_t y = 0; y < height; y++) {
        const uint8_t *row = pixels + y * stride;
        for (size_t x = 0; x < width; x++) {
            if (!row[x]) continue;
            left = MIN(left, x);
            top = MIN(top, y);
            right = MAX(right, x + 1);
            bottom = y + 1;
        }
    }
    CGContextRelease(alpha);
    if (right == 0) return CGRectNull;
    return CGRectMake(bounds.origin.x + left, bounds.origin.y + top, right - left, bottom - top);
}

@implementation LGVideoController (InlineSubtitles)

- (CGRect)naturalSubtitleFrame:(UIView *)surface relativeTo:(UIView *)parent {
    CGRect frame = [surface convertRect:surface.bounds toView:parent];
    if (surface == self.shiftedSubtitleView) frame.origin.y += self.subtitleClearance;
    return frame;
}

- (void)setSubtitleClearance:(CGFloat)clearance forSurface:(UIView *)surface {
    UIView *previous = self.shiftedSubtitleView;
    if (previous == surface && self.subtitleClearance == clearance) return;
    [UIView performWithoutAnimation:^{
        if (previous != surface || clearance == 0) previous.transform = CGAffineTransformIdentity;
        if (clearance > 0) surface.transform = CGAffineTransformMakeTranslation(0, -clearance);
    }];
    self.shiftedSubtitleView = clearance > 0 ? surface : nil;
    self.subtitleClearance = clearance;
}

- (void)resetInlineSubtitles {
    [self.subtitleLayoutLink invalidate];
    self.subtitleLayoutLink = nil;
    [self setSubtitleClearance:0 forSurface:nil];
}

- (void)subtitleLayoutDidRefresh:(CADisplayLink *)link {
    [self updateInlineSubtitles];
}

- (void)updateInlineSubtitles {
    if (!self.surfaceVisible || self.retired || self.lockHidden || self.pipActive ||
        self.externalVideoHost || self.casting || self.movie.hidden || self.controlsScroll.hidden) {
        [self resetInlineSubtitles];
        return;
    }
    CGRect deck = [self.controlsScroll convertRect:self.controlsScroll.bounds toView:self.view];
    CGRect picture = [self.movie convertRect:self.movie.bounds toView:self.view];
    if (!CGRectIntersectsRect(picture, deck)) {
        [self resetInlineSubtitles];
        return;
    }
    // A new cue can arrive without any UIKit layout, and a paused cue keeps
    // its existing pixels. Track the plane only while the deck covers video.
    if (!self.subtitleLayoutLink) {
        self.subtitleLayoutLink = [CADisplayLink displayLinkWithTarget:self selector:@selector(subtitleLayoutDidRefresh:)];
        self.subtitleLayoutLink.preferredFramesPerSecond = 30;
        [self.subtitleLayoutLink addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
    }
    UIView *surface = LGSubtitleSurface(self.movie);
    CGFloat clearance = 0;
    if (surface && !surface.hidden && !CGRectIsEmpty(surface.bounds) && LGHasPlainTextSubtitle(self.player)) {
        CGRect cue = LGRenderedSubtitleBounds(surface);
        if (!CGRectIsNull(cue)) {
            cue = [surface convertRect:cue toView:self.view];
            if (surface == self.shiftedSubtitleView) cue.origin.y += self.subtitleClearance;
            if (CGRectIntersectsRect(cue, deck)) {
                CGFloat offset = ceil(CGRectGetMaxY(cue) - CGRectGetMinY(deck));
                if (CGRectGetMinY(cue) - offset >= CGRectGetMinY(picture)) clearance = offset;
            }
        }
    }
    [self setSubtitleClearance:clearance forSurface:surface];
}

@end
