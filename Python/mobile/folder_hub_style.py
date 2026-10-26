"""Workspaces presentation using native controls and dynamic app colour roles."""
from .appearance import surface as app_surface
from .ui_metrics import TOUCH_TARGET, BODY_TEXT, toga_font_size

SOURCE_LABELS = {'Local': 'Local', 'rclone': 'Cloud', 'Network shares': 'Home Server'}
ROW_HEIGHT = TOUCH_TARGET
ROW_GAP = 4
ENTRY_ICON_SIZE = 24
ENTRY_ICON_MARGIN = (TOUCH_TARGET - ENTRY_ICON_SIZE) // 2
ENTRY_ICON_SLOT = ENTRY_ICON_SIZE + 2 * ENTRY_ICON_MARGIN
TREE_INDENT = 40
TREE_STROKE = 2
TREE_LABEL_GAP = 8


def folder_scroll(content):
    """Leave a dedicated scrollbar gutter beside the Android folder tree."""
    import toga
    from toga.style import Pack
    scroll = toga.ScrollContainer(horizontal=False, content=content, style=Pack(flex=1))
    if type(scroll._impl).__module__.startswith('toga_android.'):
        from math import ceil
        from android.view import View
        native = scroll._impl.native
        # Toga sizes its content from the full viewport, independently of
        # Android's scrollbar inset padding. Keep the bar inside the viewport
        # and reserve its actual width in Pack so row outlines stop before it.
        native.setScrollBarStyle(View.SCROLLBARS_INSIDE_OVERLAY)
        gutter = max(8, ceil(scroll._impl.scale_out(native.getVerticalScrollbarWidth())) + 4)
        if native.getLayoutDirection() == View.LAYOUT_DIRECTION_RTL:
            content.style.margin_left = gutter
        else:
            content.style.margin_right = gutter
    return scroll


def align_group_label(label):
    """Center native text in the same row geometry as the branch connectors."""
    label.style.margin_top = label.style.margin_bottom = 0
    backend = type(label._impl).__module__
    if backend.startswith('toga_iOS.'):
        from math import ceil
        size = label._impl.native.intrinsicContentSize
        size = size() if callable(size) else size
        label.style.height = ceil(size.height)
        gap = max(0, ROW_HEIGHT - label.style.height)
        label.style.margin_top = gap // 2
        label.style.margin_bottom = gap - label.style.margin_top
    elif backend.startswith('toga_android.'):
        label._impl.native.setIncludeFontPadding(False)
        label._impl.native.setGravity(3 | 16)  # Start, center vertically.
        label.style.height = ROW_HEIGHT
    return label


def tree_anchor(label=None):
    """Anchor groups beneath their text, and folders beneath their icon."""
    if label is None:
        return ENTRY_ICON_SLOT / 2
    backend = type(label._impl).__module__
    if backend.startswith('toga_iOS.'):
        size = label._impl.native.intrinsicContentSize
        # Older UIKit releases expose this getter as a method through Rubicon.
        size = size() if callable(size) else size
        width = float(size.width)
    elif backend.startswith('toga_android.'):
        width = label._impl.scale_out(label._impl.native.getPaint().measureText(label.text))
    else:
        width = len(label.text) * label.style.font_size * .5
    # Long headings must still leave space for a horizontal branch in the gutter.
    return round(min(TREE_INDENT - 8, max(8, (getattr(label.style, 'margin_left', 0) or 0) + width / 2)))


def tree_guide(height, midpoints, anchor):
    """A decorative gutter, ending its trunk at the last immediate child.

    Segments use native surfaces so light/dark and E Ink repaint together with
    the rows. Child midpoints include preceding siblings' entire subtrees.
    """
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN

    guide = toga.Box(style=Pack(direction=COLUMN, width=TREE_INDENT, height=height))
    left = anchor - TREE_STROKE / 2
    cursor = 0
    for midpoint in midpoints:
        top = midpoint - TREE_STROKE / 2
        guide.add(surface(toga.Box(style=Pack(width=TREE_STROKE,
            height=top - cursor, margin_left=left)),
            radius=0, background='tree_guide', outlined=False))
        guide.add(surface(toga.Box(style=Pack(width=TREE_INDENT - left,
            height=TREE_STROKE, margin_left=left)),
            radius=0, background='tree_guide', outlined=False))
        cursor = midpoint + TREE_STROKE / 2
    if cursor < height:
        guide.add(toga.Box(style=Pack(height=height - cursor)))
    return guide


