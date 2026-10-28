"""Decorative side-bar artwork, independent of safe foreground layout.

The extension owns an image-only view, never the real canvas or a snapshot of
text/controls. Routes, privacy shields and fullscreen remove its pixel reference.
"""
from dataclasses import dataclass
import weakref


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self):
        return self.x + self.width


def extension_rect(canvas, bounds, *, edge, safe_left, safe_right):
    """Only the canvas adjacent to the bar can extend toward the outer edge."""
    if canvas.width <= 0 or canvas.height <= 0 or canvas.y < bounds.y - 1:
        return None
    if canvas.y + canvas.height > bounds.y + bounds.height + 1:
        return None
    if edge == 2 and safe_right > 0 and canvas.right >= bounds.right - safe_right - 24:
        return Rect(canvas.x, canvas.y, bounds.right - canvas.x, canvas.height)
    if edge == 1 and safe_left > 0 and canvas.x <= bounds.x + safe_left + 24:
        return Rect(bounds.x, canvas.y, canvas.right - bounds.x, canvas.height)
    return None


def candidates(widget, *, reading=False):
    """Only canvases inside a declared reading frame supply artwork."""
    reading = reading or getattr(widget, '_reading_frame', False)
    if reading and hasattr(widget._impl, 'picture') and getattr(widget, 'image', None) is not None:
        yield widget
    for child in widget.children:
        yield from candidates(child, reading=reading)


def clear(app):
    state = getattr(app, '_ios_artwork_extension', None)
    if state is not None:
        # Remove the native image before detaching: private bytes must not be
        # held by a decorative sibling after its source session is suspended.
        state.picture.image = None
        state.native.removeFromSuperview()
        app._ios_artwork_extension = None


def reduce_transparency():
    from ctypes import CDLL, c_bool
    function = CDLL(None).UIAccessibilityIsReduceTransparencyEnabled
    function.restype = c_bool
    return bool(function())


def preview_edge(app, container):
    """Only a standalone photo may use the bar strip as real canvas space."""
    if not hasattr(app, 'routes') or not app.body.children:
        return 0
    view = app.body.children[0]
    if not getattr(view, '_image_preview_surface', False) or view._impl.container is not container:
        return 0
    privacy = getattr(app, 'screen_privacy', None)
    if (getattr(app, '_hinge_status', 0) == 2 or reduce_transparency() or
            (privacy is not None and (privacy.inactive or
             getattr(privacy, 'resume_locked', False) or
             getattr(privacy, 'shield', None) is not None))):
        return 0
    from .ios_toolbar import vertical_edge
    index = app.native_host.destinations.index(app.native_host.state.destination)
    return vertical_edge(app.native_host.adapter.content_controller(app.native_host.destinations[index]))


def expand_preview(container):
    if container.content is None:
        return False
    app = container.content.interface.app
    if app is None:
        return False
    edge = preview_edge(app, container)
    changed = False
    if edge == 1 and container.left_inset:
        container.left_inset, changed = 0, True
    elif edge == 2 and container.right_inset:
        container.right_inset, changed = 0, True
    return changed


def sync(app, *, settled=False):
    if not type(getattr(app, '_impl', None)).__module__.startswith('toga_iOS.'):
        return
    # Reader/footer safe margins can settle later in the same render pass.
    # Re-measure once after that pass; never poll or keep an image snapshot.
    if not settled and getattr(app, 'loop', None) is not None and not getattr(app, '_artwork_sync_pending', False):
        app._artwork_sync_pending = True
        def refresh():
            app._artwork_sync_pending = False
            sync(app, settled=True)
        app.loop.call_soon(refresh)
    adapter = app.native_host.adapter
    privacy = getattr(app, 'screen_privacy', None)
    if (adapter is None or not hasattr(adapter, 'navigation') or
            getattr(app, '_reader_chrome_hidden', False) or
            (privacy is not None and (privacy.inactive or
                getattr(privacy, 'resume_locked', False) or
                getattr(privacy, 'shield', None) is not None)) or reduce_transparency()):
        clear(app)
        return
    from .ios_toolbar import vertical_edge
    controller = adapter.content_controller(app.native_host.state.destination)
    edge = vertical_edge(controller)
    if edge not in (1, 2) or not app.body.children:
        clear(app)
        return
    view = app.body.children[0]
    container = view._impl.container
    if container is None:
        clear(app)
        return
    root = container.native
    bounds, safe = root.bounds, root.safeAreaInsets
    area = Rect(float(bounds.origin.x), float(bounds.origin.y), float(bounds.size.width), float(bounds.size.height))
    if preview_edge(app, container) in (1, 2):
        clear(app)
        return
    found = None
    for canvas in candidates(view):
        native = canvas._impl.native
        if native.window is None or native.isHidden():
            continue
        frame = native.convertRect(native.bounds, toView=root)
        rect = Rect(float(frame.origin.x), float(frame.origin.y), float(frame.size.width), float(frame.size.height))
        extended = extension_rect(rect, area, edge=edge, safe_left=float(safe.left), safe_right=float(safe.right))
        if extended is not None:
            found = canvas, rect, extended
    if found is None:
        clear(app)
        return
    from rubicon.objc import ObjCClass, CGRect
    canvas, rect, extended = found
    state = getattr(app, '_ios_artwork_extension', None)
    if state is None or state.root != root or state.owner() is not canvas:
        clear(app)
        try:
            extension_class = ObjCClass('UIBackgroundExtensionView')
        except NameError:
            return
        from types import SimpleNamespace
        native = extension_class.alloc().init()
        native.automaticallyPlacesContentView = False
        native.userInteractionEnabled = False
        native.accessibilityElementsHidden = True
        native.clipsToBounds = True
        picture = ObjCClass('UIImageView').alloc().init()
        picture.contentMode = 1  # Aspect fit; only UIKit's extension is decorative.
        picture.userInteractionEnabled = False
        native.contentView = picture
        root.insertSubview(native, atIndex=0)
        state = app._ios_artwork_extension = SimpleNamespace(
            root=root, native=native, picture=picture, owner=weakref.ref(canvas))
    state.picture.image = canvas._impl.picture.image
    state.native.frame = CGRect((extended.x, extended.y), (extended.width, extended.height))
    state.picture.frame = CGRect((rect.x - extended.x, rect.y - extended.y), (rect.width, rect.height))
    state.native.setNeedsLayout()
