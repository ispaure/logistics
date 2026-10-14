"""Semantic colours for the pinned native backends, without changing document data."""
import weakref
from toga.colors import BLACK

_installed = set()
_widgets = weakref.WeakSet()


def contrast_ratio(first, second):
    def luminance(value):
        channels = [((value >> shift) & 255) / 255 for shift in (16, 8, 0)]
        channels = [channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4 for channel in channels]
        return sum(a * b for a, b in zip(channels, (.2126, .7152, .0722)))
    low, high = sorted([luminance(first), luminance(second)])
    return (high + .05) / (low + .05)


def readable_accent(accent, foreground, background):
    """Keep the theme hue where possible, bringing small selected labels to 4.5:1."""
    for step in range(17):
        fraction = step / 16
        channels = [round(((accent >> shift) & 255) * (1 - fraction)
                          + ((foreground >> shift) & 255) * fraction) for shift in (16, 8, 0)]
        candidate = (255 << 24) | (channels[0] << 16) | (channels[1] << 8) | channels[2]
        if contrast_ratio(candidate, background) >= 4.5:
            return candidate - 2**32
    return foreground


def install_appearance(app):
    backend = type(app._impl).__module__
    if backend in _installed:
        return
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        from toga_iOS.widgets.label import Label
        from toga_iOS.widgets.textinput import TextInput
        from toga_iOS.widgets.multilinetextinput import MultilineTextInput
        from toga_iOS.widgets.selection import Selection
        colour = ObjCClass('UIColor')
        for cls in (Label, TextInput, MultilineTextInput, Selection):
            original = cls.set_color
            def set_color(impl, value, previous=original):
                if value not in (None, BLACK):
                    return previous(impl, value)
                impl.native.textColor = colour.labelColor()
                placeholder = getattr(impl, 'placeholder_label', None)
                if placeholder is not None:
                    placeholder.textColor = colour.secondaryLabelColor()
                    placeholder.alpha = 1.0
            cls.set_color = set_color
        for cls in (TextInput, MultilineTextInput, Selection):
            original = cls.create
            def create(impl, previous=original):
                previous(impl)
                impl.native.backgroundColor = colour.secondarySystemBackgroundColor()
                if not isinstance(impl, Selection):
                    impl.native.tintColor = colour.systemBlueColor()
            cls.create = create
    elif backend.startswith('toga_android.'):
        from android import R
        from android.content.res import ColorStateList
        from toga_android.widgets.label import TextViewWidget
        from toga_android.widgets.selection import Selection
        from toga_android.widgets.button import Button
        from toga_android.widgets.textinput import TextInput
        from com.google.android.material import R as MaterialR
        from android.text import TextUtils
        from travertino.size import at_least
        original_create = Button.create
        original_rehint = Button.rehint
        def create_button(impl):
            original_create(impl)
            impl.native.setAllCaps(False)
            impl.native.setSingleLine(True)
            impl.native.setEllipsize(TextUtils.TruncateAt.END)
        def rehint_button(impl):
            original_rehint(impl)
            if not impl._icon:
                natural = impl.interface.intrinsic.width.value
                impl.interface.intrinsic.width = at_least(44 if impl.interface.style.flex else min(natural, 256))
        Button.create = create_button
        Button.rehint = rehint_button
        original = TextViewWidget.set_color
        def set_color(impl, value):
            _widgets.add(impl)
            if value not in (None, BLACK):
                return original(impl, value)
            impl.native.setTextColor(impl.get_theme_color(R.attr.textColorPrimary))
            if isinstance(impl, TextInput):
                impl.native.setHintTextColor(impl.get_theme_color(R.attr.textColorSecondary))
                surface = impl.get_theme_color(MaterialR.attr.colorSurface)
                foreground = impl.get_theme_color(R.attr.textColorPrimary)
                accent = readable_accent(impl.get_theme_color(R.attr.colorAccent), foreground, surface)
                normal = impl.get_theme_color(R.attr.colorControlNormal)
                impl.native.setBackgroundTintList(ColorStateList([[R.attr.state_focused], []], [accent, normal]))
                impl.native_toplevel.setBackgroundColor(surface)
            if isinstance(impl, Button):
                attribute = MaterialR.attr.colorSurface if getattr(impl, '_list_row', False) else R.attr.colorButtonNormal
                impl.native.setBackgroundTintList(ColorStateList.valueOf(impl.get_theme_color(attribute)))
        TextViewWidget.set_color = set_color
        def selection_color(impl, value):
            _widgets.add(impl)
            impl.native.setBackgroundTintList(ColorStateList.valueOf(impl.get_theme_color(R.attr.textColorSecondary)))
            child = impl.native.getChildAt(0)
            if child is not None:
                child.setTextColor(impl.get_theme_color(R.attr.textColorPrimary))
        Selection.set_color = selection_color
    else:
        return
    _installed.add(backend)


def refresh_appearance(app):
    """Android handles uiMode in place, keeping editor/transfer ownership intact."""
    if not type(app._impl).__module__.startswith('toga_android.'):
        return
    from android import R
    from toga_android.widgets.selection import Selection
    for impl in list(_widgets):
        impl.set_color(impl.interface.style.color)
        if isinstance(impl, Selection):
            impl.adapter.notifyDataSetChanged()
    host = getattr(app, 'native_host', None)
    window = getattr(app, '_main_window', None)
    if host is not None and window is not None:
        colour = host.root._impl.get_theme_color(R.attr.colorBackground)
        host.root._impl.native.setBackgroundColor(colour)
        window._impl.container.native_content.setBackgroundColor(colour)

    if host is not None and host.adapter is not None:
        from android.content.res import ColorStateList
        from com.google.android.material import R as MaterialR
        impl = host.root._impl
        foreground = impl.get_theme_color(R.attr.textColorPrimary)
        accent = impl.get_theme_color(R.attr.colorAccent)
        background = impl.get_theme_color(MaterialR.attr.colorSurface)
        accent = readable_accent(accent, foreground, background)
        colours = ColorStateList([[R.attr.state_checked], []], [accent, foreground])
        for bar in (host.adapter.bottom, host.adapter.rail):
            if bar is not None:
                bar.setBackgroundColor(background)
                bar.setItemIconTintList(colours)
                bar.setItemTextColor(colours)
