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
    if not enabled or not direction:
        cancel_page_slide(content)
    return begin_slide(content, direction, enabled=enabled)


def finish_page_slide(content, direction, preferences):
    return finish_slide(content, direction, enabled=preferences.get('android_eink') != 'true')


def sync_preferences(app):
    """Push the host policy into retained rich EPUBs on either mobile backend."""
    preferences = getattr(app, 'preferences', None)
    if preferences is None:
        return
    enabled = preferences.values.get('android_eink') != 'true'
    for name in ('readers', 'private_sessions'):
        manager = getattr(app, name, None)
        for owner in getattr(manager, 'controllers', {}).values():
            panel = getattr(owner, 'provider_epub_view', None)
            view = getattr(owner, 'epub_view', None) or getattr(panel, 'webview', None)
            bridge = getattr(view, '_chapter_bridge', None)
            if bridge is not None:
                bridge.set_motion_enabled(enabled)
    if not enabled:
        cancel_visible_slides(app)
