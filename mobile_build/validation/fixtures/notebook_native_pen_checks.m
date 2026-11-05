// Synthetic native transport contracts only: no UITouch private ivars, swizzles,
// injected real UIKit events, physical hardware, accounts or document content.
#import <UIKit/UIKit.h>
#import <WebKit/WebKit.h>
#import <JavaScriptCore/JavaScriptCore.h>

// Included after the production .m in the QA-only translation unit.
@interface LogisticsNotebookInputWindow (NativeChecks)
- (BOOL)bindNotebookWebView:(WKWebView *)view forceMode:(NSInteger)mode viewID:(NSString *)viewID;
- (void)unbindNotebookWebView:(WKWebView *)view;
- (BOOL)notebookWebViewEnabled:(WKWebView *)view;
- (void)captureNotebookTouch:(UITouch *)touch event:(UIEvent *)event;
- (void)notebookInactive:(NSNotification *)notification;
@end

static void LGNotebookRequire(BOOL value, NSString *reason) {
    if (!value) @throw [NSException exceptionWithName:@"LogisticsNotebookNativeCheck" reason:reason userInfo:nil];
}
static NSString *const LGNonceA = @"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
static NSString *const LGNonceB = @"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

// Override public read-only getters. These objects are passed ONLY to the
// project producer API, never to [UIWindow sendEvent:] or UIKit recognizers.
@interface LGNotebookTestTouch : UITouch
@property(nonatomic, weak) UIWindow *testWindow;
@property(nonatomic, weak) UIView *testView;
@property(nonatomic) UITouchType testType;
@property(nonatomic) UITouchPhase testPhase;
@property(nonatomic) CGPoint testPoint;
@property(nonatomic) CGFloat testForce;
@property(nonatomic) CGFloat testMaximum;
@end
@implementation LGNotebookTestTouch
- (UIWindow *)window { return self.testWindow; }
- (UIView *)view { return self.testView; }
- (UITouchType)type { return self.testType; }
- (UITouchPhase)phase { return self.testPhase; }
- (CGPoint)locationInView:(UIView *)view { return self.testPoint; }
- (CGFloat)force { return self.testForce; }
- (CGFloat)maximumPossibleForce { return self.testMaximum; }
@end
@interface LGNotebookTestEvent : UIEvent
@property(nonatomic, strong) NSArray<UITouch *> *testCoalesced;
@end
@implementation LGNotebookTestEvent
- (NSArray<UITouch *> *)coalescedTouchesForTouch:(UITouch *)touch { return self.testCoalesced; }
@end

@interface LGNotebookTestWebView : WKWebView
@property(nonatomic, strong) NSMutableArray<NSString *> *scripts;
@property(nonatomic, strong) NSMutableArray *completions;
@property(nonatomic, strong) JSContext *testContext;
- (void)releaseOne;
- (void)releaseAll;
- (NSArray<NSArray *> *)packets;
@end
@implementation LGNotebookTestWebView
- (instancetype)initWithFrame:(CGRect)frame configuration:(WKWebViewConfiguration *)configuration {
    if ((self=[super initWithFrame:frame configuration:configuration])) {
        _scripts=[NSMutableArray array]; _completions=[NSMutableArray array];
        _testContext=[JSContext new];
        [_testContext evaluateScript:@"var window=this,state={native_pen:true},qaViewID='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',qaCalls=[],qaActive=null;function logisticsInputTrace(){return {view_id:qaViewID}};function logisticsNativePen(action,id,points,w,h){qaCalls.push([action,id]);if(action==='down')qaActive=id;else if((action==='up'||action==='cancel')&&qaActive===id)qaActive=null};function logisticsNativePenReset(){qaActive=null}"];
    }
    return self;
}
- (void)evaluateJavaScript:(NSString *)script completionHandler:(void (^)(id,NSError *))completionHandler {
    [self.scripts addObject:script];
    [self.testContext evaluateScript:script];
    LGNotebookRequire(self.testContext.exception==nil,@"Generated native script did not parse/execute in JavaScriptCore");
    if (completionHandler) [self.completions addObject:[completionHandler copy]];
}
- (void)releaseOne {
    LGNotebookRequire(self.completions.count>0,@"Missing held WK completion");
    void (^completion)(id,NSError *)=self.completions.firstObject;
    [self.completions removeObjectAtIndex:0]; completion(nil,nil);
}
- (void)releaseAll {
    NSUInteger count=0;
    while (self.completions.count) { LGNotebookRequire(++count<=300,@"Native completion chain exceeded bounded fixture limit"); [self releaseOne]; }
}
- (NSArray<NSArray *> *)packets {
    NSMutableArray *result=[NSMutableArray array];
    for (NSString *script in self.scripts) {
        NSRange start=[script rangeOfString:@"const p="],end=[script rangeOfString:@";if(window.logisticsInputTrace"];
        if (start.location==NSNotFound || end.location==NSNotFound) continue;
        NSUInteger offset=NSMaxRange(start);
        LGNotebookRequire(end.location>offset,@"Native packet envelope is invalid");
        NSString *text=[script substringWithRange:NSMakeRange(offset,end.location-offset)];
        NSArray *envelope=[NSJSONSerialization JSONObjectWithData:[text dataUsingEncoding:NSUTF8StringEncoding] options:0 error:NULL];
        LGNotebookRequire([envelope isKindOfClass:NSArray.class] && envelope.count==2,@"Native packet envelope JSON is invalid");
        [result addObject:envelope];
    }
    return result;
}
@end

