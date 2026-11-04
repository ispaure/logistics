"""Observe supported iPad Pencil hover without taking over WKWebView touches.

PointerEvents continue to own contact/cancel and work without hover hardware.
The UIKit recognizer is Pencil-only and permits simultaneous native gestures.
"""
import json
import math
from weakref import ref

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
    if not type(web._impl).__module__.startswith('toga_iOS.'):
        return None
    from rubicon.objc import ObjCClass
    if int(ObjCClass('UIDevice').currentDevice.userInterfaceIdiom) != 1:
        return None
    try:
        recognizer = ObjCClass('UIHoverGestureRecognizer')
    except NameError:
        return None
    return PencilHover(web, recognizer)
