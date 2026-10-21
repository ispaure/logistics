"""Reader animation policy over shared platform transitions."""
from commonUtils.ui.native.transitions import (
    page_direction as page_direction, begin_page_slide as begin_slide, finish_page_slide as finish_slide,
)


def cancel_page_slide(content):
    if content is None:
        return
    impl = content._impl
    backend = type(impl).__module__
    if backend.startswith('toga_iOS.'):
        # Core Animation always stores CATransition under kCATransition.
        impl.native.layer.removeAnimationForKey('transition')
    elif backend.startswith('toga_android.'):
        impl.native.clearAnimation()


def cancel_visible_slides(app):
    for manager, field in (('readers', 'book_content'), ('private_sessions', 'crypt_content')):
        owner = getattr(getattr(app, manager, None), 'active', None)
        cancel_page_slide(getattr(owner, field, None))


def begin_page_slide(content, direction, preferences):
    enabled = preferences.get('android_eink') != 'true'
    if not enabled:
        cancel_page_slide(content)
    return begin_slide(content, direction, enabled=enabled)


def finish_page_slide(content, direction, preferences):
    return finish_slide(content, direction, enabled=preferences.get('android_eink') != 'true')
