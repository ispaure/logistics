"""Observe Notes article and drawer swipes alongside native child controls."""
from weakref import ref

_apple_target = None
_swipe_class = None


def opening_swipes_allowed(owner):
    """Embedded editors can own horizontal gestures while pane buttons stay active."""
    enabled = getattr(owner, 'opening_swipes_enabled', None)
    return enabled is None or bool(enabled())


def install_opening_swipes(owner):
    backend = type(owner.detail._impl).__module__
    if owner.opening_gestures:
        return
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass, ObjCProtocol, SEL, objc_method
        from commonUtils.ui.native.keyboard import native_value
        global _apple_target
        if _apple_target is None:
            class LogisticsNotesOpeningSwipe(ObjCClass('NSObject'), protocols=(ObjCProtocol('UIGestureRecognizerDelegate'),)):
                @objc_method
                def gestureRecognizer_shouldRecognizeSimultaneouslyWithGestureRecognizer_(self, gesture, other) -> bool:
                    return True

                @objc_method
                def gestureRecognizer_shouldReceiveTouch_(self, gesture, touch) -> bool:
                    current = self.owner()
                    if current is None or current.side is not None or current.retiring or not opening_swipes_allowed(current):
                        return False
                    article = current.detail._impl.native
                    if native_value(article.window) is None or article.hidden:
                        return False
                    point = touch.locationInView(article)
                    size = article.bounds.size
                    if not (0 <= point.x < size.width and 0 <= point.y < size.height):
                        return False
                    # UIKit can report an ancestor as the touch view. Hit-test
                    # the retained scroll surfaces before walking that ancestry.
                    for name in ('breadcrumb_scroll', 'document_web'):
                        surface = getattr(current, name, None)
                        if surface is None or surface.parent is None:
                            continue
                        viewport = surface._impl.native
                        if native_value(viewport.window) is not None and not viewport.hidden:
                            if viewport.pointInside(touch.locationInView(viewport), withEvent=None):
                                return False
                    view = native_value(touch.view)
                    while view is not None:
                        # HTML owns document swipes so nested table scrolling,
                        # text selection and zoom are resolved in the DOM.
                        if view.isKindOfClass(ObjCClass('WKWebView')):
                            return False
                        if view.respondsToSelector(SEL('selectedTextRange')):
                            selection = native_value(view.selectedTextRange)
                            if selection is not None and view.offsetFromPosition(selection.start, toPosition=selection.end):
                                return False
                        if view.isKindOfClass(ObjCClass('UIControl')) or view.isKindOfClass(ObjCClass('UITextView')):
                            return False
                        if view.isKindOfClass(ObjCClass('UIScrollView')):
                            if (float(view.contentSize.width) > float(view.bounds.size.width) + 2
                                    or float(view.zoomScale) > float(view.minimumZoomScale) + .01):
                                return False
                        view = native_value(view.superview)
                    return True

                @objc_method
                def swipe_(self, gesture) -> None:
                    current = self.owner()
                    if current is not None:
                        current.open_swipe(1 if int(gesture.direction) == 1 else -1)
            _apple_target = LogisticsNotesOpeningSwipe
        target = _apple_target.alloc().init()
        target.owner = ref(owner)
        window = owner.host.window()
        strip = getattr(owner, 'breadcrumb_scroll', None)
        for direction in (1, 2):
            gesture = ObjCClass('UISwipeGestureRecognizer').alloc().initWithTarget(target, action=SEL('swipe:'))
            gesture.direction = direction
            gesture.delegate = target
            gesture.cancelsTouchesInView = False
            if strip is not None:
                # UIKit can allow both simultaneous recognizers to succeed on
                # the Duo display. The strip's pan must win this competition.
                gesture.requireGestureRecognizerToFail(strip._impl.native.panGestureRecognizer)
            window.addGestureRecognizer(gesture)
            owner.opening_gestures.append((window, gesture, target))
    elif backend.startswith('toga_android.'):
        from android.view import View
        from java import dynamic_proxy
        reference = ref(owner)
        surface = getattr(owner, 'opening_surface', owner.detail)._impl
        # Toga nests a disabled horizontal ScrollView inside the vertical one.
        # Its listener consumes touches even when horizontal scrolling is off.
        native = getattr(surface, 'hScrollView', surface.native)
        previous_touch = getattr(surface, 'hScrollListener', None)
        class Touch(dynamic_proxy(View.OnTouchListener)):
            start = None
            def onTouch(self, view, event):
                current = reference()
                if current is None or current.side is not None or current.retiring or not opening_swipes_allowed(current):
                    self.start = None
                    return self.forward(view, event)
                action = event.getActionMasked()
                if action == 0:
                    self.start = (event.getRawX(), event.getRawY(), event.getEventTime())
                elif action == 2 and self.start is not None:
                    dx, dy = event.getRawX() - self.start[0], event.getRawY() - self.start[1]
                    if abs(dy) > 10 * view.getContext().getResources().getDisplayMetrics().density and abs(dx) < 2 * abs(dy):
                        self.start = None
                elif action == 1 and self.start is not None:
                    x, y, started = self.start
                    self.start = None
                    dx, dy = event.getRawX() - x, event.getRawY() - y
                    density = view.getContext().getResources().getDisplayMetrics().density
                    if abs(dx) > 60 * density and abs(dx) > 2 * abs(dy) and event.getEventTime() - started < 800:
                        if current.open_swipe(1 if dx > 0 else -1):
                            return True
                elif action in (3, 5):
                    self.start = None
                return self.forward(view, event)

            def forward(self, view, event):
                return bool(previous_touch.onTouch(view, event)) if previous_touch is not None else False
        native.setClickable(True)
        listener = Touch()
        listener.previous_touch = previous_touch
        native.setOnTouchListener(listener)
        owner.opening_gestures.append((native, None, listener))


