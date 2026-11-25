// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

#import <AVFoundation/AVFoundation.h>
#import <ImageIO/ImageIO.h>
#import <PhotosUI/PhotosUI.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>

typedef void (^LGNotebookPhotoCompletion)(NSData * _Nullable, NSString * _Nullable);

static char LGNotebookPhotoDelegateKey;
static const NSUInteger LGNotebookPhotoByteLimit = 1280 * 1024;
static const CGFloat LGNotebookPhotoEdge = 1600;

static NSData *LGNotebookPNG(UIImage *image, CGFloat edge) {
    CGSize original = image.size;
    if (original.width <= 0 || original.height <= 0) return nil;
    CGFloat ratio = MIN(image.scale, edge / MAX(original.width, original.height));
    CGSize size = CGSizeMake(MAX(1, round(original.width * ratio)), MAX(1, round(original.height * ratio)));
    UIGraphicsImageRendererFormat *format = [UIGraphicsImageRendererFormat defaultFormat];
    format.scale = 1;
    format.opaque = YES;
    format.preferredRange = UIGraphicsImageRendererFormatRangeStandard;
    UIGraphicsImageRenderer *renderer = [[UIGraphicsImageRenderer alloc] initWithSize:size format:format];
    return [renderer PNGDataWithActions:^(UIGraphicsImageRendererContext *context) {
        CGRect rect = CGRectMake(0, 0, size.width, size.height);
        CGContextSetRGBFillColor(context.CGContext, 1, 1, 1, 1);
        CGContextFillRect(context.CGContext, rect);
        [image drawInRect:rect];
    }];
}

static NSData *LGNotebookBoundedPhoto(UIImage *image) {
    if (!image) return nil;
    CGFloat edge = LGNotebookPhotoEdge;
    NSData *data = LGNotebookPNG(image, edge);
    while (data.length > LGNotebookPhotoByteLimit && edge > 320) {
        edge = floor(edge * .75);
        data = LGNotebookPNG(image, edge);
    }
    return data.length && data.length <= LGNotebookPhotoByteLimit ? data : nil;
}

static UIImage *LGNotebookPhotoThumbnail(NSURL *url) {
    NSNumber *size = nil;
    if (![url getResourceValue:&size forKey:NSURLFileSizeKey error:NULL] ||
        size.unsignedLongLongValue > 128 * 1024 * 1024) return nil;
    CGImageSourceRef source = CGImageSourceCreateWithURL((__bridge CFURLRef)url, NULL);
    if (!source) return nil;
    NSMutableDictionary *options = [@{
        (__bridge NSString *)kCGImageSourceCreateThumbnailFromImageAlways: @YES,
        (__bridge NSString *)kCGImageSourceCreateThumbnailWithTransform: @YES,
        (__bridge NSString *)kCGImageSourceThumbnailMaxPixelSize: @(LGNotebookPhotoEdge),
        (__bridge NSString *)kCGImageSourceShouldCacheImmediately: @YES
    } mutableCopy];
    if (@available(iOS 17.0, *)) {
        options[(__bridge NSString *)kCGImageSourceDecodeRequest] = (__bridge NSString *)kCGImageSourceDecodeToSDR;
    }
    CGImageRef thumbnail = CGImageSourceCreateThumbnailAtIndex(source, 0, (__bridge CFDictionaryRef)options);
    CFRelease(source);
    if (!thumbnail) return nil;
    UIImage *image = [UIImage imageWithCGImage:thumbnail];
    CGImageRelease(thumbnail);
    return image;
}

@interface LogisticsNotebookPhotoPicker : NSObject <PHPickerViewControllerDelegate, UIImagePickerControllerDelegate, UINavigationControllerDelegate>
@property(nonatomic, copy) LGNotebookPhotoCompletion completion;
+ (BOOL)cameraAvailable;
+ (BOOL)showFrom:(UIViewController *)presenter camera:(BOOL)camera completion:(LGNotebookPhotoCompletion)completion;
@end

