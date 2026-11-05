// Project-owned UIWindow; UIKit remains the sole system event dispatcher.
#import <UIKit/UIKit.h>
#import <WebKit/WebKit.h>
#import <math.h>

// No public API identifies the connected Pencil model. Callers must explicitly
// select event-payload normalization (0) or explicitly confirmed constant (1).
// Event normalization is not connected-Pencil model/capability detection.
typedef NS_ENUM(NSInteger, LogisticsPencilForceMode) {
    LogisticsPencilEventForce = 0, LogisticsPencilConstant = 1
};
static const NSUInteger LogisticsPencilMaxPackets = 128;
static const NSUInteger LogisticsPencilMaxSamples = 8192;

@protocol LogisticsNotebookPencilMetrics <NSObject>
- (void)recordPencilMetric:(NSString *)metric;
@end

@interface LogisticsNotebookPencilBinding : NSObject
@property(nonatomic, weak) WKWebView *view;
@property(nonatomic, weak) id<LogisticsNotebookPencilMetrics> metrics;
@property(nonatomic, copy) NSString *viewID;
@property(nonatomic) LogisticsPencilForceMode forceMode;
@property(nonatomic, weak) UITouch *touch;
@property(nonatomic, strong) NSMutableArray<NSArray *> *packets;
@property(nonatomic, strong) NSArray<NSNumber *> *lastPoint;
@property(nonatomic, strong) NSArray *inflightPacket;
@property(nonatomic, strong) NSArray *deliveredPacket;
@property(nonatomic) CGSize lastSize;
@property(nonatomic) NSUInteger samples;
@property(nonatomic) NSUInteger nextContact;
@property(nonatomic) NSUInteger contact;
@property(nonatomic) BOOL pending;
@property(nonatomic) NSUInteger epoch;
@property(nonatomic, strong) dispatch_source_t deadlineTimer;
@property(nonatomic) BOOL accepting;
@property(nonatomic) BOOL retired;
- (void)capture:(UITouch *)touch event:(UIEvent *)event;
- (void)cancel;
- (void)retire;
- (void)cancelUnsubmitted;
- (void)drain;
- (void)stopDeadline;
@end