def clear_opening_swipes(owner):
    for native, gesture, target in owner.opening_gestures:
        if gesture is not None:
            native.removeGestureRecognizer(gesture)
            gesture.delegate = None
        else:
            native.setOnTouchListener(getattr(target, 'previous_touch', None))
    owner.opening_gestures.clear()


def install_dismiss_swipe(owner, panel):
    backend = type(panel._impl).__module__
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass, ObjCProtocol, SEL, objc_method
        # An overlay owns its recognizer target; release both on dismissal.
        global _swipe_class
        if _swipe_class is None:
            class LogisticsNotesDrawerSwipe(ObjCClass('NSObject'), protocols=(ObjCProtocol('UIGestureRecognizerDelegate'),)):
                @objc_method
                def gestureRecognizer_shouldRecognizeSimultaneouslyWithGestureRecognizer_(self, gesture, other) -> bool:
                    return True

                @objc_method
                def swipe_(self, gesture) -> None:
                    if self.owner is not None:
                        self.owner.swipe(1 if int(gesture.direction) == 1 else -1)
            _swipe_class = LogisticsNotesDrawerSwipe
        target = _swipe_class.alloc().init()
        target.owner = owner
        native = owner.overlay.container.native
        gesture = ObjCClass('UISwipeGestureRecognizer').alloc().initWithTarget(target, action=SEL('swipe:'))
        gesture.direction = 2 if owner.side == 'files' else 1
        gesture.delegate = target
        native.addGestureRecognizer(gesture)
        owner.gestures.append((native, gesture, target))
    elif backend.startswith('toga_android.'):
        from android.view import View
        from java import dynamic_proxy
        class Touch(dynamic_proxy(View.OnTouchListener)):
            start = None
            def onTouch(self, view, event):
                action = event.getActionMasked()
                if action == 0:
                    self.start = (event.getRawX(), event.getRawY(), event.getEventTime())
                elif action == 2 and self.start is not None:
                    x, y, _ = self.start
                    dx, dy = event.getRawX() - x, event.getRawY() - y
                    density = view.getContext().getResources().getDisplayMetrics().density
                    if abs(dy) > 10 * density and abs(dx) < 2 * abs(dy):
                        self.start = None
                elif action == 1 and self.start is not None:
                    x, y, started = self.start
                    self.start = None
                    dx, dy = event.getRawX() - x, event.getRawY() - y
                    density = view.getContext().getResources().getDisplayMetrics().density
                    if abs(dx) > 60 * density and abs(dx) > 2 * abs(dy) and event.getEventTime() - started < 800:
                        return owner.swipe(1 if dx > 0 else -1)
                elif action in (3, 5):
                    self.start = None
                return False
        # PopupWindow observes the complete stream before child controls
        # consume it. Per-widget listeners miss scrolls and native children.
        popup = owner.overlay.popup
        listener = Touch()
        popup.setTouchInterceptor(listener)
        owner.gestures.append((popup, None, listener))


def clear_dismiss_swipes(owner):
    for native, gesture, target in owner.gestures:
        if gesture is not None:
            native.removeGestureRecognizer(gesture)
            gesture.delegate = None
            target.owner = None
        else:
            native.setTouchInterceptor(None)
    owner.gestures.clear()