@implementation LogisticsNotebookPhotoPicker

+ (BOOL)cameraAvailable {
    return [UIImagePickerController isSourceTypeAvailable:UIImagePickerControllerSourceTypeCamera];
}

+ (BOOL)showFrom:(UIViewController *)presenter camera:(BOOL)camera completion:(LGNotebookPhotoCompletion)completion {
    if (!presenter.view.window || presenter.presentedViewController || !completion) return NO;
    if (camera && ![self cameraAvailable]) return NO;
    if (camera && [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeVideo] != AVAuthorizationStatusAuthorized) {
        AVAuthorizationStatus status = [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeVideo];
        if (status != AVAuthorizationStatusNotDetermined) {
            completion(nil, @"Allow camera access in Settings to take a photo.");
        } else {
            [AVCaptureDevice requestAccessForMediaType:AVMediaTypeVideo completionHandler:^(BOOL allowed) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    if (!allowed) completion(nil, @"Camera access was declined.");
                    else if (![self showFrom:presenter camera:YES completion:completion])
                        completion(nil, @"The notebook is no longer ready to show the camera.");
                });
            }];
        }
        return YES;
    }
    LogisticsNotebookPhotoPicker *delegate = [self new];
    delegate.completion = completion;
    UIViewController *picker;
    if (camera) {
        UIImagePickerController *controller = [UIImagePickerController new];
        controller.sourceType = UIImagePickerControllerSourceTypeCamera;
        controller.delegate = delegate;
        picker = controller;
    } else {
        PHPickerConfiguration *configuration = [PHPickerConfiguration new];
        configuration.filter = PHPickerFilter.imagesFilter;
        configuration.selectionLimit = 1;
        configuration.preferredAssetRepresentationMode = PHPickerConfigurationAssetRepresentationModeCurrent;
        PHPickerViewController *controller = [[PHPickerViewController alloc] initWithConfiguration:configuration];
        controller.delegate = delegate;
        picker = controller;
    }
    picker.modalPresentationStyle = UIModalPresentationFullScreen;
    objc_setAssociatedObject(picker, &LGNotebookPhotoDelegateKey, delegate, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    [presenter presentViewController:picker animated:YES completion:nil];
    return YES;
}

- (void)picker:(PHPickerViewController *)picker didFinishPicking:(NSArray<PHPickerResult *> *)results {
    NSItemProvider *provider = results.firstObject.itemProvider;
    LGNotebookPhotoCompletion completion = self.completion;
    [picker dismissViewControllerAnimated:YES completion:^{
        if (!provider) {
            completion(nil, nil);
            return;
        }
        [provider loadFileRepresentationForTypeIdentifier:@"public.image" completionHandler:^(NSURL *url, NSError *error) {
            NSData *image = url && !error ? LGNotebookBoundedPhoto(LGNotebookPhotoThumbnail(url)) : nil;
            dispatch_async(dispatch_get_main_queue(), ^{
                completion(image, image ? nil : @"Could not prepare this photo for the notebook.");
            });
        }];
    }];
}

- (void)imagePickerControllerDidCancel:(UIImagePickerController *)picker {
    LGNotebookPhotoCompletion completion = self.completion;
    [picker dismissViewControllerAnimated:YES completion:^{ completion(nil, nil); }];
}

- (void)imagePickerController:(UIImagePickerController *)picker
    didFinishPickingMediaWithInfo:(NSDictionary<UIImagePickerControllerInfoKey, id> *)info {
    UIImage *photo = info[UIImagePickerControllerOriginalImage];
    LGNotebookPhotoCompletion completion = self.completion;
    [picker dismissViewControllerAnimated:YES completion:^{
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
            NSData *image = LGNotebookBoundedPhoto(photo);
            dispatch_async(dispatch_get_main_queue(), ^{
                completion(image, image ? nil : @"Could not prepare this photo for the notebook.");
            });
        });
    }];
}
@end
