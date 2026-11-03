// Shared by transfers and video players across all application scenes.
#import <UIKit/UIKit.h>

static NSUInteger LGScreenAwakeOwners = 0;
static BOOL LGScreenAwakePrevious = NO;

@interface LGScreenAwakeLease : NSObject
@property(nonatomic) BOOL finished;
- (void)finish;
@end

@implementation LGScreenAwakeLease
- (instancetype)init {
    self = [super init];
    if (self) {
        if (LGScreenAwakeOwners++ == 0) LGScreenAwakePrevious = UIApplication.sharedApplication.idleTimerDisabled;
        UIApplication.sharedApplication.idleTimerDisabled = YES;
    }
    return self;
}
- (void)finish {
    if (self.finished) return;
    self.finished = YES;
    if (--LGScreenAwakeOwners == 0) UIApplication.sharedApplication.idleTimerDisabled = LGScreenAwakePrevious;
}
@end
