#import <UIKit/UIKit.h>

// Start the Swift bridge after UIApplication has launched; no Python callbacks or session access.
@interface LogisticsWatchValueBootstrap : NSObject
@end
@implementation LogisticsWatchValueBootstrap
+ (void)load {
    [NSNotificationCenter.defaultCenter addObserverForName:UIApplicationDidFinishLaunchingNotification
        object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *notification) {
        Class publisher = NSClassFromString(@"LogisticsWatchValuePublisher");
        if ([publisher respondsToSelector:@selector(start)]) [publisher performSelector:@selector(start)];
    }];
    [NSNotificationCenter.defaultCenter addObserverForName:UIApplicationDidBecomeActiveNotification
        object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *notification) {
        Class publisher = NSClassFromString(@"LogisticsWatchValuePublisher");
        if ([publisher respondsToSelector:@selector(retry)]) [publisher performSelector:@selector(retry)];
    }];
}
@end
