#import <Foundation/Foundation.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/file.h>

static NSString * const LogisticsIncomingGroup = @"group.io.github.ispaure.logisticsmobile";
static const unsigned long long LogisticsFileLimit = 1024ULL * 1024 * 1024;

@interface LogisticsIncomingFiles : NSObject
+ (NSString *)privateQueue;
+ (NSString *)sharedQueue;
+ (BOOL)stageURL:(NSURL *)url queue:(NSString *)queue name:(NSString *)name cancelled:(BOOL (^)(void))cancelled;
+ (void)receiveURL:(NSURL *)url;
@end

@implementation LogisticsIncomingFiles
+ (NSString *)privateQueue {
    NSURL *support = [NSFileManager.defaultManager URLsForDirectory:NSApplicationSupportDirectory inDomains:NSUserDomainMask].firstObject;
    return [[support URLByAppendingPathComponent:@"Logistics/Incoming"] path];
}
+ (NSString *)sharedQueue {
    NSURL *group = [NSFileManager.defaultManager containerURLForSecurityApplicationGroupIdentifier:LogisticsIncomingGroup];
    return group ? [[group URLByAppendingPathComponent:@"Incoming"] path] : nil;
}
+ (BOOL)stageURL:(NSURL *)url queue:(NSString *)queue name:(NSString *)name cancelled:(BOOL (^)(void))cancelled {
    if (!url.isFileURL || !queue || !name.length || [name isEqual:@"."] || [name isEqual:@".."]
        || [name lengthOfBytesUsingEncoding:NSUTF8StringEncoding] > 240
        || [name rangeOfCharacterFromSet:NSCharacterSet.controlCharacterSet].location != NSNotFound
        || [name containsString:@"/"] || [name containsString:@"\\"]) return NO;
    NSFileManager *fm = NSFileManager.defaultManager;
    NSDictionary *attributes = @{NSFileProtectionKey:NSFileProtectionCompleteUntilFirstUserAuthentication};
    if (![fm createDirectoryAtPath:queue withIntermediateDirectories:YES attributes:attributes error:nil]) return NO;
    NSURL *queueURL = [NSURL fileURLWithPath:queue isDirectory:YES];
    if (![queueURL setResourceValue:@YES forKey:NSURLIsExcludedFromBackupKey error:nil]) return NO;
    int lockFD = open([[queue stringByAppendingPathComponent:@".producer.lock"] fileSystemRepresentation], O_CREAT | O_RDWR, 0600);
    if (lockFD < 0) return NO;
    if (flock(lockFD, LOCK_EX | LOCK_NB) != 0) { close(lockFD); return NO; }
    @try {
        // Bound the shared queue as well as each stream; incomplete copies count.
        unsigned long long queued = 0; NSUInteger files = 0;
        for (NSURL *child in [fm enumeratorAtURL:queueURL includingPropertiesForKeys:@[NSURLFileSizeKey, NSURLIsSymbolicLinkKey] options:0 errorHandler:nil]) {
            NSNumber *size = nil, *linked = nil;
            [child getResourceValue:&linked forKey:NSURLIsSymbolicLinkKey error:nil];
            if (linked.boolValue || ++files > 1000) return NO;
            [child getResourceValue:&size forKey:NSURLFileSizeKey error:nil];
            queued += size.unsignedLongLongValue;
        }
        if (queued >= 4 * LogisticsFileLimit) return NO;
        NSString *identifier = NSUUID.UUID.UUIDString;
        NSString *partial = [queue stringByAppendingPathComponent:[identifier stringByAppendingString:@".partial"]];
        if (![fm createDirectoryAtPath:partial withIntermediateDirectories:NO attributes:attributes error:nil]) return NO;
        __block BOOL success = NO;
        BOOL access = [url startAccessingSecurityScopedResource];
        NSFileCoordinator *coordinator = [[NSFileCoordinator alloc] initWithFilePresenter:nil];
        [coordinator coordinateReadingItemAtURL:url options:0 error:nil byAccessor:^(NSURL *source) {
            NSDictionary *info = [fm attributesOfItemAtPath:source.path error:nil];
            if (![info[NSFileType] isEqual:NSFileTypeRegular] || [info[NSFileSize] unsignedLongLongValue] > LogisticsFileLimit) return;
            NSString *payload = [partial stringByAppendingPathComponent:@"payload"];
            [fm createFileAtPath:payload contents:nil attributes:attributes];
            NSInputStream *input = [NSInputStream inputStreamWithURL:source];
            NSFileHandle *output = [NSFileHandle fileHandleForWritingAtPath:payload];
            if (!input || !output) return;
            [input open];
            uint8_t buffer[256 * 1024]; unsigned long long bytes = 0; NSInteger count;
            @try {
                while ((count = [input read:buffer maxLength:sizeof(buffer)]) > 0) {
                    bytes += count;
                    if (cancelled() || bytes > LogisticsFileLimit || queued + bytes > 4 * LogisticsFileLimit) break;
                    [output writeData:[NSData dataWithBytes:buffer length:count]];
                }
                success = count == 0 && !cancelled();
                [output synchronizeFile];
            } @catch (NSException *error) { success = NO; }
            @finally { [input close]; [output closeFile]; }
        }];
        if (access) [url stopAccessingSecurityScopedResource];
        NSData *metadata = [NSJSONSerialization dataWithJSONObject:@{@"name":name} options:0 error:nil];
        success = success && [metadata writeToFile:[partial stringByAppendingPathComponent:@"metadata.json"] options:NSDataWritingAtomic | NSDataWritingFileProtectionCompleteUntilFirstUserAuthentication error:nil];
        if (success) success = [fm moveItemAtPath:partial toPath:[queue stringByAppendingPathComponent:[identifier stringByAppendingString:@".ready"]] error:nil];
        if (!success) [fm removeItemAtPath:partial error:nil];
        return success;
    } @finally { flock(lockFD, LOCK_UN); close(lockFD); }
}
+ (void)receiveURL:(NSURL *)url {
    if (!url.isFileURL) return;
    NSString *documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject.path;
    NSString *inbox = [[documents stringByAppendingPathComponent:@"Inbox"] stringByAppendingString:@"/"];
    // UIKit's copy-mode Open in has already delivered a durable Inbox file.
    if ([url.URLByResolvingSymlinksInPath.path hasPrefix:inbox]) return;
    // Acquire the grant before returning to UIKit; balance after the worker.
    BOOL access = [url startAccessingSecurityScopedResource];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        BOOL saved = [self stageURL:url queue:self.privateQueue name:url.lastPathComponent cancelled:^BOOL { return NO; }];
        if (access) [url stopAccessingSecurityScopedResource];
        if (!saved) {
            // A generic durable marker avoids exposing caller names in logs.
            NSString *marker = [self.privateQueue stringByAppendingPathComponent:@"failed"];
            [@"Some files could not be received. Share them again." writeToFile:marker atomically:YES encoding:NSUTF8StringEncoding error:nil];
        }
    });
}
@end
