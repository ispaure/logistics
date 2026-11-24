"""Subtle native feedback for custom mobile controls."""


def feedback(widget, *, confirmed=False):
    impl = getattr(widget, '_impl', None)
    backend = type(impl).__module__
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        if confirmed:
            ObjCClass('UINotificationFeedbackGenerator').alloc().init().notificationOccurred(0)
        else:
            ObjCClass('UISelectionFeedbackGenerator').alloc().init().selectionChanged()
    elif backend.startswith('toga_android.'):
        from android.os import Build
        from android.view import HapticFeedbackConstants

        view = getattr(impl, 'native', None)
        if not hasattr(view, 'performHapticFeedback'):
            view = widget.app._impl.native.getWindow().getDecorView()
        effect = HapticFeedbackConstants.CLOCK_TICK
        if confirmed:
            effect = (HapticFeedbackConstants.CONFIRM if Build.VERSION.SDK_INT >= 30
                      else HapticFeedbackConstants.VIRTUAL_KEY)
        view.performHapticFeedback(effect)
