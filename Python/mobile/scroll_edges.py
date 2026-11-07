"""Keep browser clearance inside scrolling content, below its final row."""


def fill_bottom(view, *scrolls):
    """Declare a page whose bottom edge belongs entirely to scrolling lists."""
    view._bottom_scrolls = scrolls
    view.style.margin_bottom = 0
    sync_bottom(view)
    return view


def reserve_container(container):
    """Refresh retained Back previews as well as the currently visible route."""
    if container.content is None:
        return
    root = container.content.interface
    for view in (root, *root.children):
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
        native = getattr(scroll._impl, 'native', None)
        bottom = inset + overlap + 12
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
    return True
