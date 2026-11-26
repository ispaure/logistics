"""Keep browser clearance inside scrolling content, below its final row."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"


BOTTOM_GAP = 12


def fill_bottom(view, *scrolls):
    """Declare a page whose bottom edge belongs entirely to scrolling lists."""
    backend = type(view._impl).__module__
    for previous in getattr(view, '_bottom_scrolls', ()):
        if previous not in scrolls:
            _pad_bottom(previous, BOTTOM_GAP, backend)
    view._bottom_scrolls = scrolls
    view.style.margin_bottom = 0
    sync_bottom(view)
    return view


def refresh_scroll_panel(panel):
    """Let the route's bottommost vertical scrollers own its bottom edge."""
    if not getattr(panel, '_route_scroll_panel', False):
        return False
    import toga
    from toga.style.pack import COLUMN, NONE

    def scrolls_at_bottom(view):
        # Explicit browser, drawer and reader layout keeps its own geometry.
        if (view is not panel and getattr(view, '_bottom_scrolls', ())) or getattr(view, '_reading_frame', False):
            return ()
        if isinstance(view, toga.ScrollContainer):
            return (view,) if view.vertical else ()
        if not isinstance(view, toga.Box):
            return ()
        children = [child for child in view.children if child.style.display != NONE]
        if not children:
            return ()
        if view.style.direction == COLUMN:
            last = children[-1]
            return scrolls_at_bottom(last) if last.style.flex and last.style.height == NONE else ()
        sides = [scrolls_at_bottom(child) if child.style.height == NONE else () for child in children]
        return tuple(scroll for side in sides for scroll in side) if all(sides) else ()

    if not getattr(panel, '_automatic_scroll_edge', False) and getattr(panel, '_bottom_scrolls', ()):
        return True
    previous = getattr(panel, '_bottom_scrolls', ())
    scrolls = scrolls_at_bottom(panel)
    if scrolls != previous:
        fill_bottom(panel, *scrolls)
        panel._automatic_scroll_edge = bool(scrolls)
    return bool(scrolls)


def reserve_container(container):
    """Refresh retained Back previews as well as the currently visible route."""
    if container.content is None:
        return
    root = container.content.interface
    for view in (root, *root.children):
        refresh_scroll_panel(view)
        if getattr(view, '_bottom_scrolls', ()) and view.app is not None:
            from .appearance import reserve_navigation
            reserve_navigation(view.app, view=view)


def sync_bottom(view, *, inset=0, overlap=0):
    """Extend the viewport to its host edge and retain safe final-row padding."""
    scrolls = getattr(view, '_bottom_scrolls', ())
    if not scrolls:
        return False
    margin = -inset
    if view.style.margin_bottom != margin:
        view.style.margin_bottom = margin
    backend = type(view._impl).__module__
    for scroll in scrolls:
        _pad_bottom(scroll, inset + overlap + BOTTOM_GAP, backend)
    return True


def _pad_bottom(scroll, bottom, backend):
    native = getattr(scroll._impl, 'native', None)
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import UIEdgeInsets
        # The owning container has already measured safe areas and bars.
        native.contentInsetAdjustmentBehavior = 2  # Never.
        current = native.contentInset
        if current.bottom != bottom:
            native.contentInset = UIEdgeInsets(current.top, current.left, bottom, current.right)
        indicator = native.verticalScrollIndicatorInsets
        if indicator.bottom != bottom:
            native.verticalScrollIndicatorInsets = UIEdgeInsets(
                indicator.top, indicator.left, bottom, indicator.right)
    elif backend.startswith('toga_android.'):
        padding = scroll._impl.scale_in(bottom)
        if native.getPaddingBottom() != padding:
            native.setPadding(native.getPaddingLeft(), native.getPaddingTop(),
                              native.getPaddingRight(), padding)
        native.setClipToPadding(False)