@interface LogisticsNotebookNativeChecks : NSObject
+ (NSDictionary *)runOnWindow:(UIWindow *)window;
@end
@implementation LogisticsNotebookNativeChecks
+ (LGNotebookTestWebView *)viewIn:(UIView *)host {
    WKWebViewConfiguration *config=[WKWebViewConfiguration new];
    config.websiteDataStore=WKWebsiteDataStore.nonPersistentDataStore;
    LGNotebookTestWebView *view=[[LGNotebookTestWebView alloc] initWithFrame:CGRectMake(0,0,160,200) configuration:config];
    [host addSubview:view]; return view;
}
+ (LGNotebookTestTouch *)touchFor:(UIView *)view window:(UIWindow *)window {
    LGNotebookTestTouch *touch=[LGNotebookTestTouch new];
    touch.testWindow=window;touch.testView=view;touch.testType=UITouchTypePencil;
    touch.testPhase=UITouchPhaseBegan;touch.testPoint=CGPointMake(40,60);
    touch.testForce=0;touch.testMaximum=0; return touch;
}
+ (void)dot:(LogisticsNotebookInputWindow *)window view:(UIView *)view event:(LGNotebookTestEvent *)event {
    LGNotebookTestTouch *touch=[self touchFor:view window:window];
    [window captureNotebookTouch:touch event:event];
    touch.testPhase=UITouchPhaseEnded;
    [window captureNotebookTouch:touch event:event];
}
+ (NSDictionary *)runOnWindow:(UIWindow *)input {
    if (!NSThread.isMainThread) return @{@"success":@NO,@"error":@"Native fixture requires the main UIKit thread"};
    if (![input isKindOfClass:LogisticsNotebookInputWindow.class] || !input.isKeyWindow)
        return @{@"success":@NO,@"error":@"Use the actual owned/key native producer window"};
    LogisticsNotebookInputWindow *window=(id)input;
    NSMutableArray *cases=[NSMutableArray array];
    UIView *host=[[UIView alloc] initWithFrame:CGRectMake(0,0,200,240)];
    [window.rootViewController.view addSubview:host];
    NSMutableArray<LGNotebookTestWebView *> *views=[NSMutableArray array];
    NSDictionary *report=nil;
    @try {
        LGNotebookTestEvent *event=[LGNotebookTestEvent new];
        // Hold the first completion: the actual native queue must preserve all
        // forty packets independently of browser event admission/recognizers.
        LGNotebookTestWebView *view=[self viewIn:host];[views addObject:view];
        LGNotebookRequire(view.window==window,@"Synthetic WK view did not attach to owned window");
        LGNotebookRequire([window bindNotebookWebView:view forceMode:1 viewID:LGNonceA],@"Native binding rejected");
        for(NSUInteger i=0;i<20;i++)[self dot:window view:view event:event];
        LGNotebookRequire(view.packets.count==1 && view.completions.count==1,@"First WK completion was not held");
        [view releaseAll];NSArray *packets=view.packets;
        LGNotebookRequire(packets.count==40,@"Twenty rapid native dots lost/duplicated packets");
        for(NSUInteger i=0;i<20;i++) {
            NSArray *down=packets[i*2][1],*up=packets[i*2+1][1];
            LGNotebookRequire([down[0] isEqual:@"down"] && [up[0] isEqual:@"up"] && [down[1] isEqual:up[1]] && [down[1] unsignedIntegerValue]==i+1,@"Native FIFO/contact IDs changed");
            LGNotebookRequire([down[2] count]==1 && [down[2][0][2] doubleValue]==.5,@"Confirmed USB-C constant force did not remain .5");
        }
        LGNotebookRequire([[view.testContext evaluateScript:@"qaCalls.length"] toNumber].unsignedIntegerValue==40,@"Native generated scripts did not preserve twenty dots");
        [window unbindNotebookWebView:view];[view releaseAll];
        [cases addObject:@"twenty-rapid-one-point-dots-held-first-completion-fifo"];

        view=[self viewIn:host];[views addObject:view];
        LGNotebookRequire([window bindNotebookWebView:view forceMode:0 viewID:LGNonceA],@"Event-force bind rejected");
        LGNotebookTestTouch *touch=[self touchFor:view window:window];
        touch.testForce=2;touch.testMaximum=4;
        [window captureNotebookTouch:touch event:event];[view releaseAll];
        LGNotebookRequire([view.packets[0][1][2][0][2] doubleValue]==.5,@"Positive event force normalization changed");
        LGNotebookTestTouch *a=[self touchFor:view window:window],*b=[self touchFor:view window:window];
        a.testPoint=CGPointMake(45,65);b.testPoint=CGPointMake(50,70);a.testForce=b.testForce=2;a.testMaximum=b.testMaximum=4;
        touch.testPhase=UITouchPhaseMoved;touch.testPoint=CGPointMake(55,75);event.testCoalesced=@[a,b];
        [window captureNotebookTouch:touch event:event];[view releaseAll];
        NSArray *points=view.packets[1][1][2];
        LGNotebookRequire(points.count==3 && [points[0][0] doubleValue]==45 && [points[1][0] doubleValue]==50 && [points[2][0] doubleValue]==55,@"Coalesced points were reordered/dropped");
        touch.testPhase=UITouchPhaseEnded;event.testCoalesced=nil;[window captureNotebookTouch:touch event:event];[view releaseAll];
        [window unbindNotebookWebView:view];[view releaseAll];[cases addObject:@"coalesced-history-and-event-pressure"];

        view=[self viewIn:host];[views addObject:view];
        LGNotebookRequire([window bindNotebookWebView:view forceMode:0 viewID:LGNonceA],@"Unsupported-force bind rejected");
        [self dot:window view:view event:event];[view releaseAll];
        LGNotebookRequire([view.packets[0][1][2][0][2] doubleValue]==.5,@"Unsupported zero/max-zero force must remain visible .5");
        NSUInteger before=view.packets.count;
        touch=[self touchFor:view window:window];touch.testType=UITouchTypeDirect;[window captureNotebookTouch:touch event:event];
        UIWindow *foreign=[[UIWindow alloc] initWithFrame:CGRectMake(0,0,20,20)];
        touch=[self touchFor:view window:foreign];[window captureNotebookTouch:touch event:event];
        touch=[self touchFor:host window:window];[window captureNotebookTouch:touch event:event];
        LGNotebookRequire(view.packets.count==before,@"Finger/foreign-window/native-toolbar target became ink");
        [window unbindNotebookWebView:view];[view releaseAll];[cases addObject:@"unsupported-force-finger-foreign-window-toolbar-admission"];

        // Retirement drops starts never submitted to WK; only contact1 may be
        // cancelled, not the most recent queued contact ID.
        view=[self viewIn:host];[views addObject:view];
        LGNotebookRequire([window bindNotebookWebView:view forceMode:1 viewID:LGNonceA],@"Retirement bind rejected");
        for(NSUInteger i=0;i<20;i++)[self dot:window view:view event:event];
        [window unbindNotebookWebView:view];LGNotebookRequire(![window notebookWebViewEnabled:view],@"Retired binding remained enabled");
        [view releaseAll];packets=view.packets;
        LGNotebookRequire(packets.count==2 && [packets[1][1][0] isEqual:@"cancel"] && [packets[1][1][1] isEqual:packets[0][1][1]],@"Retirement delivered stale starts or cancelled the wrong in-flight contact");
        [cases addObject:@"retire-drops-unsubmitted-contact-starts"];

        view=[self viewIn:host];[views addObject:view];
        LGNotebookRequire([window bindNotebookWebView:view forceMode:1 viewID:LGNonceA],@"Focus bind rejected");
        [self dot:window view:view event:event];[self dot:window view:view event:event];
        [window notebookInactive:nil];[view releaseAll];
        LGNotebookRequire(view.packets.count==2 && [view.packets[1][1][0] isEqual:@"cancel"],@"Inactive window did not cancel the submitted contact");
        [window unbindNotebookWebView:view];[view releaseAll];[cases addObject:@"focus-cancels-inflight-not-queued-contact"];

        view=[self viewIn:host];[views addObject:view];
        LGNotebookRequire([window bindNotebookWebView:view forceMode:1 viewID:LGNonceA],@"Overflow bind rejected");
        for(NSUInteger i=0;i<100;i++)[self dot:window view:view event:event];
        LGNotebookRequire(![window notebookWebViewEnabled:view],@"Overflow did not stop native capture");
        [view releaseAll];packets=view.packets;
        LGNotebookRequire(packets.count==2 && [packets[1][1][0] isEqual:@"cancel"] && [packets[1][1][1] isEqual:packets[0][1][1]],@"Overflow cancelled latest queued rather than actual in-flight contact");
        LGNotebookRequire(![[view.testContext evaluateScript:@"state.native_pen"] toBool],@"Overflow did not restore ordinary DOM input");
        [window unbindNotebookWebView:view];[view releaseAll];[cases addObject:@"overflow-failclosed-inflight-cancel-dom-fallback"];

        view=[self viewIn:host];[views addObject:view];
        LGNotebookRequire([window bindNotebookWebView:view forceMode:1 viewID:LGNonceA],@"Old nonce bind rejected");
        [self dot:window view:view event:event];[window unbindNotebookWebView:view];
        [view.testContext evaluateScript:@"qaViewID='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';qaActive=null;qaCalls=[];state.native_pen=true"];
        LGNotebookRequire([window bindNotebookWebView:view forceMode:1 viewID:LGNonceB],@"Replacement nonce bind rejected");
        touch=[self touchFor:view window:window];[window captureNotebookTouch:touch event:event];
        [view releaseOne]; // Old completion submits old cancellation AFTER new down.
        LGNotebookRequire([[view.testContext evaluateScript:@"qaActive"] toNumber].integerValue==1,@"Old nonce cancellation erased replacement contact");
        touch.testPhase=UITouchPhaseEnded;[window captureNotebookTouch:touch event:event];[view releaseAll];
        LGNotebookRequire([[view.testContext evaluateScript:@"qaCalls.length"] toNumber].integerValue==2,@"Stale-nonce packets reached replacement document");
        [window unbindNotebookWebView:view];[view releaseAll];[cases addObject:@"old-inflight-nonce-cannot-cancel-replacement-contact"];
        report=@{@"success":@YES,@"diagnostic_only":@YES,@"cases":cases,@"native_transport_only":@YES,
                 @"physical_pencil_tested":@NO,@"system_super_forwarding":@"source contract; synthetic events never passed into UIKit"};
    } @catch(NSException *error) {
        report=@{@"success":@NO,@"diagnostic_only":@YES,@"cases":cases,
                 @"error":[error.name isEqual:@"LogisticsNotebookNativeCheck"] ? error.reason : @"Unexpected native fixture exception"};
    } @finally {
        NSMutableArray *cleanupErrors=[NSMutableArray array];
        for(LGNotebookTestWebView *view in views) {
            @try { [window unbindNotebookWebView:view]; }
            @catch(NSException *error) { [cleanupErrors addObject:@"Native unbind failed"]; }
            @try { [view releaseAll]; }
            @catch(NSException *error) { [cleanupErrors addObject:@"Held native completion cleanup failed"]; }
            @try { [view removeFromSuperview]; }
            @catch(NSException *error) { [cleanupErrors addObject:@"Synthetic view cleanup failed"]; }
        }
        @try { [host removeFromSuperview]; }
        @catch(NSException *error) { [cleanupErrors addObject:@"Synthetic host cleanup failed"]; }
        if(cleanupErrors.count) {
            NSMutableDictionary *failed=[report mutableCopy] ?: [NSMutableDictionary dictionary];
            failed[@"success"]=@NO;failed[@"cleanup_errors"]=cleanupErrors;report=failed;
        }
    }
    return report;
}
@end