@implementation LogisticsNotebookPencilBinding
- (instancetype)init {
    if ((self = [super init])) { _packets = [NSMutableArray array]; _nextContact = 1; _accepting = YES; }
    return self;
}
- (void)stopDeadline {
    if (self.deadlineTimer) { dispatch_source_cancel(self.deadlineTimer); self.deadlineTimer = nil; }
}
- (void)dealloc { [self stopDeadline]; }
- (NSArray<NSNumber *> *)point:(UITouch *)touch {
    WKWebView *view = self.view;
    if (!view) return nil;
    CGPoint p = [touch locationInView:view];
    if (!isfinite(p.x) || !isfinite(p.y)) return nil;
    double pressure = .5;
    if (self.forceMode == LogisticsPencilEventForce) {
        double force = touch.force, maximum = touch.maximumPossibleForce;
        if (isfinite(force) && isfinite(maximum) && maximum > 0 && force > 0) pressure = fmax(0, fmin(1, force / maximum));
    }
    return @[@(p.x), @(p.y), @(pressure)];
}
- (void)disableAfterDrain {
    WKWebView *view = self.view;
    if (!view) return;
    NSData *data = [NSJSONSerialization dataWithJSONObject:@[self.viewID] options:0 error:NULL];
    NSString *identity = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    NSString *script = [NSString stringWithFormat:@"(()=>{const id=%@[0];if(window.logisticsInputTrace&&logisticsInputTrace().view_id===id){if(window.logisticsNativePenReset)logisticsNativePenReset();state.native_pen=false}})()", identity];
    [view evaluateJavaScript:script completionHandler:nil];
}
- (void)drain {
    if (self.pending) return;
    WKWebView *view = self.view;
    if (!view) { [self.packets removeAllObjects]; self.samples = 0; return; }
    if (!self.packets.count) { if (!self.accepting) [self disableAfterDrain]; return; }
    NSArray *packet = self.packets.firstObject;
    [self.packets removeObjectAtIndex:0];
    self.samples -= [packet[2] count];
    NSData *data = [NSJSONSerialization dataWithJSONObject:@[self.viewID, packet] options:0 error:NULL];
    if (!data) { self.accepting = NO; [self.packets removeAllObjects]; self.samples = 0; [self disableAfterDrain]; return; }
    NSString *json = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    NSString *script = [NSString stringWithFormat:@"(()=>{const p=%@;if(window.logisticsInputTrace&&logisticsInputTrace().view_id===p[0]&&typeof logisticsNativePen==='function')logisticsNativePen(...p[1])})()", json];
    self.pending = YES; self.inflightPacket = packet;
    NSUInteger epoch = ++self.epoch;
    [self stopDeadline];
    self.deadlineTimer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, dispatch_get_main_queue());
    dispatch_source_set_timer(self.deadlineTimer, dispatch_time(DISPATCH_TIME_NOW, 3 * NSEC_PER_SEC), DISPATCH_TIME_FOREVER, NSEC_PER_MSEC);
    __weak LogisticsNotebookPencilBinding *weakSelf = self;
    dispatch_source_set_event_handler(self.deadlineTimer, ^{
        LogisticsNotebookPencilBinding *owner = weakSelf;
        if (!owner || !owner.pending || owner.epoch != epoch) return;
        [owner stopDeadline];
        ++owner.epoch; owner.pending = NO; owner.accepting = NO; owner.touch = nil; owner.inflightPacket = nil;
        [owner.packets removeAllObjects]; owner.samples = 0;
        [owner.metrics recordPencilMetric:@"timeout"];
        NSLog(@"Logistics notebook native Pencil delivery timed out");
        [owner disableAfterDrain];
    });
    dispatch_resume(self.deadlineTimer);
    // The block retains only this bounded binding until native WK completion.
    // No Python callback/GIL, source path, coordinates in logs, or persistence.
    [self.metrics recordPencilMetric:@"submitted"];
    [view evaluateJavaScript:script completionHandler:^(id value, NSError *error) {
        if (self.epoch != epoch) return;
        [self stopDeadline];
        [self.metrics recordPencilMetric:@"completed"];
        self.pending = NO; self.inflightPacket = nil;
        if (error) {
            self.accepting = NO; self.touch = nil;
            [self.packets removeAllObjects]; self.samples = 0;
            [self.metrics recordPencilMetric:@"delivery_error"];
            NSLog(@"Logistics notebook native Pencil delivery unavailable");
            [self disableAfterDrain];
            return;
        }
        self.deliveredPacket = ([packet[0] isEqual:@"up"] || [packet[0] isEqual:@"cancel"]) ? nil : packet;
        [self drain];
    }];
}
- (void)append:(NSString *)action points:(NSArray *)points {
    WKWebView *view = self.view;
    CGSize size = view.bounds.size;
    if ([action isEqual:@"cancel"] && (size.width <= 0 || size.height <= 0)) size = self.lastSize;
    if (!view || !points.count || !isfinite(size.width) || !isfinite(size.height) || size.width <= 0 || size.height <= 0) {
        self.accepting = NO; self.touch = nil; [self.packets removeAllObjects]; self.samples = 0; [self disableAfterDrain]; return;
    }
    if (self.packets.count >= LogisticsPencilMaxPackets || self.samples + points.count > LogisticsPencilMaxSamples) {
        // Fail closed at a packet boundary. The in-flight contact gets a terminal
        // cancel, while queued starts that never reached JS are discarded.
        [self.metrics recordPencilMetric:@"overflow"];
        self.accepting = NO; [self cancelUnsubmitted]; return;
    }
    self.lastSize = size;
    [self.packets addObject:@[action, @(self.contact), points, @(size.width), @(size.height)]];
    self.samples += points.count;
    [self drain];
}
- (void)cancel {
    if (self.touch && self.lastPoint) [self append:@"cancel" points:@[self.lastPoint]];
    self.touch = nil;
}
- (void)cancelUnsubmitted {
    // A retired/defocused canvas must not receive starts it never observed.
    // Keep only the terminal cancellation for an actually submitted contact.
    [self.packets removeAllObjects]; self.samples = 0; self.touch = nil;
    NSArray *submitted = self.inflightPacket ?: self.deliveredPacket;
    if (submitted && ![submitted[0] isEqual:@"up"] && ![submitted[0] isEqual:@"cancel"]) {
        NSArray *last = [submitted[2] lastObject];
        [self.packets addObject:@[@"cancel", submitted[1], @[last], submitted[3], submitted[4]]];
        self.samples = 1;
    }
    [self drain];
}
- (void)retire {
    if (self.retired) return;
    [self.metrics recordPencilMetric:@"retired"];
    self.accepting = NO; self.retired = YES; [self cancelUnsubmitted];
}
- (void)capture:(UITouch *)touch event:(UIEvent *)event {
    if (!self.accepting || self.retired || touch.type != UITouchTypePencil) return;
    if (touch.phase == UITouchPhaseBegan) {
        if (self.touch == touch) return;
        [self cancel];
        [self.metrics recordPencilMetric:@"admitted_begin"];
        self.touch = touch; self.contact = self.nextContact++;
        self.lastPoint = [self point:touch];
        if (!self.lastPoint) { [self retire]; return; }
        [self append:@"down" points:@[self.lastPoint]];
        return;
    }
    if (touch != self.touch) return;
    if (touch.phase == UITouchPhaseCancelled) { [self cancel]; return; }
    if (touch.phase != UITouchPhaseMoved && touch.phase != UITouchPhaseEnded) return;
    NSArray<UITouch *> *coalesced = [event coalescedTouchesForTouch:touch];
    if (coalesced.count > LogisticsPencilMaxSamples) { [self retire]; return; }
    NSMutableArray *points = [NSMutableArray array];
    for (UITouch *sample in coalesced) {
        NSArray *point = [self point:sample];
        if (!point) { [self retire]; return; }
        [points addObject:point];
    }
    NSArray *final = [self point:touch];
    if (!final) { [self retire]; return; }
    if (![points.lastObject isEqual:final]) [points addObject:final];
    self.lastPoint = final;
    BOOL ended = touch.phase == UITouchPhaseEnded;
    [self append:ended ? @"up" : @"move" points:points];
    if (ended) self.touch = nil;
}
@end

