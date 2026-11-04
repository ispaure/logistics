"""Observe supported iPad Pencil hover without taking over WKWebView touches.

PointerEvents continue to own contact/cancel and work without hover hardware.
The UIKit recognizer is Pencil-only and permits simultaneous native gestures.
"""
import json
import math
from weakref import ref
from uuid import uuid4
from commonUtils.ui.native.text_size import native_backend

_hover_target = None


def _target_class():
    from rubicon.objc import ObjCClass, ObjCProtocol, objc_method
    global _hover_target
    if _hover_target is None:
        class LogisticsNotebookPencilHover(ObjCClass('NSObject'), protocols=(ObjCProtocol('UIGestureRecognizerDelegate'),)):
            @objc_method
            def gestureRecognizer_shouldRecognizeSimultaneouslyWithGestureRecognizer_(self, gesture, other) -> bool:
                return True

            @objc_method
            def hover_(self, gesture) -> None:
                owner = self.owner() if self.owner is not None else None
                if owner is not None:
                    owner.hover(gesture)
        _hover_target = LogisticsNotebookPencilHover
    return _hover_target


class PencilHover:
    def __init__(self, web, recognizer_type):
        from rubicon.objc import SEL, ns_from_py
        self.native = web._impl.native
        self.target = _target_class().alloc().init()
        self.target.owner = ref(self)
        self.gesture = recognizer_type.alloc().initWithTarget(self.target, action=SEL('hover:'))
        self.gesture.allowedTouchTypes = ns_from_py([2])  # UITouchTypePencil
        self.gesture.requiresExclusiveTouchType = True
        self.gesture.cancelsTouchesInView = False
        self.gesture.delaysTouchesBegan = False
        self.gesture.delaysTouchesEnded = False
        self.gesture.delegate = self.target
        self.closed = False
        self.native.addGestureRecognizer(self.gesture)

    def emit(self, nearby, x=0., y=0.):
        if self.closed:
            return
        size = self.native.bounds.size
        values = [bool(nearby), float(x), float(y), float(size.width), float(size.height)]
        if not all(math.isfinite(value) for value in values[1:]):
            return
        self.native.evaluateJavaScript('window.logisticsPenProximity&&window.logisticsPenProximity('
            + ','.join(json.dumps(value) for value in values) + ')', completionHandler=None)

    def hover(self, gesture):
        # UIGestureRecognizerState began=1, changed=2; ended/cancelled/failed
        # all release proximity and leave the bounded JS pen-up grace period.
        nearby = int(gesture.state) in (1, 2)
        point = gesture.locationInView(self.native)
        self.emit(nearby, point.x, point.y)

    def close(self):
        if self.closed:
            return
        self.emit(False)
        self.closed = True
        self.native.removeGestureRecognizer(self.gesture)
        self.gesture.delegate = None
        self.target.owner = None


def attach(web):
    """Return an owned hover observer only when UIKit exposes it on an iPad."""
    if not native_backend(web).startswith('toga_iOS.'):
        return None
    from rubicon.objc import ObjCClass
    if int(ObjCClass('UIDevice').currentDevice.userInterfaceIdiom) != 1:
        return None
    try:
        recognizer = ObjCClass('UIHoverGestureRecognizer')
    except NameError:
        return None
    return PencilHover(web, recognizer)


_contact_trace_class = None


