"""Native motion for Notes drawers and the persistent Files pane."""


def resize_panes(view, apply):
    impl = view._impl
    if type(impl).__module__.startswith('toga_iOS.') and impl.native.window is not None:
        from ctypes import CDLL, c_bool
        reduced = CDLL(None).UIAccessibilityIsReduceMotionEnabled
        reduced.restype = c_bool
        if not reduced():
            from rubicon.objc import Block, ObjCClass
            # Toga attaches pane constraints to the shared native container.
            container = impl.container.native
            container.layoutIfNeeded()

            def layout():
                apply()
                container.layoutIfNeeded()

            # Match Workspaces and retarget from the current presentation.
            ObjCClass('UIView').animateWithDuration(.28, delay=0, options=(1 << 2) | (1 << 1),
                animations=Block(layout, None), completion=None)
            return
    apply()


def slide_out(overlay, direction, app):
    if overlay.container is None and overlay.popup is None:
        return 0
    if app.preferences.values.get('android_eink') == 'true':
        return 0
    backend = type(overlay.panel._impl).__module__
    duration = .22
    if backend.startswith('toga_iOS.'):
        from ctypes import CDLL, c_bool
        from rubicon.objc import ObjCClass
        reduced = CDLL(None).UIAccessibilityIsReduceMotionEnabled
        reduced.restype = c_bool
        if reduced():
            return 0
        native = overlay.container.native
        animation = ObjCClass('CABasicAnimation').animationWithKeyPath('transform.translation.x')
        animation.fromValue = 0
        animation.toValue = direction * (float(native.bounds.size.width) + 24)
        animation.duration = duration
        animation.fillMode = 'forwards'
        animation.removedOnCompletion = False
        animation.timingFunction = ObjCClass('CAMediaTimingFunction').functionWithName('easeIn')
        native.layer.removeAnimationForKey('commonutils.page')
        native.layer.addAnimation(animation, forKey='logistics.drawer.exit')
        return duration
    if backend.startswith('toga_android.'):
        from android.provider import Settings
        from android.view.animation import TranslateAnimation
        native = overlay.popup.getContentView()
        if Settings.Global.getFloat(native.getContext().getContentResolver(), Settings.Global.ANIMATOR_DURATION_SCALE, 1.0) == 0:
            return 0
        animation = TranslateAnimation(1, 0.0, 1, float(direction), 1, 0.0, 1, 0.0)
        animation.setDuration(round(duration * 1000))
        animation.setFillAfter(True)
        native.startAnimation(animation)
        return duration
    return 0