@interface LogisticsNotebookInputWindow : UIWindow <LogisticsNotebookPencilMetrics>
@property(nonatomic, strong) NSMapTable<WKWebView *, LogisticsNotebookPencilBinding *> *notebookBindings;
@property(nonatomic, strong) NSMutableDictionary<NSString *, NSNumber *> *notebookMetrics;
@property(nonatomic, strong) NSHashTable<UITouch *> *notebookRawContacts;
- (BOOL)bindNotebookWebView:(WKWebView *)view forceMode:(NSInteger)mode viewID:(NSString *)viewID;
- (void)unbindNotebookWebView:(WKWebView *)view;
- (BOOL)notebookWebViewEnabled:(WKWebView *)view;
- (void)captureNotebookTouch:(UITouch *)touch event:(UIEvent *)event;
- (NSDictionary *)notebookPencilSnapshot;
@end

@implementation LogisticsNotebookInputWindow
- (instancetype)initWithFrame:(CGRect)frame {
    if ((self = [super initWithFrame:frame])) {
        _notebookBindings = [NSMapTable weakToStrongObjectsMapTable];
        _notebookMetrics = [NSMutableDictionary dictionary];
        _notebookRawContacts = [NSHashTable weakObjectsHashTable];
        NSNotificationCenter *center = NSNotificationCenter.defaultCenter;
        [center addObserver:self selector:@selector(notebookInactive:) name:UIApplicationWillResignActiveNotification object:nil];
        [center addObserver:self selector:@selector(notebookInactive:) name:UIWindowDidResignKeyNotification object:self];
    }
    return self;
}
- (void)dealloc { [NSNotificationCenter.defaultCenter removeObserver:self]; }
- (BOOL)bindNotebookWebView:(WKWebView *)view forceMode:(NSInteger)mode viewID:(NSString *)viewID {
    if (![NSThread isMainThread] || ![view isKindOfClass:WKWebView.class] || (view.window && view.window != self) ||
        ![viewID isKindOfClass:NSString.class] || (mode != LogisticsPencilConstant && mode != LogisticsPencilEventForce) || viewID.length != 32) return NO;
    if ([viewID rangeOfCharacterFromSet:[[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"] invertedSet]].location != NSNotFound) return NO;
    if ([self.notebookBindings objectForKey:view]) return NO;
    if (self.notebookBindings.count >= 16) return NO;
    LogisticsNotebookPencilBinding *binding = [LogisticsNotebookPencilBinding new];
    binding.view = view; binding.viewID = viewID; binding.forceMode = mode; binding.metrics = self;
    [self.notebookBindings setObject:binding forKey:view];
    return YES;
}
- (BOOL)notebookWebViewEnabled:(WKWebView *)view {
    LogisticsNotebookPencilBinding *binding = [self.notebookBindings objectForKey:view];
    return binding.accepting && !binding.retired && (!view.window || view.window == self);
}
- (void)unbindNotebookWebView:(WKWebView *)view {
    [[self.notebookBindings objectForKey:view] retire];
    [self.notebookBindings removeObjectForKey:view];
}
- (void)notebookInactive:(NSNotification *)notification {
    for (LogisticsNotebookPencilBinding *binding in self.notebookBindings.objectEnumerator) [binding cancelUnsubmitted];
}
- (void)recordPencilMetric:(NSString *)metric {
    static NSSet *allowed;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ allowed = [NSSet setWithArray:@[@"raw_begin", @"raw_move", @"raw_end", @"raw_cancel", @"admitted_begin", @"submitted", @"completed", @"timeout", @"overflow", @"retired", @"delivery_error", @"capture_error"]]; });
    if (![allowed containsObject:metric]) return;
    unsigned long long count = [self.notebookMetrics[metric] unsignedLongLongValue];
    self.notebookMetrics[metric] = @(MIN(count + 1, 9007199254740991ULL));
}
- (NSDictionary *)notebookPencilSnapshot {
    NSUInteger packets = 0, samples = 0, inflight = 0;
    for (LogisticsNotebookPencilBinding *binding in self.notebookBindings.objectEnumerator) {
        packets += binding.packets.count; samples += binding.samples; inflight += binding.pending ? 1 : 0;
    }
    return @{@"native_producer": @YES, @"scope": @"owned-window", @"counts": [self.notebookMetrics copy],
             @"bindings": @(self.notebookBindings.count), @"queued_packets": @(packets),
             @"queued_samples": @(samples), @"inflight": @(inflight)};
}
- (void)captureNotebookTouch:(UITouch *)touch event:(UIEvent *)event {
    if (touch.type != UITouchTypePencil || touch.window != self) return;
    if (touch.phase == UITouchPhaseBegan && ![self.notebookRawContacts containsObject:touch]) {
        if (self.notebookRawContacts.count >= 128) { [self.notebookRawContacts removeAllObjects]; [self recordPencilMetric:@"capture_error"]; }
        [self.notebookRawContacts addObject:touch]; [self recordPencilMetric:@"raw_begin"];
    } else if ((touch.phase == UITouchPhaseEnded || touch.phase == UITouchPhaseCancelled) && [self.notebookRawContacts containsObject:touch]) {
        [self.notebookRawContacts removeObject:touch];
        [self recordPencilMetric:touch.phase == UITouchPhaseEnded ? @"raw_end" : @"raw_cancel"];
    } else if (touch.phase == UITouchPhaseMoved) [self recordPencilMetric:@"raw_move"];
    for (WKWebView *view in self.notebookBindings.keyEnumerator) {
        LogisticsNotebookPencilBinding *binding = [self.notebookBindings objectForKey:view];
        if (binding.touch == touch) { [binding capture:touch event:event]; continue; }
        if (touch.phase != UITouchPhaseBegan || !self.isKeyWindow || view.window != self) continue;
        BOOL visible = YES;
        for (UIView *node = view; node; node = node.superview) if (node.hidden || node.alpha <= 0) { visible = NO; break; }
        if (visible && [touch.view isDescendantOfView:view]) [binding capture:touch event:event];
    }
}
- (void)sendEvent:(UIEvent *)event {
    @try {
        if (event.type == UIEventTypeTouches && self.notebookBindings.count) {
            for (UITouch *touch in event.allTouches) [self captureNotebookTouch:touch event:event];
        }
    } @catch (NSException *error) {
        [self recordPencilMetric:@"capture_error"];
        for (LogisticsNotebookPencilBinding *binding in self.notebookBindings.objectEnumerator) {
            @try { [binding retire]; }
            @catch (NSException *cleanupError) { [self recordPencilMetric:@"capture_error"]; }
        }
        NSLog(@"Logistics notebook native Pencil capture unavailable");
    } @finally {
        [super sendEvent:event]; // Exactly once; no interception of UIKit controls or recognizers.
    }
}
@end
