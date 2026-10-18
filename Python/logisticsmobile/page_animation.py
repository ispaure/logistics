"""Short native page slides, scoped to the reader's content surface."""


def page_direction(previous, current, *, right_to_left=False):
    if previous is None or previous == current:
        return 0
    direction = 1 if current > previous else -1
    return -direction if right_to_left else direction


def begin_page_slide(content, direction, preferences):
    """Capture the outgoing Apple layer before replacing its page children."""
    if not direction or preferences.get('android_eink') == 'true':
        return
    impl = content._impl
    backend = type(impl).__module__
    if backend.startswith('toga_iOS.'):
        from ctypes import CDLL, c_bool
        from rubicon.objc import ObjCClass
        reduced = CDLL(None).UIAccessibilityIsReduceMotionEnabled
        reduced.restype = c_bool
        if reduced():
            return
        animation = ObjCClass('CATransition').animation()
        animation.type = 'push'
        animation.subtype = 'fromRight' if direction > 0 else 'fromLeft'
        animation.duration = .22
        impl.native.layer.addAnimation(animation, forKey='logistics.page')


def finish_page_slide(content, direction, preferences):
    """Slide Android's replacement content in after its children are mounted."""
    if not direction or preferences.get('android_eink') == 'true':
        return
    impl = content._impl
    if type(impl).__module__.startswith('toga_android.'):
        from android.provider import Settings
        from android.view.animation import TranslateAnimation
        # Settings.Global also supports the app's Android 7 / API 24 floor.
        resolver = impl.native.getContext().getContentResolver()
        if Settings.Global.getFloat(resolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1.0) == 0:
            return
        # RELATIVE_TO_SELF follows the reader pane on phones and split layouts.
        animation = TranslateAnimation(1, float(direction), 1, 0.0, 1, 0.0, 1, 0.0)
        animation.setDuration(220)
        impl.native.startAnimation(animation)
