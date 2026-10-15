"""Semantic colours for the pinned native backends, without changing document data."""
import weakref
from toga.colors import BLACK
from .palette import LIGHT, DARK, argb

_installed = set()
_widgets = weakref.WeakSet()
_surfaces = weakref.WeakKeyDictionary()
_apple_colors = {}
_color_blocks = []


def apple_color(role):
    """Keep semantic UIColors dynamic; never resolve a colour at construction."""
    if role not in _apple_colors:
        from rubicon.objc import ObjCClass, ObjCInstance, Block, objc_id
        colour = ObjCClass('UIColor')
        def resolve(traits):
            values = DARK if ObjCInstance(traits).userInterfaceStyle == 2 else LIGHT
            value = int(values[role][1:], 16)
            return colour.colorWithRed(((value >> 16) & 255) / 255,
                green=((value >> 8) & 255) / 255, blue=(value & 255) / 255, alpha=1).ptr.value
        block = Block(resolve, objc_id, objc_id)
        _color_blocks.append(block)
        _apple_colors[role] = colour.colorWithDynamicProvider(block)
    return _apple_colors[role]


def paint_surface(impl, radius):
    backend = type(impl).__module__
    if backend.startswith('toga_iOS.'):
        native = impl.native
        impl._default_background_color = apple_color('surface')
        native.backgroundColor = impl._default_background_color
        native.layer.cornerRadius = radius
        native.layer.borderWidth = 1
        native.layer.borderColor = apple_color('border').resolvedColorWithTraitCollection(native.traitCollection).CGColor
    elif backend.startswith('toga_android.'):
        from android.graphics.drawable import GradientDrawable
        colors = DARK if impl.native.getResources().getConfiguration().uiMode & 0x30 == 0x20 else LIGHT
        drawable = GradientDrawable()
        drawable.setColor(argb(colors['surface']))
        drawable.setCornerRadius(impl.scale_in(radius))
        drawable.setStroke(max(1, impl.scale_in(1)), argb(colors['border']))
        impl.native.setBackground(drawable)


def surface(widget, *, radius=12):
    _surfaces[widget._impl] = radius
    paint_surface(widget._impl, radius)
    return widget


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
        from rubicon.objc import ObjCClass, objc_method, send_super, objc_id
        import toga_iOS.widgets.box as box_module
        # CALayer stores a resolved CGColor. Refresh card strokes when UIKit
        # changes traits, while dynamic text/background colours update themselves.
        class LogisticsSurfaceView(box_module.TogaView):
            @objc_method
            def traitCollectionDidChange_(self, previous: objc_id) -> None:
                send_super(__class__, self, 'traitCollectionDidChange:', previous, argtypes=[objc_id])
                impl = self.impl
                if impl in _surfaces:
                    paint_surface(impl, _surfaces[impl])
        box_module.TogaView = LogisticsSurfaceView
        from toga_iOS.widgets.base import Widget
        from toga_iOS.widgets.button import Button
        original_background = Widget.set_background_color
        def set_background(impl, value):
            if value is None and isinstance(impl, (TextInput, MultilineTextInput, Selection)):
                impl._default_background_color = apple_color('surface')
            original_background(impl, value)
        Widget.set_background_color = set_background
        original_button_color = Button.set_color
        def button_color(impl, value):
            if value is None:
                impl.native.tintColor = apple_color('accent')
            original_button_color(impl, value)
        Button.set_color = button_color
        from toga_iOS.widgets.label import Label
        from toga_iOS.widgets.textinput import TextInput
        from toga_iOS.widgets.multilinetextinput import MultilineTextInput
        from toga_iOS.widgets.selection import Selection
        for cls in (Label, TextInput, MultilineTextInput, Selection):
            original = cls.set_color
            def set_color(impl, value, previous=original):
                if value not in (None, BLACK):
                    return previous(impl, value)
                impl.native.textColor = apple_color('text')
                placeholder = getattr(impl, 'placeholder_label', None)
                if placeholder is not None:
                    placeholder.textColor = apple_color('muted')
                    placeholder.alpha = 1.0
            cls.set_color = set_color
        for cls in (TextInput, MultilineTextInput, Selection):
            original = cls.create
            def create(impl, previous=original):
                previous(impl)
                impl.native.backgroundColor = apple_color('surface')
                if not isinstance(impl, Selection):
                    impl.native.tintColor = apple_color('accent')
                if isinstance(impl, MultilineTextInput):
                    # The navigation host already reserves keyboard/safe areas.
                    # UIKit's automatic text-view insets can exceed a compact
                    # editor's height; iOS 26's scroll-edge veil then covers its
                    # text while typing. Keep scrolling inside the measured box.
                    impl.native.contentInsetAdjustmentBehavior = 2  # never
                    from rubicon.objc import SEL
                    for edge in ('topEdgeEffect', 'bottomEdgeEffect'):
                        if impl.native.respondsToSelector(SEL(edge)):
                            getattr(impl.native, edge).hidden = True
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
        from toga_android.widgets.base import Widget
        original_theme_color = Widget.get_theme_color
        roles = {R.attr.colorBackground: 'window', MaterialR.attr.colorSurface: 'surface',
                 R.attr.colorButtonNormal: 'surface', R.attr.textColorPrimary: 'text',
                 R.attr.textColorSecondary: 'muted', R.attr.colorControlNormal: 'border',
                 R.attr.colorAccent: 'accent'}
        def theme_color(impl, attribute):
            role = roles.get(attribute)
            if role is None:
                return original_theme_color(impl, attribute)
            colors = DARK if impl.native.getResources().getConfiguration().uiMode & 0x30 == 0x20 else LIGHT
            return argb(colors[role])
        Widget.get_theme_color = theme_color
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
    """Recolour live chrome without replacing editors or transfer owners."""
    if type(app._impl).__module__.startswith('toga_iOS.'):
        host = getattr(app, 'native_host', None)
        window = getattr(app, '_main_window', None)
        if host is not None and window is not None:
            color = apple_color('window')
            window._impl.native.backgroundColor = color
            window._impl.container.native.backgroundColor = color
            for body in host.bodies.values():
                body._impl._default_background_color = color
                body._impl.native.backgroundColor = color
            if host.adapter is not None:
                for navigation in host.adapter.navigation:
                    navigation.view.backgroundColor = color
                    navigation.navigationBar.tintColor = apple_color('accent')
                host.adapter.controller.tabBar.tintColor = apple_color('accent')
        for impl, radius in list(_surfaces.items()):
            paint_surface(impl, radius)
        return
    if not type(app._impl).__module__.startswith('toga_android.'):
        return
    from android import R
    from toga_android.widgets.selection import Selection
    for impl in list(_widgets):
        impl.set_color(impl.interface.style.color)
        if isinstance(impl, Selection):
            impl.adapter.notifyDataSetChanged()
    for impl, radius in list(_surfaces.items()):
        paint_surface(impl, radius)
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