def _contact_class():
    """A passive recognizer observes UIKit delivery before WK sees the contact."""
    from rubicon.objc import ObjCClass, objc_method, objc_property, send_super, objc_id
    global _contact_trace_class
    if _contact_trace_class is None:
        class LogisticsNotebookPencilTrace(ObjCClass('UIGestureRecognizer')):
            # Rubicon's weak Python-property setter cannot accept None. Retain
            # only a Python weakref in an ordinary property, so close can clear it.
            trace_owner = objc_property(object)

            @objc_method
            def canPreventGestureRecognizer_(self, other) -> bool:
                return False

            @objc_method
            def canBePreventedByGestureRecognizer_(self, other) -> bool:
                return False

            @objc_method
            def touchesBegan_withEvent_(self, touches, event) -> None:
                owner_ref = self.trace_owner
                owner = owner_ref() if owner_ref is not None else None
                if owner is not None:
                    owner.record('begin', int(touches.count))
                send_super(__class__, self, 'touchesBegan:withEvent:', touches, event,
                           restype=None, argtypes=[objc_id, objc_id])

            @objc_method
            def touchesEnded_withEvent_(self, touches, event) -> None:
                owner_ref = self.trace_owner
                owner = owner_ref() if owner_ref is not None else None
                if owner is not None:
                    owner.record('end', int(touches.count))
                send_super(__class__, self, 'touchesEnded:withEvent:', touches, event,
                           restype=None, argtypes=[objc_id, objc_id])
                self.state = 5  # Failed: observe only, never recognize/intercept ink.

            @objc_method
            def touchesCancelled_withEvent_(self, touches, event) -> None:
                owner_ref = self.trace_owner
                owner = owner_ref() if owner_ref is not None else None
                if owner is not None:
                    owner.record('cancel', int(touches.count))
                send_super(__class__, self, 'touchesCancelled:withEvent:', touches, event,
                           restype=None, argtypes=[objc_id, objc_id])
                self.state = 5
        _contact_trace_class = LogisticsNotebookPencilTrace
    return _contact_trace_class


