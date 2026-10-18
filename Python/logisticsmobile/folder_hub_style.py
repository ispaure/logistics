"""Workspaces presentation using native controls and dynamic app colour roles."""
from .appearance import surface as app_surface

SOURCE_LABELS = {'Local': 'Local', 'rclone': 'Cloud', 'Network shares': 'Home Server'}
ROW_HEIGHT = 48
ROW_GAP = 4
ENTRY_ICON_SIZE = 24
ENTRY_ICON_MARGIN = 6
ENTRY_ICON_SLOT = ENTRY_ICON_SIZE + 2 * ENTRY_ICON_MARGIN
TREE_INDENT = 40
TREE_STROKE = 1.5


def tree_anchor(label=None):
    """Anchor groups beneath their text, and folders beneath their icon."""
    if label is None:
        return ENTRY_ICON_SLOT / 2
    backend = type(label._impl).__module__
    if backend.startswith('toga_iOS.'):
        width = float(label._impl.native.intrinsicContentSize.width)
    elif backend.startswith('toga_android.'):
        width = label._impl.scale_out(label._impl.native.getPaint().measureText(label.text))
    else:
        width = len(label.text) * label.style.font_size * .5
    # Long headings must still leave space for a horizontal branch in the gutter.
    return min(TREE_INDENT - 8, max(8, width / 2))


def tree_guide(height, midpoints, anchor):
    """A decorative gutter, ending its trunk at the last immediate child.

    Segments use native surfaces so light/dark and E Ink repaint together with
    the rows. Child midpoints include preceding siblings' entire subtrees.
    """
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN

    guide = toga.Box(style=Pack(direction=COLUMN, width=TREE_INDENT, height=height))
    cursor = 0
    for midpoint in midpoints:
        top = midpoint - TREE_STROKE / 2
        guide.add(surface(toga.Box(style=Pack(width=TREE_STROKE,
            height=top - cursor, margin_left=anchor)),
            radius=0, background='tree_guide', outlined=False))
        guide.add(surface(toga.Box(style=Pack(width=TREE_INDENT - anchor,
            height=TREE_STROKE, margin_left=anchor)),
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
        native.setPadding(0, 0, 0, 0)


def toolbar_button(button, symbol):
    surface(button, radius=9, foreground='accent')
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
    app_surface(row, radius=8, background='surface', outlined=False, eink_outlined=False)
    if backend.startswith('toga_iOS.'):
        row._impl.native.layer.masksToBounds = True
    elif backend.startswith('toga_android.'):
        row._impl.native.setClipToOutline(True)
    return row


def folder_name(button):
    """Shared single-line title metrics, inside the row's own surface."""
    button.style.height = ROW_HEIGHT
    button.style.font_size = 15
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
    action = (host.folder_transfers_button if host.folder_source == 'rclone' and transfer else
              host.folder_add_share_button if host.folder_source == 'Network shares' else None)
    actions = [action] if action is not None else []
    if list(host.folder_source_actions.children) != actions:
        for child in list(host.folder_source_actions.children):
            host.folder_source_actions.remove(child)
        for child in actions:
            host.folder_source_actions.add(child)
    host.folder_source_actions.style.margin_bottom = 12 if actions else 0
