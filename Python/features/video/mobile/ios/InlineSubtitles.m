// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

#import <CoreImage/CoreImage.h>
#import <objc/runtime.h>

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

static CGFloat LGCaptionGain(NSString *level, BOOL brightAvailable) {
    if ([level isEqualToString:@"dim"]) return .60;
    return brightAvailable && [level isEqualToString:@"bright"] ? 1.25 : 1;
}

static CIImage *LGScaleCaptionRGB(CIImage *caption, CGFloat gain) {
    if (gain == 1) return caption;
    // Core Image works in extended linear RGB. Keep the original alpha.
    return [caption imageByApplyingFilter:@"CIColorMatrix" withInputParameters:@{
        @"inputRVector": [CIVector vectorWithX:gain Y:0 Z:0 W:0],
        @"inputGVector": [CIVector vectorWithX:0 Y:gain Z:0 W:0],
        @"inputBVector": [CIVector vectorWithX:0 Y:0 Z:gain W:0],
    }];
}

@interface LGInlineCaptionLayer : CALayer
@property(nonatomic) CGFloat gain;
@end
@implementation LGInlineCaptionLayer
@end

static char LGInlineCaptionLayerKey;
static void (*LGDrawVLCSubtitle)(UIView *, SEL, CGRect);

static BOOL LGDrawOriginalSubtitle(UIView *view, CGContextRef context) {
    if (!objc_getAssociatedObject(view, &LGInlineCaptionLayerKey)) return NO;
    UIGraphicsPushContext(context);
    LGDrawVLCSubtitle(view, @selector(drawRect:), view.bounds);
    UIGraphicsPopContext();
    return YES;
}

static void LGDrawInlineSubtitle(UIView *view, SEL selector, CGRect dirtyRect) {
    LGInlineCaptionLayer *layer = objc_getAssociatedObject(view, &LGInlineCaptionLayerKey);
    if (!layer || CGRectIsEmpty(view.bounds)) {
        LGDrawVLCSubtitle(view, selector, dirtyRect);
        return;
    }
    static CIContext *context;
    if (!context) context = [CIContext contextWithOptions:@{kCIContextCacheIntermediates: @NO}];
    UIGraphicsImageRendererFormat *format = [UIGraphicsImageRendererFormat defaultFormat];
    format.scale = view.contentScaleFactor;
    format.preferredRange = UIGraphicsImageRendererFormatRangeStandard;
    UIGraphicsImageRenderer *renderer = [[UIGraphicsImageRenderer alloc] initWithBounds:view.bounds format:format];
    UIImage *native = [renderer imageWithActions:^(UIGraphicsImageRendererContext *drawing) {
        LGDrawOriginalSubtitle(view, drawing.CGContext);
    }];
    CIImage *caption = LGScaleCaptionRGB([CIImage imageWithCGImage:native.CGImage], layer.gain);
    BOOL bright = layer.gain > 1;
    CGColorSpaceRef colorSpace = CGColorSpaceCreateWithName(bright ? kCGColorSpaceExtendedLinearSRGB : kCGColorSpaceSRGB);
    CGImageRef image = [context createCGImage:caption fromRect:caption.extent
        format:bright ? kCIFormatRGBAh : kCIFormatRGBA8 colorSpace:colorSpace deferred:YES];
    CGColorSpaceRelease(colorSpace);

    [CATransaction begin];
    [CATransaction setDisableActions:YES];
    layer.frame = view.bounds;
    layer.contents = (__bridge id)image;
    [CATransaction commit];
    if (image) {
        CGImageRelease(image);
        CGContextClearRect(UIGraphicsGetCurrentContext(), view.bounds);
    } else LGDrawVLCSubtitle(view, selector, dirtyRect);
}

static void LGSetInlineCaptionGain(UIView *surface, CGFloat gain) {
    if (!surface) return;
    LGInlineCaptionLayer *layer = objc_getAssociatedObject(surface, &LGInlineCaptionLayerKey);
    if ((layer ? layer.gain : 1) == gain) return;
    if (gain == 1) {
        [layer removeFromSuperlayer];
        objc_setAssociatedObject(surface, &LGInlineCaptionLayerKey, nil, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    } else {
        if (!LGDrawVLCSubtitle) {
            // The pinned VLC renderer redraws this view on cue changes, including
            // animated captions. Intercept only its drawRect; the video layer
            // and unconfigured subtitle views use their native draw paths.
            Class cls = NSClassFromString(@"VLCSampleBufferSubpictureView");
            Method method = class_getInstanceMethod(cls, @selector(drawRect:));
            LGDrawVLCSubtitle = (void (*)(UIView *, SEL, CGRect))method_getImplementation(method);
            class_replaceMethod(cls, @selector(drawRect:), (IMP)LGDrawInlineSubtitle, method_getTypeEncoding(method));
        }
        if (!layer) {
            layer = [LGInlineCaptionLayer layer];
            [surface.layer addSublayer:layer];
            objc_setAssociatedObject(surface, &LGInlineCaptionLayerKey, layer, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        }
        layer.gain = gain;
        if (@available(iOS 26.0, *)) {
            layer.preferredDynamicRange = gain > 1 ? CADynamicRangeConstrainedHigh : CADynamicRangeStandard;
            layer.contentsHeadroom = gain > 1 ? gain : 0;
        } else if (@available(iOS 17.0, *)) layer.wantsExtendedDynamicRangeContent = gain > 1;
    }
    [surface setNeedsDisplay];
    [surface.layer displayIfNeeded];
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

- (BOOL)canAdjustInlineSubtitleBrightness {
    return ![self hasAirPlay] && !self.externalVideoHost && !self.casting && LGSubtitleSurface(self.movie) != nil;
}

- (void)updateInlineSubtitleBrightness {
    CGFloat gain = 1;
    UIView *surface = nil;
    if (self.surfaceVisible && !self.retired && !self.lockHidden && !self.pipActive && !self.movie.hidden &&
        ![self hasAirPlay] && !self.externalVideoHost && !self.casting) {
        BOOL brightAvailable = NO;
        if (@available(iOS 17.0, *)) brightAvailable = self.view.window.screen.potentialEDRHeadroom > 1;
        gain = LGCaptionGain([self playbackOptions][@"subtitle_brightness"], brightAvailable);
        if (gain != 1) surface = LGSubtitleSurface(self.movie);
    }
    if (self.brightnessSubtitleView != surface) LGSetInlineCaptionGain(self.brightnessSubtitleView, 1);
    self.brightnessSubtitleView = surface;
    LGSetInlineCaptionGain(surface, gain);
}

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