def surface(widget, *, outlined=True, **kwargs):
    """Keep a row's children borderless in monochrome, just as in Slate."""
    return app_surface(widget, outlined=outlined, eink_outlined=outlined, **kwargs)


def source_tab(button, selected):
    button.enabled = True
    button.style.font_weight = 'bold' if selected else 'normal'
    surface(button, radius=8, background='surface' if selected else 'alternate',
            foreground='text' if selected else 'muted', outlined=False,
            eink_selected=selected)
    backend = type(button._impl).__module__
    if backend.startswith('toga_iOS.'):
        button._impl.native.accessibilityTraits = (1 | 4) if selected else 1
    elif backend.startswith('toga_android.'):
        button._impl.native.setSelected(selected)


def compact_icon(button, *, width=24, height=48, size=17, background='transparent', foreground='muted'):
    """Small symbols within a full-height, tappable folder row."""
    button.style.width, button.style.height = width, height
    surface(button, radius=0, background=background, foreground=foreground, outlined=False)
    backend = type(button._impl).__module__
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        config = ObjCClass('UIImageSymbolConfiguration').configurationWithPointSize(size, weight=4)
        button._impl.native.setPreferredSymbolConfiguration(config, forImageInState=0)
    elif backend.startswith('toga_android.'):
        native = button._impl.native
        pixels = button._impl.scale_in(size)
        button._impl._control_drawable.setBounds(0, 0, pixels, pixels)
        # Android places a start compound drawable against the content edge,
        # even with an empty, centered title. Reserve the same space on both
        # sides so the glyph sits inside its touch target instead of against
        # the row outline. This geometry is shared by both colour modes.
        horizontal = button._impl.scale_in(max(0, (width - size) / 2))
        vertical = button._impl.scale_in(max(0, (height - size) / 2))
        native.setPadding(horizontal, vertical, horizontal, vertical)


def toolbar_button(button, symbol):
    surface(button, radius=9, foreground='accent', outlined=False)
    if type(button._impl).__module__.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        native = button._impl.native
        native.setImage(ObjCClass('UIImage').systemImageNamed(symbol), forState=0)
        native.setPreferredSymbolConfiguration(
            ObjCClass('UIImageSymbolConfiguration').configurationWithPointSize(14, weight=4),
            forImageInState=0)


def folder_row(row):
    """Shared list surface for workspace locations and browser entries."""
    row.style.margin_bottom = ROW_GAP
    backend = type(row._impl).__module__
    app_surface(row, radius=8, background='surface', outlined=False, eink_outlined=True)
    if backend.startswith('toga_iOS.'):
        row._impl.native.layer.masksToBounds = True
    elif backend.startswith('toga_android.'):
        row._impl.native.setClipToOutline(True)
    return row


def folder_name(button):
    """Shared single-line title metrics, inside the row's own surface."""
    button.style.height = ROW_HEIGHT
    button.style.font_size = toga_font_size(BODY_TEXT)
    button.style.font_weight = 'normal'
    if type(button._impl).__module__.startswith('toga_android.'):
        # Keep the platform's default button family from changing row metrics.
        button.style.font_family = 'sans-serif'
        button._impl.native.setPadding(0, 0, 0, 0)
    return surface(button, radius=0, background='transparent', foreground='text', outlined=False)


def source_actions(host):
    """Only reserve toolbar space when the source has a useful action."""
    if not hasattr(host, 'folder_source_actions'):
        return
    transfer = (getattr(host, 'transfer_busy', False) or
                (getattr(host, 'transfer_notification', False) and not getattr(host, 'transfer_complete', False)))
    configured = getattr(host, 'folder_configured_sources', set())
    action = (host.folder_transfers_button if host.folder_source == 'rclone' and transfer else
              host.folder_add_share_button if host.folder_source == 'Network shares' and 'Network shares' not in configured else
              host.folder_add_remote_button if host.folder_source == 'rclone' and 'rclone' not in configured else None)
    actions = [action] if action is not None else []
    if list(host.folder_source_actions.children) != actions:
        for child in list(host.folder_source_actions.children):
            host.folder_source_actions.remove(child)
        for child in actions:
            host.folder_source_actions.add(child)
    margin = 12 if actions else 0
    if host.folder_source_actions.style.margin_bottom != margin:
        host.folder_source_actions.style.margin_bottom = margin
