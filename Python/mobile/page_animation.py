"""Reader animation policy, with an explicit visible iOS outgoing page."""
from commonUtils.ui.native.transitions import (
    page_direction as page_direction, finish_page_slide as finish_slide,
)


def cancel_page_slide(content):
    if content is None:
        return
    impl = content._impl
    backend = type(impl).__module__
    if backend.startswith('toga_iOS.'):
        state = getattr(impl, '_ios_page_slide', None)
        impl._ios_page_slide = None
        if state is not None:
            if state.snapshot is not None:
                state.snapshot.layer.removeAllAnimations()
                state.snapshot.image = None
                state.snapshot.removeFromSuperview()
                state.snapshot = None  # Release captured private pixels now.
            wrapper = getattr(state, 'wrapper', None)
            if wrapper is not None:
                wrapper.removeFromSuperview()
                state.wrapper = None
            state.blocks = ()
        impl.native.layer.removeAnimationForKey('transition')
    elif backend.startswith('toga_android.'):
        impl.native.clearAnimation()


def cancel_visible_slides(app):
    for manager, field in (('readers', 'book_content'), ('private_sessions', 'crypt_content')):
        owner = getattr(getattr(app, manager, None), 'active', None)
        cancel_page_slide(getattr(owner, field, None))


def begin_page_slide(content, direction, preferences):
    if preferences.get('android_eink') == 'true':
        cancel_page_slide(content)
        return
    impl = content._impl
    if not direction:
        # Preserve same-page repaints; a real viewport change cancels motion.
        state = getattr(impl, '_ios_page_slide', None) if type(impl).__module__.startswith('toga_iOS.') else None
        if state is not None:
            rect = impl.native.convertRect(impl.native.bounds, toView=state.root)
            current = (float(rect.origin.x), float(rect.origin.y), float(rect.size.width), float(rect.size.height))
            if any(abs(old - new) > 1 for old, new in zip(state.geometry, current)):
                cancel_page_slide(content)
        return
    cancel_page_slide(content)
    if type(impl).__module__.startswith('toga_iOS.'):
        from ctypes import CDLL, c_bool
        from types import SimpleNamespace
        reduced = CDLL(None).UIAccessibilityIsReduceMotionEnabled
        reduced.restype = c_bool
        if reduced() or impl.native.window is None:
            return
        # Toga iOS flattens widget views into one ControlledContainer: a Box
        # does not own its image/text siblings. Capture its rectangle from that
        # real hierarchy, and later overlay it above the destination siblings.
        from rubicon.objc import ObjCClass, Block, objc_id, CGRect
        native, root = impl.native, impl.container.native
        rect = native.convertRect(native.bounds, toView=root)
        width, height = float(rect.size.width), float(rect.size.height)
        if min(width, height) <= 0:
            return
        def image_canvases(widget):
            if getattr(widget, 'image', None) is not None and hasattr(widget._impl, 'picture'):
                yield widget
            for child in widget.children:
                yield from image_canvases(child)
        canvases = list(image_canvases(content))
        renderer = ObjCClass('UIGraphicsImageRenderer').alloc().initWithSize(rect.size)
        def draw(context):
            from .appearance import apple_color
            apple_color('window').setFill()
            ObjCClass('UIBezierPath').bezierPathWithRect(CGRect((0, 0), (width, height))).fill()
            if len(canvases) == 1:
                canvas = canvases[0]._impl
                viewport = canvas.native.convertRect(canvas.native.bounds, toView=root)
                clip = CGRect((float(viewport.origin.x - rect.origin.x), float(viewport.origin.y - rect.origin.y)),
                              (float(viewport.size.width), float(viewport.size.height)))
                ObjCClass('UIBezierPath').bezierPathWithRect(clip).addClip()
                picture = canvas.picture.convertRect(canvas.picture.bounds, toView=root)
                canvas.picture.image.drawInRect(CGRect(
                    (float(picture.origin.x - rect.origin.x), float(picture.origin.y - rect.origin.y)),
                    (float(picture.size.width), float(picture.size.height))))
            else:
                window = native.window
                window_rect = native.convertRect(native.bounds, toView=window)
                window.drawViewHierarchyInRect(CGRect((-float(window_rect.origin.x), -float(window_rect.origin.y)),
                    (float(window.bounds.size.width), float(window.bounds.size.height))), afterScreenUpdates=True)
        image = renderer.imageWithActions(Block(draw, None, objc_id))
        snapshot = ObjCClass('UIImageView').alloc().initWithImage(image)
        snapshot.opaque = False
        snapshot.userInteractionEnabled = False
        snapshot.accessibilityElementsHidden = True
        impl._ios_page_slide = SimpleNamespace(snapshot=snapshot, root=root,
            geometry=(float(rect.origin.x), float(rect.origin.y), width, height), wrapper=None, blocks=())


def finish_page_slide(content, direction, preferences):
    impl = content._impl
    if not type(impl).__module__.startswith('toga_iOS.'):
        return finish_slide(content, direction, enabled=preferences.get('android_eink') != 'true')
    state = getattr(impl, '_ios_page_slide', None)
    if state is None:
        return
    if preferences.get('android_eink') == 'true':
        cancel_page_slide(content)
        return
    if not direction:
        if state.wrapper is not None:
            state.root.bringSubviewToFront(state.wrapper)
        return
    from rubicon.objc import ObjCClass, Block, CGRect
    native, snapshot = impl.native, state.snapshot
    width, height = float(native.bounds.size.width), float(native.bounds.size.height)
    if min(width, height) <= 0:
        cancel_page_slide(content)
        return
    rect = native.convertRect(native.bounds, toView=state.root)
    wrapper = state.wrapper = ObjCClass('UIView').alloc().init()
    wrapper.userInteractionEnabled = False
    wrapper.accessibilityElementsHidden = True
    wrapper.clipsToBounds = True
    wrapper.frame = rect
    snapshot.frame = CGRect((0, 0), (width, height))
    wrapper.addSubview(snapshot)
    state.root.addSubview(wrapper)
    def complete():
        if getattr(impl, '_ios_page_slide', None) is state:
            cancel_page_slide(content)
    completion = Block(complete, None)
    state.blocks = (completion,)
    transaction = ObjCClass('CATransaction')
    transaction.begin()
    transaction.setDisableActions(True)
    transaction.setCompletionBlock(completion)
    displacement = (-1 if direction > 0 else 1) * width
    snapshot.frame = CGRect((displacement, 0), (width, height))
    animation = ObjCClass('CABasicAnimation').animationWithKeyPath('position.x')
    animation.fromValue = width / 2
    animation.toValue = width / 2 + displacement
    animation.duration = .22
    animation.timingFunction = ObjCClass('CAMediaTimingFunction').functionWithName('easeOut')
    snapshot.layer.addAnimation(animation, forKey='logistics.page.slide')
    transaction.commit()


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
            drawer = getattr(owner, 'chapter_sidebar', None) or getattr(panel, 'sidebar', None)
            if not enabled and hasattr(drawer, 'cancel_motion'):
                drawer.cancel_motion()
            view = getattr(owner, 'epub_view', None) or getattr(panel, 'webview', None)
            bridge = getattr(view, '_chapter_bridge', None)
            if bridge is not None:
                bridge.set_motion_enabled(enabled)
    if not enabled:
        cancel_visible_slides(app)
