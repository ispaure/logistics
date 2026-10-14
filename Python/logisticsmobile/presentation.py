"""Small native presentation helpers; system colours follow light/dark appearance."""

def surface(widget):
    if type(widget._impl).__module__.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        native = widget._impl.native
        colour = ObjCClass('UIColor').secondarySystemGroupedBackgroundColor()
        widget._impl._default_background_color = colour
        native.backgroundColor = colour
        native.layer.cornerRadius = 10
    return widget


def list_button(button):
    from travertino.size import at_least
    # Text may truncate inside a row rather than widening the whole scroll view.
    button.intrinsic.width = at_least(44)
    backend = type(button._impl).__module__
    if backend.startswith(('toga_iOS.', 'toga_android.')) and not getattr(button._impl, '_row_hint', False):
        import weakref
        reference = weakref.ref(button)
        native_rehint = type(button._impl).rehint
        def rehint():
            target = reference()
            if target is not None:
                native_rehint(target._impl)
                target.intrinsic.width = at_least(44)
        button._impl.rehint = rehint
        button._impl._row_hint = True
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        native = button._impl.native
        native.contentHorizontalAlignment = 1
        native.titleLabel.lineBreakMode = 4
        native.tintColor = ObjCClass('UIColor').labelColor()
        native.setTitleColor(native.tintColor, forState=0)
        native.accessibilityLabel = button.text
    elif backend.startswith('toga_android.'):
        from android.text import TextUtils
        from android.content.res import ColorStateList
        from com.google.android.material import R as MaterialR
        button._impl._list_row = True
        native = button._impl.native
        native.setBackgroundTintList(ColorStateList.valueOf(button._impl.get_theme_color(MaterialR.attr.colorSurface)))
        native.setGravity(3 | 16)
        native.setSingleLine(True)
        native.setEllipsize(TextUtils.TruncateAt.END)
    return button


def template_icon(image):
    if type(image._impl).__module__.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        native = image._impl.native
        native.image = native.image.imageWithRenderingMode(2)
        native.tintColor = ObjCClass('UIColor').labelColor()
    return image


def scroll_content(view):
    """Give a reparented subtree a fresh root and zero layout origin.

    The pinned layout engine retains the old parent's origin on a detached
    subtree. A fresh Box rebases both ancestry and coordinates through public
    parenting APIs before the subtree becomes scroll content.
    """
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN
    return toga.Box(children=[view], style=Pack(direction=COLUMN))