class PencilInputTrace:
    """Native/DOM paired counters, rate limited into the ordinary process log."""
    def __init__(self, web, loop, output):
        from rubicon.objc import ns_from_py
        import time
        self.web, self.native, self.loop = web, web._impl.native, loop
        self.output = output
        self.observer_id = uuid4().hex
        self.dom = self.dom_native_counts = None
        self.clock = time.monotonic
        self.counts, self.recent = {}, []
        self.closed, self.pending, self.timer = False, None, None
        self.dirty = False
        self.query = None
        self.last_report = float('-inf')
        self.gesture = None
        try:
            self.gesture = _contact_class().alloc().initWithTarget(None, action=None)
            self.gesture.trace_owner = ref(self)
            self.gesture.allowedTouchTypes = ns_from_py([2])
            self.gesture.cancelsTouchesInView = False
            self.gesture.delaysTouchesBegan = False
            self.gesture.delaysTouchesEnded = False
            self.native.addGestureRecognizer(self.gesture)
        except Exception:
            # addGestureRecognizer may attach and then fail. Retire only this
            # observer, including work a synchronous callback may have scheduled.
            self.closed = True
            for handle in (self.timer,self.pending):
                if handle is not None:
                    try:
                        handle.cancel()
                    except Exception:
                        pass
            if self.gesture is not None:
                try:
                    self.gesture.trace_owner = None
                except Exception:
                    pass
                try:
                    self.native.removeGestureRecognizer(self.gesture)
                except Exception:
                    pass
            self.timer = self.pending = self.web = self.native = None
            raise

    def record(self, kind, count):
        if self.closed:
            return
        try:
            count = max(0, min(8, int(count)))
            self.counts[kind] = self.counts.get(kind, 0) + count
            self.recent.append(dict(kind=kind,count=count))
            self.recent = self.recent[-24:]
            self.dirty = True
            now = self.clock()
            if self.pending is None and now-self.last_report >= 3:
                self.flush()
            if self.timer is None:
                self.timer = self.loop.call_later(3,self.flush)
        except Exception:
            pass  # Diagnostic observers cannot replace native input dispatch.

    def flush(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
        if self.closed or not self.dirty:
            return
        try:
            self.dirty = False
            self.last_report = self.clock()
            print('LOGISTICS_NOTEBOOK_NATIVE_INPUT='+json.dumps(self.snapshot()),flush=True)
            self.loop.call_soon(self.write_report)
            if self.pending is None and (self.query is None or self.query.done()):
                self.pending = self.loop.create_task(self.report())
        except Exception:
            pass

    def write_report(self):
        try:
            from commonUtils.persistence import atomic_write_json
            value = dict(schema=1,diagnostic_only=True,native=self.snapshot(),dom=self.dom,
                         native_at_dom_query=self.dom_native_counts,
                         pair_stable=self.dom_native_counts is not None and self.dom_native_counts==self.counts,
                         closed=self.closed)
            if len(json.dumps(value).encode('utf-8')) <= 16384:
                atomic_write_json(self.output,value)
        except Exception:
            pass

    def snapshot(self):
        return dict(observer_id=self.observer_id,counts=dict(self.counts),recent=list(self.recent),diagnostic_only=True)

    async def report(self):
        import asyncio
        query = None
        try:
            if self.closed:
                return
            native_at_query = dict(self.counts)
            query = self.query = asyncio.ensure_future(self.web.evaluate_javascript(
                'JSON.stringify(window.logisticsInputTrace?window.logisticsInputTrace():null)'))
            done, _ = await asyncio.wait((query,),timeout=2)
            if done and not self.closed:
                self.dom = _safe_dom_trace(json.loads(query.result()))
                self.dom_native_counts = native_at_query
                self.write_report()
                print('LOGISTICS_NOTEBOOK_INPUT='+json.dumps(dict(native=self.snapshot(),dom=self.dom)),flush=True)
        except Exception:
            pass
        finally:
            if query is not None and not query.done():
                # Native completion may still arrive: consume it without cancelling
                # Toga's JavaScriptResult or retaining this observer in a callback.
                query.add_done_callback(_consume_trace_result)
            if self.pending is asyncio.current_task():
                self.pending = None

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
        try:
            print('LOGISTICS_NOTEBOOK_NATIVE_INPUT_FINAL='+json.dumps(self.snapshot()),flush=True)
        except Exception:
            pass
        self.write_report()
        self.gesture.trace_owner = None
        self.native.removeGestureRecognizer(self.gesture)
        if self.pending is not None:
            self.pending.cancel()
            self.pending = None
        self.web = self.native = self.query = None


def _consume_trace_result(future):
    try:
        future.result()
    except BaseException:
        pass


def attach_diagnostics(web, loop, output):
    try:
        from commonUtils.ui.native.text_size import native_backend
        if not native_backend(web).startswith('toga_iOS.'):
            return None
        return PencilInputTrace(web,loop,output)
    except Exception:
        # Observation is optional. Never block a notebook or serialize an
        # exception string that could contain document/provider information.
        unavailable = dict(schema=1,diagnostic_only=True,available=False,
                           reason='native-observer-unavailable')
        try:
            from commonUtils.persistence import atomic_write_json
            atomic_write_json(output,unavailable)
        except Exception:
            pass
        try:
            print('LOGISTICS_NOTEBOOK_INPUT_UNAVAILABLE='+json.dumps(unavailable),flush=True)
        except Exception:
            pass
        return None


def _safe_dom_trace(value):
    """Only fixed diagnostic fields may enter the ordinary support receipt."""
    if not isinstance(value,dict):
        return None
    kinds = {'delivered-pointerdown','delivered-pointerup','delivered-pointercancel',
             'delivered-lostpointercapture','reject-palm','reject-native-duplicate',
             'reject-active','reject-locked-or-busy','accepted-down','cancelled-contact',
             'completed-contact','stroke-ack-deferred','stroke-ack-applied'}
    types = {'pen','touch','mouse','host'}
    keys = {kind+':'+pointer for kind in kinds for pointer in types}
    counts = {key:min(1000000,max(0,count)) for key,count in value.get('counts',{}).items()
              if key in keys and type(count) is int}
    recent = []
    for row in value.get('recent',[])[-24:]:
        if not isinstance(row,dict) or row.get('kind') not in kinds or row.get('type') not in types:
            continue
        recent.append(dict(kind=row['kind'],type=row['type'],
                           **{key:row.get(key) is True for key in ('trusted','active','busy','ink')},
                           queued=min(64,max(0,row['queued'])) if type(row.get('queued')) is int else 0))
    token = value.get('view_id')
    token = token if (isinstance(token,str) and len(token)==32
                      and all(character in '0123456789abcdef' for character in token)) else None
    return dict(view_id=token,counts=counts,recent=recent)
