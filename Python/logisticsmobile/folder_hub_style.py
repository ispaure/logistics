"""Folder Hub presentation using native controls and dynamic app colour roles."""
from .appearance import surface as app_surface


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


def compact_icon(button, *, width=24, height=56, size=17, background='transparent'):
    """Small symbols within a full-height, tappable folder row."""
    button.style.width, button.style.height = width, height
    surface(button, radius=0, background=background, foreground='muted', outlined=False)
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
    backend = type(row._impl).__module__
    if backend.startswith('toga_android.'):
        # Toga flattens boxes and controls into native siblings. Keep opaque
        # controls inside the outline instead of painting across its edges.
        for child in row.children:
            child.style.margin_top = child.style.margin_bottom = 1
        if row.children:
            row.children[0].style.margin_left = max(1, row.children[0].style.margin_left)
            row.children[-1].style.margin_right = max(1, row.children[-1].style.margin_right)
        row.style.margin_bottom = 6
    app_surface(row, radius=10, outlined=False, eink_outlined=True)
    if backend.startswith('toga_iOS.'):
        row._impl.native.layer.masksToBounds = True
    elif backend.startswith('toga_android.'):
        row._impl.native.setClipToOutline(True)
    return row


def folder_name(button):
    """The title is part of the folder row, rather than a boxed action."""
    return surface(button, radius=0, background='transparent', foreground='text', outlined=False)
