// PiP receives one composited sample, including VLC's rendered subtitle planes.
// All pixels remain volatile. UIKit/layer capture runs on MAIN, only during PiP.
#import <AVKit/AVKit.h>
#import <CoreImage/CoreImage.h>

API_AVAILABLE(ios(17.4))
@interface LGCaptionPictureInPicture : NSObject <VLCPictureInPictureWindowControlling,
    AVPictureInPictureControllerDelegate, AVPictureInPictureSampleBufferPlaybackDelegate>
@property(nonatomic, weak) LGVideoController *owner;
@property(nonatomic, strong) AVPictureInPictureController *controller;
@property(nonatomic, strong) AVSampleBufferDisplayLayer *layer;
@property(nonatomic, strong) CIContext *context;
@property(nonatomic, strong) NSTimer *timer;
@property(nonatomic) CVPixelBufferPoolRef pool;
@property(nonatomic) CGSize poolSize;
@property(nonatomic) OSType poolFormat;
@property(nonatomic) NSUInteger framesProduced;
@property(nonatomic) BOOL starting, restoring, requested;
@property(nonatomic) NSTimeInterval startDeadline;
@property(nonatomic) void (^stateChangeEventHandler)(BOOL);
- (void)renderFrame;
@end

@implementation LGCaptionPictureInPicture
- (instancetype)initWithOwner:(LGVideoController *)owner {
    if (!(self = [super init])) return nil;
    if (![AVPictureInPictureController isPictureInPictureSupported]) return nil;
    self.owner = owner;
    self.layer = [AVSampleBufferDisplayLayer new];
    self.layer.videoGravity = AVLayerVideoGravityResizeAspect;
    self.context = [CIContext contextWithOptions:@{kCIContextCacheIntermediates: @NO}];
    CMTimebaseRef timebase;
    if (CMTimebaseCreateWithSourceClock(NULL, CMClockGetHostTimeClock(), &timebase) != noErr) return nil;
    CMTimebaseSetTime(timebase, CMClockGetTime(CMClockGetHostTimeClock()));
    CMTimebaseSetRate(timebase, 1);
    self.layer.controlTimebase = timebase;
    CFRelease(timebase);
    AVPictureInPictureControllerContentSource *source = [[AVPictureInPictureControllerContentSource alloc]
        initWithSampleBufferDisplayLayer:self.layer playbackDelegate:self];
    self.controller = [[AVPictureInPictureController alloc] initWithContentSource:source];
    self.controller.delegate = self;
    return self;
}
- (void)dealloc {
    [_timer invalidate];
    if (_pool) CVPixelBufferPoolRelease(_pool);
}
- (AVSampleBufferDisplayLayer *)sourceLayer {
    // The derivative layer is a direct CALayer, never a VLC drawable subview.
    for (UIView *view in self.owner.movie.subviews) {
        AVSampleBufferDisplayLayer *layer = [self.owner sampleBufferLayer:view.layer];
        if (layer) return layer;
    }
    return nil;
}
- (void)drawSubtitleViews:(UIView *)root context:(CGContextRef)cg {
    LGVideoController *owner = self.owner;
    for (UIView *view in root.subviews) {
        if (view.hidden || view.alpha <= 0 || [view.layer isKindOfClass:AVSampleBufferDisplayLayer.class]) continue;
        // VLC can wrap video and subpictures together. Descend through that
        // wrapper rather than excluding its subtitle sibling with the video.
        if ([owner sampleBufferLayer:view.layer]) {
            [self drawSubtitleViews:view context:cg];
            continue;
        }
        CGRect frame = [view convertRect:view.bounds toView:owner.movie];
        CGContextSaveGState(cg);
        CGContextTranslateCTM(cg, frame.origin.x, frame.origin.y);
        CGContextSetAlpha(cg, view.alpha);
        [view.layer displayIfNeeded];
        [view.layer renderInContext:cg];
        CGContextRestoreGState(cg);
    }
}
- (UIImage *)subtitlePlane:(CGSize)size {
    CGSize bounds = self.owner.movie.bounds.size;
    if (bounds.width <= 0 || bounds.height <= 0) return nil;
    UIGraphicsImageRendererFormat *format = [UIGraphicsImageRendererFormat defaultFormat];
    format.opaque = NO; format.scale = 1;
    UIGraphicsImageRenderer *renderer = [[UIGraphicsImageRenderer alloc] initWithSize:size format:format];
    return [renderer imageWithActions:^(UIGraphicsImageRendererContext *context) {
        CGContextScaleCTM(context.CGContext, size.width / bounds.width, size.height / bounds.height);
        [self drawSubtitleViews:self.owner.movie context:context.CGContext];
    }];
}
- (void)renderFrame {
    LGVideoController *owner = self.owner;
    if (!owner || owner.retired || owner.lockHidden || ![owner canPlay:YES]) {
        [self stopPictureInPicture]; return;
    }
    if (self.starting && NSProcessInfo.processInfo.systemUptime > self.startDeadline) {
        [self stopPictureInPicture];
        [owner showStatus:@"Picture in picture is not ready. Start playback and try again."];
        return;
    }
    if (!CGRectEqualToRect(self.layer.frame, owner.movie.bounds)) self.layer.frame = owner.movie.bounds;
    if (!self.layer.readyForMoreMediaData) return;
    CVPixelBufferRef source = [[self sourceLayer].sampleBufferRenderer copyDisplayedPixelBuffer];
    if (!source) return;
    @try {
        CGSize movie = owner.movie.bounds.size;
        if (movie.width <= 0 || movie.height <= 0) return;
        CGFloat scale = MIN(1, 720 / MAX(movie.width, movie.height));
        CGSize size = CGSizeMake(MAX(2, (int)(movie.width * scale) / 2 * 2),
                                 MAX(2, (int)(movie.height * scale) / 2 * 2));
        // Keep 10-bit HDR sources on a tagged 10-bit output, including color
        // conversion of the SDR subtitle plane into the source color space.
        OSType inputFormat = CVPixelBufferGetPixelFormatType(source);
        CFTypeRef sourceTransfer = CVBufferCopyAttachment(source, kCVImageBufferTransferFunctionKey, NULL);
        BOOL hdr = sourceTransfer && (CFEqual(sourceTransfer, kCVImageBufferTransferFunction_SMPTE_ST_2084_PQ) ||
                                      CFEqual(sourceTransfer, kCVImageBufferTransferFunction_ITU_R_2100_HLG));
        if (sourceTransfer) CFRelease(sourceTransfer);
        OSType pixelFormat = hdr || inputFormat == kCVPixelFormatType_420YpCbCr10BiPlanarVideoRange
            ? kCVPixelFormatType_420YpCbCr10BiPlanarVideoRange : kCVPixelFormatType_32BGRA;
        if (!self.pool || !CGSizeEqualToSize(size, self.poolSize) || self.poolFormat != pixelFormat) {
            if (self.pool) CVPixelBufferPoolRelease(self.pool);
            _pool = NULL;
            NSDictionary *attributes = @{(id)kCVPixelBufferWidthKey: @(size.width),
                (id)kCVPixelBufferHeightKey: @(size.height), (id)kCVPixelBufferPixelFormatTypeKey: @(pixelFormat),
                (id)kCVPixelBufferIOSurfacePropertiesKey: @{}};
            if (CVPixelBufferPoolCreate(NULL, NULL, (__bridge CFDictionaryRef)attributes, &_pool) != kCVReturnSuccess) return;
            self.poolSize = size; self.poolFormat = pixelFormat;
        }
        CVPixelBufferRef pixels = NULL;
        NSDictionary *limit = @{(id)kCVPixelBufferPoolAllocationThresholdKey: @3};
        if (CVPixelBufferPoolCreatePixelBufferWithAuxAttributes(NULL, self.pool,
                (__bridge CFDictionaryRef)limit, &pixels) != kCVReturnSuccess) return;
        CIImage *video = [CIImage imageWithCVPixelBuffer:source];
        CGRect canvas = CGRectMake(0, 0, size.width, size.height);
        CGRect clean = CVImageBufferGetCleanRect(source);
        if (!CGRectIsEmpty(clean)) video = [video imageByCroppingToRect:clean];
        CGSize display = CVImageBufferGetDisplaySize(source);
        if (display.width <= 0 || display.height <= 0) display = video.extent.size;
        CGRect target = AVMakeRectWithAspectRatioInsideRect(display, canvas);
        CGFloat sx = target.size.width / video.extent.size.width;
        CGFloat sy = target.size.height / video.extent.size.height;
        if ([[owner playbackOptions][@"aspect"] isEqualToString:@"fill"]) {
            CGFloat fill = MAX(size.width / display.width, size.height / display.height);
            target.size = CGSizeMake(display.width * fill, display.height * fill);
            sx = target.size.width / video.extent.size.width;
            sy = target.size.height / video.extent.size.height;
            target.origin = CGPointMake((size.width - target.size.width) / 2, (size.height - target.size.height) / 2);
        }
        video = [video imageByApplyingTransform:CGAffineTransformMakeTranslation(-video.extent.origin.x, -video.extent.origin.y)];
        video = [video imageByApplyingTransform:CGAffineTransformMakeScale(sx, sy)];
        video = [video imageByApplyingTransform:CGAffineTransformMakeTranslation(target.origin.x, target.origin.y)];
        video = [video imageByCompositingOverImage:[[CIImage imageWithColor:CIColor.blackColor] imageByCroppingToRect:canvas]];
        UIImage *plane = [self subtitlePlane:size];
        CIImage *image = plane ? [[CIImage imageWithCGImage:plane.CGImage] imageByCompositingOverImage:video] : video;
        CFTypeRef transfer = CVBufferCopyAttachment(source, kCVImageBufferTransferFunctionKey, NULL);
        CFStringRef spaceName = kCGColorSpaceSRGB;
        if (transfer && CFEqual(transfer, kCVImageBufferTransferFunction_SMPTE_ST_2084_PQ)) spaceName = kCGColorSpaceITUR_2100_PQ;
        else if (transfer && CFEqual(transfer, kCVImageBufferTransferFunction_ITU_R_2100_HLG)) spaceName = kCGColorSpaceITUR_2100_HLG;
        CGColorSpaceRef space = CGColorSpaceCreateWithName(spaceName);
        if (!hdr) {
            CVBufferSetAttachment(pixels, kCVImageBufferColorPrimariesKey, kCVImageBufferColorPrimaries_ITU_R_709_2, kCVAttachmentMode_ShouldPropagate);
            CVBufferSetAttachment(pixels, kCVImageBufferTransferFunctionKey, kCVImageBufferTransferFunction_sRGB, kCVAttachmentMode_ShouldPropagate);
        }
        for (NSString *key in hdr ? @[(__bridge NSString *)kCVImageBufferColorPrimariesKey,
                (__bridge NSString *)kCVImageBufferTransferFunctionKey,
                (__bridge NSString *)kCVImageBufferYCbCrMatrixKey,
                (__bridge NSString *)kCVImageBufferMasteringDisplayColorVolumeKey,
                (__bridge NSString *)kCVImageBufferContentLightLevelInfoKey] : @[]) {
            CFTypeRef value = CVBufferCopyAttachment(source, (__bridge CFStringRef)key, NULL);
            if (value) { CVBufferSetAttachment(pixels, (__bridge CFStringRef)key, value, kCVAttachmentMode_ShouldPropagate); CFRelease(value); }
        }
        [self.context render:image toCVPixelBuffer:pixels bounds:CGRectMake(0, 0, size.width, size.height) colorSpace:space];
        CGColorSpaceRelease(space);
        if (transfer) CFRelease(transfer);
        CMVideoFormatDescriptionRef description = NULL;
        CMSampleBufferRef sample = NULL;
        OSStatus error = CMVideoFormatDescriptionCreateForImageBuffer(NULL, pixels, &description);
        CMSampleTimingInfo timing = {CMTimeMake(1, 30), CMTimebaseGetTime(self.layer.controlTimebase), kCMTimeInvalid};
        if (error == noErr) error = CMSampleBufferCreateReadyWithImageBuffer(NULL, pixels, description, &timing, &sample);
        if (error == noErr) {
            CFArrayRef attachments = CMSampleBufferGetSampleAttachmentsArray(sample, YES);
            CFDictionarySetValue((CFMutableDictionaryRef)CFArrayGetValueAtIndex(attachments, 0),
                kCMSampleAttachmentKey_DisplayImmediately, kCFBooleanTrue);
            if (self.layer.status == AVQueuedSampleBufferRenderingStatusFailed) [self.layer flush];
            [self.layer enqueueSampleBuffer:sample];
            self.framesProduced++;
        }
        if (sample) CFRelease(sample);
        if (description) CFRelease(description);
        CVPixelBufferRelease(pixels);
    } @finally { CVPixelBufferRelease(source); }
}
- (void)startPictureInPicture {
    if (![self.owner canPlay:YES] || self.starting || self.controller.pictureInPictureActive) return;
    self.starting = YES; self.restoring = NO; self.requested = NO;
    self.startDeadline = NSProcessInfo.processInfo.systemUptime + 8;
    self.layer.frame = self.owner.movie.bounds;
    [self.owner configureVideoDynamicRange:self.layer];
    [self.owner.movie.layer addSublayer:self.layer];
    __weak LGCaptionPictureInPicture *weak = self;
    self.timer = [NSTimer timerWithTimeInterval:1.0 / 30 repeats:YES block:^(NSTimer *timer) {
        LGCaptionPictureInPicture *strong = weak;
        [strong renderFrame];
        if (strong.starting && !strong.requested && strong.layer.readyForDisplay && strong.controller.pictureInPicturePossible) {
            strong.requested = YES;
            [strong.controller startPictureInPicture];
        }
    }];
    [NSRunLoop.mainRunLoop addTimer:self.timer forMode:NSRunLoopCommonModes];
    [self invalidatePlaybackState];
    [self renderFrame];
}
- (void)discardFrames {
    self.starting = NO;
    [self.timer invalidate]; self.timer = nil;
    [self.layer flushAndRemoveImage];
    [self.layer removeFromSuperlayer];
    if (self.pool) { CVPixelBufferPoolRelease(self.pool); _pool = NULL; }
    [self.context clearCaches];
}
- (void)stopPictureInPicture {
    [self.controller stopPictureInPicture];
    [self discardFrames];
    [self setActive:NO];
}
- (void)setActive:(BOOL)active {
    self.starting = NO;
    self.owner.pipActive = active;
    [self.owner updateScreenAwake];
    [self.owner setControlsShown:YES];
    if (self.owner.externalOutputChanged) self.owner.externalOutputChanged();
    if (self.stateChangeEventHandler) self.stateChangeEventHandler(active);
}
- (void)invalidatePlaybackState {
    if (!self.layer.controlTimebase) return;
    CMTimebaseSetTime(self.layer.controlTimebase, CMClockGetTime(CMClockGetHostTimeClock()));
    float rate = self.owner.player.rate;
    CMTimebaseSetRate(self.layer.controlTimebase, self.owner.playRequested && !self.owner.pausePending
        ? (isfinite(rate) && rate > 0 ? rate : 1) : 0);
    self.controller.requiresLinearPlayback = ![self.owner isMediaSeekable];
    [self.controller invalidatePlaybackState];
}
- (void)pictureInPictureControllerWillStartPictureInPicture:(AVPictureInPictureController *)controller { [self setActive:YES]; }
- (void)pictureInPictureControllerDidStartPictureInPicture:(AVPictureInPictureController *)controller { [self setActive:YES]; }
- (void)pictureInPictureControllerDidStopPictureInPicture:(AVPictureInPictureController *)controller {
    [self discardFrames]; [self setActive:NO];
    if (!self.restoring && UIApplication.sharedApplication.applicationState != UIApplicationStateActive && !self.owner.casting)
        [self.owner pause];
}
- (void)pictureInPictureController:(AVPictureInPictureController *)controller failedToStartPictureInPictureWithError:(NSError *)error {
    [self discardFrames]; [self setActive:NO];
    [self.owner showStatus:@"Picture in picture could not start. Try again after playback resumes."];
}
- (void)pictureInPictureController:(AVPictureInPictureController *)controller restoreUserInterfaceForPictureInPictureStopWithCompletionHandler:(void (^)(BOOL))completion {
    self.restoring = YES;
    completion(!self.owner.retired && self.owner.view.window != nil);
}
- (void)pictureInPictureController:(AVPictureInPictureController *)controller setPlaying:(BOOL)playing {
    if (playing) [self.owner play]; else [self.owner pause];
    [self invalidatePlaybackState];
}
- (CMTimeRange)pictureInPictureControllerTimeRangeForPlayback:(AVPictureInPictureController *)controller {
    if (!self.owner || self.owner.retired) return kCMTimeRangeInvalid;
    int64_t length = [self.owner durationMilliseconds];
    CMTime duration = [self.owner isMediaSeekable] && length > 0 ? CMTimeMake(length, 1000) : kCMTimePositiveInfinity;
    return CMTimeRangeMake(CMTimeSubtract(CMTimebaseGetTime(self.layer.controlTimebase),
        CMTimeMake([self.owner positionMilliseconds], 1000)), duration);
}
- (BOOL)pictureInPictureControllerIsPlaybackPaused:(AVPictureInPictureController *)controller { return !self.owner.playRequested || self.owner.pausePending; }
- (void)pictureInPictureController:(AVPictureInPictureController *)controller didTransitionToRenderSize:(CMVideoDimensions)size {}
- (void)pictureInPictureController:(AVPictureInPictureController *)controller skipByInterval:(CMTime)interval completionHandler:(void (^)(void))completion {
    CMTime milliseconds = CMTimeConvertScale(interval, 1000, kCMTimeRoundingMethod_Default);
    [self.owner seekBy:CMTIME_IS_NUMERIC(milliseconds) ? milliseconds.value : 0 completion:^{
        [self invalidatePlaybackState]; completion();
    }];
}
@end

static id<VLCPictureInPictureWindowControlling> LGCreateCaptionPiP(LGVideoController *owner) {
    if (@available(iOS 17.4, *)) return [[LGCaptionPictureInPicture alloc] initWithOwner:owner];
    return nil;
}
