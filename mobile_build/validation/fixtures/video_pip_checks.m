static NSArray *LGPiPViewTree(UIView *view) {
    NSMutableArray *children = [NSMutableArray array];
    for (UIView *child in view.subviews) [children addObject:LGPiPViewTree(child)];
    return @[view.description, view.layer.description, children];
}
// Read the actual PiP sample output, not a substitute subtitle label.
static NSDictionary *LGPiPPixels(AVSampleBufferDisplayLayer *layer, NSString *path) API_AVAILABLE(ios(17.4)) {
    CVPixelBufferRef pixels = [layer.sampleBufferRenderer copyDisplayedPixelBuffer];
    if (!pixels) return @{};
    CIImage *image = [CIImage imageWithCVPixelBuffer:pixels];
    CGColorSpaceRef space = CGColorSpaceCreateWithName(kCGColorSpaceSRGB);
    CGImageRef cg = [[CIContext contextWithOptions:nil] createCGImage:image fromRect:image.extent
        format:kCIFormatRGBA8 colorSpace:space];
    CGColorSpaceRelease(space);
    size_t width = CGImageGetWidth(cg), height = CGImageGetHeight(cg);
    unsigned char *data = calloc(width * height, 4);
    CGColorSpaceRef rgb = CGColorSpaceCreateDeviceRGB();
    CGContextRef context = CGBitmapContextCreate(data, width, height, 8, width * 4, rgb,
        kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
    CGContextDrawImage(context, CGRectMake(0, 0, width, height), cg);
    NSUInteger white = 0, yellow = 0, blue = 0;
    for (size_t i = 0; i < width * height; i++) {
        if (data[i * 4 + 2] > data[i * 4] + 20 && data[i * 4 + 2] > data[i * 4 + 1] + 10) blue++;
        if (data[i * 4] > 180 && data[i * 4 + 1] > 180) {
            if (data[i * 4 + 2] > 180) white++;
            else if (data[i * 4 + 2] < 100) yellow++;
        }
    }
    if (path) [UIImagePNGRepresentation([UIImage imageWithCGImage:cg]) writeToFile:path atomically:YES];
    CFTypeRef transfer = CVBufferCopyAttachment(pixels, kCVImageBufferTransferFunctionKey, NULL);
    NSDictionary *result = @{@"transfer": transfer ? (__bridge id)transfer : @"", @"white": @(white), @"yellow": @(yellow), @"blue": @(blue),
        @"width": @(width), @"height": @(height), @"format": @(CVPixelBufferGetPixelFormatType(pixels))};
    if (transfer) CFRelease(transfer);
    CGContextRelease(context); CGColorSpaceRelease(rgb); CGImageRelease(cg); free(data); CVPixelBufferRelease(pixels);
    return result;
}

@implementation LGVideoChromeChecks (PiPChecks)
- (void)samplePipSubtitles {
    if (@available(iOS 17.4, *)) {
        NSTimeInterval now = NSProcessInfo.processInfo.systemUptime;
        if (now - self.started > 40) { [self finish:@"PiP caption stages did not finish"]; return; }
        LGVideoController *v = self.video;
        LGCaptionPictureInPicture *pip = (id)v.captionPiP;
        if (self.pipStage == 0 && v.player.isPlaying && now - self.started > 2) {
            if ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAPipEmbedded"] boolValue]) {
                if (!v.player.textTracks.count) return;
                v.player.textTracks.firstObject.selectedExclusively = YES;
            } else [v attachSubtitleURL:[NSBundle.mainBundle URLForResource:@"captions" withExtension:@"srt"].absoluteString];
            [v pip:nil]; self.pipStage = 1; self.pipStageTime = now;
            return;
        }
        [@{@"stage": @(self.pipStage), @"frames": @(pip.framesProduced),
            @"clock": @([v positionMilliseconds]), @"sourceReady": @([pip sourceLayer].readyForDisplay),
            @"possible": @(pip.controller.pictureInPicturePossible), @"active": @(pip.controller.pictureInPictureActive),
            @"ready": @(pip.layer.readyForDisplay), @"status": @(pip.layer.status),
            @"error": pip.layer.error.description ?: @"", @"views": v.movie.subviews.description ?: @""}
            writeToFile:[self outputPath:@"pip-progress.plist"] atomically:YES];
        if (!pip.controller.pictureInPictureActive) return;
        if (self.pipStage == 1 && self.samples.count == 0 && now - self.pipStageTime > 1) {
            [self.samples addObject:@{@"event": @"native-caption-hierarchy", @"views": LGPiPViewTree(v.movie),
                @"tracks": v.player.textTracks.description ?: @""}];
            UIImage *plane = [pip subtitlePlane:pip.layer.bounds.size];
            [UIImagePNGRepresentation(plane) writeToFile:[self outputPath:@"subtitle-plane.png"] atomically:YES];
        }
        NSDictionary *pixels = LGPiPPixels(pip.layer, nil);
        NSUInteger white = [pixels[@"white"] unsignedIntegerValue], yellow = [pixels[@"yellow"] unsignedIntegerValue];
        if (self.pipStage == 1 && white > 10) {
            if ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAHDR"] boolValue] &&
                (pip.poolFormat != kCVPixelFormatType_420YpCbCr10BiPlanarVideoRange ||
                 ![pixels[@"transfer"] isEqual:(__bridge NSString *)kCVImageBufferTransferFunction_SMPTE_ST_2084_PQ])) {
                [self finish:@"Caption composition lost 10-bit PQ output"]; return;
            }
            if (![[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAHDR"] boolValue] && [pixels[@"blue"] unsignedIntegerValue] < 100) {
                [self finish:@"Captioned PiP lost the decoded blue video plane"]; return;
            }
            [self.samples addObject:@{@"event": @"caption-in-active-pip", @"pixels": pixels, @"enqueuedFormat": @(pip.poolFormat)}];
            LGPiPPixels(pip.layer, [self outputPath:@"pip-caption-white.png"]);
            self.pipFrameCheckpoint = pip.framesProduced; self.pipClockCheckpoint = [v positionMilliseconds];
            [@"ready" writeToFile:[self outputPath:@"pip-ready.json"] atomically:YES encoding:NSUTF8StringEncoding error:nil];
            self.pipStage = 2; self.pipStageTime = now;
        } else if (self.pipStage == 2 && now - self.pipStageTime > 2) {
            if (![NSFileManager.defaultManager fileExistsAtPath:[self outputPath:@"pip-background-ready"]] ||
                UIApplication.sharedApplication.applicationState != UIApplicationStateBackground ||
                pip.framesProduced < self.pipFrameCheckpoint + 15 || [v positionMilliseconds] < self.pipClockCheckpoint + 1000) return;
            [self.samples addObject:@{@"event": @"pip-background-frames-and-clock", @"frames": @(pip.framesProduced)}];
            [pip pictureInPictureController:pip.controller setPlaying:NO];
            [v.player deselectAllTextTracks];
            self.pipStage = 3; self.pipStageTime = now;
        } else if (self.pipStage == 3 && now - self.pipStageTime > 1 && white + yellow < 5) {
            [self.samples addObject:@{@"event": @"subtitles-off-clears-pip", @"pixels": pixels}];
            if (!v.player.textTracks.count) { [self finish:@"The real VLC subtitle track disappeared"]; return; }
            v.player.textTracks.firstObject.selectedExclusively = YES;
            [v seekToMilliseconds:2000];
            [pip pictureInPictureController:pip.controller setPlaying:YES];
            self.pipStage = 4; self.pipStageTime = now;
        } else if (self.pipStage == 4 && now - self.pipStageTime > 1 && white + yellow > 10 &&
                   v.player.isPlaying && v.player.time.value.longLongValue >= 1500 &&
                   v.player.time.value.longLongValue < 6000) {
            [self.samples addObject:@{@"event": @"restored-caption-and-seek-clock", @"pixels": pixels,
                @"clock": @(v.player.time.value.longLongValue), @"shown": @([v positionMilliseconds])}];
            [pip pictureInPictureController:pip.controller setPlaying:NO];
            [pip pictureInPictureController:pip.controller skipByInterval:CMTimeMake(10000, 1000)
                completionHandler:^{ self.pipSeekCompletions++; }];
            [pip pictureInPictureController:pip.controller setPlaying:YES];
            self.pipStage = 5; self.pipStageTime = now;
        } else if (self.pipStage == 5 && now - self.pipStageTime > 1 &&
                   (yellow > 10 || ([[NSBundle.mainBundle objectForInfoDictionaryKey:@"QAPipEmbedded"] boolValue] && white > 10)) &&
                   v.player.time.value.longLongValue >= 8000 && v.player.time.value.longLongValue < 25000 && self.pipSeekCompletions == 1) {
            [self.samples addObject:@{@"event": @"forward-seek-selects-second-cue", @"pixels": pixels}];
            LGPiPPixels(pip.layer, [self outputPath:@"pip-caption-yellow.png"]);
            [pip pictureInPictureController:pip.controller skipByInterval:CMTimeMake(-10000, 1000)
                completionHandler:^{ self.pipSeekCompletions++; }];
            self.pipStage = 6; self.pipStageTime = now;
        } else if (self.pipStage == 6 && now - self.pipStageTime > 1 && self.pipSeekCompletions == 2 && white > 10 && yellow == 0) {
            [v retireWithCompletion:^{
                if (pip.timer || pip.pool || pip.layer.superlayer) { [self finish:@"PiP kept a frame producer or pixel pool after retirement"]; return; }
                [self.samples addObject:@{@"event": @"backward-seek-and-pip-retirement", @"frames": @(pip.framesProduced)}];
                [self finish:nil];
            }];
            self.pipStage = 7;
        }
        [@{ @"stage": @(self.pipStage), @"pixels": pixels, @"frames": @(pip.framesProduced),
            @"clock": @([v positionMilliseconds]), @"pipActive": @(pip.controller.pictureInPictureActive),
            @"sourcePixels": @([pip sourceLayer].readyForDisplay) }
            writeToFile:[self outputPath:@"pip-progress.plist"] atomically:YES];
    } else [self finish:@"PiP caption acceptance requires iOS 17.4 or later"];
}
@end
