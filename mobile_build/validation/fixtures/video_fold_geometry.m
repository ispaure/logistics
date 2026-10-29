// Appended to the real controller only in an owned native QA build. This
// supplies a horizontal reserved division, without claiming hardware posture.
@interface LGVideoQADivision : NSObject
@property(nonatomic) CGRect frame;
@end
@implementation LGVideoQADivision
- (BOOL)isActive { return YES; }
@end
@interface LGVideoQAView : UIView
@property(nonatomic) BOOL testFold;
@end
@implementation LGVideoQAView
- (NSArray *)reservedRegionsOfKind:(UIViewReservedRegionKind *)kind API_AVAILABLE(ios(27.1)) {
    if (!self.testFold) return @[];
    LGVideoQADivision *region = [LGVideoQADivision new];
    region.frame = CGRectMake(0, self.bounds.size.height / 2 - 6, self.bounds.size.width, 12);
    return @[region];
}
@end
@interface LGVideoPoseQAController : LGVideoController
- (void)applyTestFold:(BOOL)fold;
@end
@implementation LGVideoPoseQAController
- (void)loadView { self.view = [[LGVideoQAView alloc] initWithFrame:UIScreen.mainScreen.bounds]; }
- (void)setHingePartiallyOpen:(BOOL)fold {
    [super setHingePartiallyOpen:fold || ((LGVideoQAView *)self.view).testFold];
}
- (void)applyTestFold:(BOOL)fold {
    ((LGVideoQAView *)self.view).testFold = fold;
    self.hingePartiallyOpen = fold;
    [self.view setNeedsLayout];
    [self.view layoutIfNeeded];
}
@end
