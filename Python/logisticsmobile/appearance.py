"""Semantic colours for the pinned native backends, without changing document data."""
import weakref
from toga.colors import BLACK
from .palette import LIGHT, DARK, argb, android_palette, eink_enabled

_installed = set()
_widgets = weakref.WeakSet()
_surfaces = weakref.WeakKeyDictionary()
_apple_colors = {}
_color_blocks = []
_template_icons = weakref.WeakSet()
_android_boxes = weakref.WeakSet()
_android_webviews = weakref.WeakSet()


def template_icon(widget):
    from commonUtils.ui.native.presentation import template_icon as native_template_icon
    native_template_icon(widget)
    if type(widget._impl).__module__.startswith('toga_android.'):
        _template_icons.add(widget._impl)
        from android import R
        from android.content.res import ColorStateList
        widget._impl.native.setImageTintList(ColorStateList.valueOf(widget._impl.get_theme_color(R.attr.textColorPrimary)))
    return widget


def accessible_name(widget, name):
    """Name icon-only controls without changing their visible title."""
    widget.accessible_name = name
    backend = type(widget._impl).__module__
    if backend.startswith('toga_iOS.'):
        widget._impl.native.accessibilityLabel = name
    elif backend.startswith('toga_android.'):
        widget._impl.native.setContentDescription(name)
    return widget


def action_button(button, *, destructive=False):
    """Use native action hierarchy; keep platform disabled/focus states."""
    button.action_role = 'destructive' if destructive else 'primary'
    button._impl._action_role = button.action_role
    _widgets.add(button._impl)
    backend = type(button._impl).__module__
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        if destructive:
            button._impl.native.setTitleColor(ObjCClass('UIColor').systemRedColor(), forState=0)
        else:
            config = ObjCClass('UIButtonConfiguration').filledButtonConfiguration()
            config.title = button.text
            config.cornerStyle = 3
            config.baseForegroundColor = ObjCClass('UIColor').whiteColor
            config.baseBackgroundColor = apple_color('primary')
            button._impl.native.configuration = config
            button._impl.native.setTitleColor(ObjCClass('UIColor').whiteColor, forState=0)
    elif backend.startswith('toga_android.'):
        restore_eink_button(button._impl)
        if eink_enabled():
            paint_eink_button(button._impl)
        elif destructive:
            dark = button._impl.native.getResources().getConfiguration().uiMode & 0x30 == 0x20
            button._impl.native.setTextColor(argb('#ff8a80' if dark else '#c62828'))
        else:
            from android.content.res import ColorStateList
            from android import R
            button._impl.native.setBackgroundTintList(ColorStateList(
                [[R.attr.state_enabled], [-R.attr.state_enabled]], [argb('#2563eb'), argb('#606b7c')]))
            button._impl.native.setTextColor(argb('#ffffff'))
    return button


def reserve_navigation(app):
    """Reserve only the measured floating-bar overlap, for the active screen."""
    adapter = app.native_host.adapter
    if adapter is None or not hasattr(adapter, 'navigation'):
        return
    body = app.routes.body()
    if not body.children:
        return
    view = body.children[0]
    # Chat owns composer clearance; fullscreen comics hide their navigation.
    # Readers with controls still need room above a floating destination bar.
    if (view is getattr(app, 'chat_view', None) or getattr(view, '_comic_fullscreen', False)
            or getattr(view, '_reader_fullscreen', False)):
        return
    container = view._impl.container
    if container is None or container.native.bounds.size.height <= 0:
        return
    if getattr(view, '_reading_frame', False):
        view._navigation_margin = view._reading_frame_owner.margin
    elif not hasattr(view, '_navigation_margin'):
        view._navigation_margin = view.style.margin_bottom
    extra = 0
    bar = adapter.controller.tabBar
    if not bar.isHidden():
        window = app.main_window._impl.native
        viewport = container.native.convertRect(container.native.bounds, toView=window)
        bounds = bar.convertRect(bar.bounds, toView=window)
        from features.lm.mobile.presentation import navigation_clearance
        extra = navigation_clearance(float(viewport.origin.y + container.top_inset),
            float(viewport.origin.y + viewport.size.height - container.bottom_inset),
            float(bounds.origin.y), float(bounds.size.height), bar_width=float(bounds.size.width)) - 12
    margin = view._navigation_margin + extra
    if view.style.margin_bottom != margin:
        view.style.margin_bottom = margin


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
    background, foreground, outlined = getattr(impl, '_surface_roles', ('surface', None, True))
    if backend.startswith('toga_iOS.'):
        native = impl.native
        impl._default_background_color = apple_color(background)
        native.backgroundColor = impl._default_background_color
        native.layer.cornerRadius = radius
        native.layer.borderWidth = 1 if outlined else 0
        native.layer.borderColor = apple_color('border').resolvedColorWithTraitCollection(native.traitCollection).CGColor
        if foreground:
            if hasattr(impl.interface, 'on_press'):
                native.configuration = None
                native.tintColor = apple_color(foreground)
                native.setTitleColor(apple_color(foreground), forState=0)
                native.setTitleColor(apple_color('muted'), forState=2)
            else:
                native.textColor = apple_color(foreground)
    elif backend.startswith('toga_android.'):
        from android.graphics.drawable import GradientDrawable
        colors = android_palette(impl.native.getResources().getConfiguration().uiMode & 0x30 == 0x20)
        drawable = GradientDrawable()
        drawable.setColor(argb(colors.get(background, colors['surface'])))
        drawable.setCornerRadius(0 if eink_enabled() else impl.scale_in(radius))
        if outlined or eink_enabled():
            drawable.setStroke(max(1, impl.scale_in(1)), argb(colors['border']))
        if foreground:
            from android.content.res import ColorStateList
            from android import R
            impl.native.setTextColor(ColorStateList(
                [[-R.attr.state_enabled], []], [argb(colors['muted']), argb(colors.get(foreground, colors['text']))]))
        if hasattr(impl.interface, 'on_press'):
            from android.content.res import ColorStateList
            from android.graphics.drawable import RippleDrawable
            impl.native.setBackgroundTintList(None)
            impl.native.setBackground(RippleDrawable(ColorStateList.valueOf(argb(colors['hover'])), drawable, None))
        else:
            impl.native.setBackground(drawable)
        if hasattr(impl, '_control_drawable'):
            from .control_icons import tint_android
            tint_android(impl)


def surface(widget, *, radius=12, background='surface', foreground=None, outlined=True):
    widget._impl._surface_roles = (background, foreground, outlined)
    if foreground and hasattr(widget, 'on_press'):
        widget._impl._row_hint = True
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


def select_apple_item(impl, index, item, *, select):
    """Refresh UIPickerView's row count before choosing from a replaced source."""
    impl.native_picker.reloadAllComponents()
    return select(impl, index, item)


def commit_apple_selection(picker, row):
    """Close the input field's picker before a user selection changes routes."""
    item = picker.interface.items[row]
    picker.native.text = picker.interface._title_for_item(item)
    # UITextField owns first-responder status; UIPickerView is its inputView.
    picker.native.resignFirstResponder()
    picker.interface.on_change()


def install_appearance(app):
    backend = type(app._impl).__module__
    if backend in _installed:
        return
    if backend.startswith('toga_iOS.'):
        from .ios_reader_chrome import install
        install()
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
        from ctypes import c_bool
        from rubicon.objc.types import CGPoint
        import toga_iOS.widgets.button as button_module

        class LogisticsActionButton(button_module.TogaButton):
            @objc_method
            def pointInside_withEvent_(self, point: CGPoint, event: objc_id) -> bool:
                inside = send_super(__class__, self, 'pointInside:withEvent:', point, event,
                                    restype=c_bool, argtypes=[CGPoint, objc_id])
                if not inside or self.impl is None:
                    return bool(inside)
                # Filled rows, small icon controls and glass buttons show their
                # full target. A plain text action shows only its title/image.
                if (getattr(self.impl, '_row_hint', False) or self.bounds.size.width <= 52
                        or self.configuration is not None):
                    return True
                title = self.titleRectForContentRect(self.bounds)
                left, right = title.origin.x, title.origin.x + title.size.width
                if self.imageForState(0) is not None:
                    image = self.imageRectForContentRect(self.bounds)
                    left = min(left, image.origin.x)
                    right = max(right, image.origin.x + image.size.width)
                # Plain text still needs a complete 44-point target. Keep it
                # inside the button so adjacent commands never steal touches.
                center = (left + right) / 2
                half = max(22, (right - left) / 2 + 2)
                return max(0, center - half) <= point.x <= min(self.bounds.size.width, center + half)

        button_module.TogaButton = LogisticsActionButton
        original_create_button = button_module.Button.create
        def create_action_button(impl):
            original_create_button(impl)
            from rubicon.objc import SEL
            impl.native.removeTarget(impl.native, action=SEL('onPress:'), forControlEvents=1)
            impl.native.addTarget(impl.native, action=SEL('onPress:'), forControlEvents=1 << 6)
        button_module.Button.create = create_action_button
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
            role = getattr(impl, '_action_role', None)
            if role is not None:
                colour = ObjCClass('UIColor').systemRedColor() if role == 'destructive' else ObjCClass('UIColor').whiteColor
                impl.native.setTitleColor(colour, forState=0)
                return
            if value is None:
                impl.native.tintColor = apple_color('accent')
            original_button_color(impl, value)
        Button.set_color = button_color
        from toga_iOS.widgets.label import Label
        from toga_iOS.widgets.textinput import TextInput
        from toga_iOS.widgets.multilinetextinput import MultilineTextInput
        import toga_iOS.widgets.selection as selection_module

        class LogisticsPickerView(selection_module.TogaPickerView):
            @objc_method
            def pickerView_didSelectRow_inComponent_(
                    self, picker_view: objc_id, row: int, component: int) -> None:
                commit_apple_selection(self, row)

        selection_module.TogaPickerView = LogisticsPickerView
        Selection = selection_module.Selection
        original_select_item = Selection.select_item
        def select_item(impl, index, item):
            return select_apple_item(impl, index, item, select=original_select_item)
        Selection.select_item = select_item
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
        from toga_android.widgets.switch import Switch
        original_theme_color = Widget.get_theme_color
        roles = {R.attr.colorBackground: 'window', MaterialR.attr.colorSurface: 'surface',
                 R.attr.colorButtonNormal: 'surface', R.attr.textColorPrimary: 'text',
                 R.attr.textColorSecondary: 'muted', R.attr.colorControlNormal: 'border',
                 R.attr.colorAccent: 'accent'}
        def theme_color(impl, attribute):
            role = roles.get(attribute)
            if role is None:
                return original_theme_color(impl, attribute)
            colors = android_palette(impl.native.getResources().getConfiguration().uiMode & 0x30 == 0x20)
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
            restore_eink_button(impl)
            if not eink_enabled() and value not in (None, BLACK):
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
            if isinstance(impl, Switch):
                paint_eink_switch(impl)
            if isinstance(impl, Button):
                attribute = MaterialR.attr.colorSurface if getattr(impl, '_list_row', False) else R.attr.colorButtonNormal
                impl.native.setBackgroundTintList(ColorStateList.valueOf(impl.get_theme_color(attribute)))
                role = getattr(impl, '_action_role', None)
                if role is not None:
                    action_button(impl.interface, destructive=role == 'destructive')
                if eink_enabled():
                    paint_eink_button(impl)
        TextViewWidget.set_color = set_color
        def selection_color(impl, value):
            _widgets.add(impl)
            impl.native.setBackgroundTintList(ColorStateList.valueOf(impl.get_theme_color(R.attr.textColorSecondary)))
            child = impl.native.getChildAt(0)
            if child is not None:
                child.setTextColor(impl.get_theme_color(R.attr.textColorPrimary))
        Selection.set_color = selection_color
        from toga_android.widgets.box import Box
        original_box_background = Box.set_background_color
        def box_background(impl, value):
            _android_boxes.add(impl)
            if eink_enabled():
                impl.native_toplevel.setBackgroundColor(argb('#ffffff'))
            else:
                original_box_background(impl, value)
        Box.set_background_color = box_background
        from toga_android.widgets.webview import WebView
        original_content = WebView.set_content
        def web_content(impl, root_url, content):
            from .palette import eink_html
            _android_webviews.add(impl)
            content = eink_html(content)
            if getattr(impl.interface, 'private_configured', False) and len(content.encode('utf-8')) > 2 * 1024 * 1024:
                raise ValueError('Private HTML exceeds the memory-only limit after appearance styling.')
            original_content(impl, root_url, content)
        WebView.set_content = web_content
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
        if hasattr(app, 'chat_view'):
            app.sync_chat_appearance()
        return
    if not type(app._impl).__module__.startswith('toga_android.'):
        return
    from android import R
    from toga_android.widgets.selection import Selection
    from android.content.res import ColorStateList
    from .control_icons import refresh_icons
    refresh_icons()
    for impl in list(_template_icons):
        impl.native.setImageTintList(ColorStateList.valueOf(impl.get_theme_color(R.attr.textColorPrimary)))
    from .palette import eink_script
    native_window = app._impl.native.getWindow()
    decor = native_window.getDecorView()
    if eink_enabled():
        if not hasattr(app, '_eink_system_bars'):
            app._eink_system_bars = (native_window.getStatusBarColor(), native_window.getNavigationBarColor(), decor.getSystemUiVisibility())
        native_window.setStatusBarColor(argb('#ffffff'))
        native_window.setNavigationBarColor(argb('#ffffff'))
        decor.setSystemUiVisibility(decor.getSystemUiVisibility() | 8192 | 16)
    elif hasattr(app, '_eink_system_bars'):
        status, navigation, visibility = app._eink_system_bars
        native_window.setStatusBarColor(status)
        native_window.setNavigationBarColor(navigation)
        decor.setSystemUiVisibility(visibility)
        del app._eink_system_bars
    for impl in list(_android_boxes):
        impl.set_background_color(impl.interface.style.background_color)
    for impl in list(_android_webviews):
        if not getattr(impl.interface, 'private_closed', False):
            impl.native.evaluateJavascript(eink_script(), None)
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
        from android.graphics.drawable import ColorDrawable
        bar = app._impl.native.getSupportActionBar()
        if bar is not None:
            bar.setBackgroundDrawable(ColorDrawable(colour))
            from android.text import SpannableString, Spanned
            from android.text.style import ForegroundColorSpan
            from androidx.appcompat import R as AppCompatR
            foreground = host.root._impl.get_theme_color(R.attr.textColorPrimary)
            title = SpannableString(window.title)
            title.setSpan(ForegroundColorSpan(foreground), 0, title.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            bar.setTitle(title)
            toolbar = app._impl.native.findViewById(AppCompatR.id.action_bar)
            if toolbar is not None and toolbar.getOverflowIcon() is not None:
                toolbar.getOverflowIcon().mutate().setTint(foreground)

    if host is not None and host.adapter is not None:
        from android.content.res import ColorStateList
        from com.google.android.material import R as MaterialR
        impl = host.root._impl
        foreground = impl.get_theme_color(R.attr.textColorPrimary)
        accent = impl.get_theme_color(R.attr.colorAccent)
        background = impl.get_theme_color(MaterialR.attr.colorSurface)
        accent = readable_accent(accent, foreground, background)
        colours = ColorStateList([[R.attr.state_checked], []], [accent, foreground])
        if not hasattr(host.adapter, '_eink_bar_styles'):
            host.adapter._eink_bar_styles = {}
        for index, bar in enumerate((host.adapter.bottom, host.adapter.rail)):
            if bar is not None:
                saved = host.adapter._eink_bar_styles
                if eink_enabled() and index not in saved:
                    saved[index] = bar.getItemActiveIndicatorColor(), bar.getItemRippleColor(), bar.getElevation()
                if eink_enabled():
                    bar.setItemActiveIndicatorColor(ColorStateList.valueOf(argb('#000000')))
                    bar.setItemRippleColor(ColorStateList.valueOf(0))
                    bar.setElevation(0)
                    bar.setItemIconTintList(ColorStateList([[R.attr.state_checked], []], [argb('#ffffff'), foreground]))
                    bar.setItemTextColor(ColorStateList.valueOf(foreground))
                else:
                    if index in saved:
                        indicator, ripple, elevation = saved.pop(index)
                        bar.setItemActiveIndicatorColor(indicator)
                        bar.setItemRippleColor(ripple)
                        bar.setElevation(elevation)
                    bar.setItemIconTintList(colours)
                    bar.setItemTextColor(colours)
                bar.setBackgroundColor(background)


def configure_android_eink(app):
    """Android is a single-activity host; other platforms keep their own themes."""
    if type(app._impl).__module__.startswith('toga_android.'):
        from .palette import set_eink_enabled
        enabled = app.preferences.values['android_eink'] == 'true'
        set_eink_enabled(enabled)
        # This activity handles uiMode changes; do not recreate document owners.
        delegate = app._impl.native.getDelegate()
        mode = 1 if enabled else -1  # MODE_NIGHT_NO / MODE_NIGHT_FOLLOW_SYSTEM
        if delegate.getLocalNightMode() != mode:
            delegate.setLocalNightMode(mode)


def restore_eink_button(impl):
    saved = getattr(impl, '_eink_button_style', None)
    if saved is not None and not eink_enabled():
        background, animator, elevation = saved
        impl.native.setBackground(background)
        impl.native.setStateListAnimator(animator)
        impl.native.setElevation(elevation)
        del impl._eink_button_style


def paint_eink_button(impl):
    from android.graphics.drawable import GradientDrawable
    from android.content.res import ColorStateList
    if not hasattr(impl, '_eink_button_style'):
        impl._eink_button_style = impl.native.getBackground(), impl.native.getStateListAnimator(), impl.native.getElevation()
    filled = getattr(impl, '_action_role', None) == 'primary'
    background = '#000000' if filled else '#ffffff'
    drawable = GradientDrawable()
    drawable.setColor(argb(background))
    drawable.setStroke(max(1, impl.scale_in(1)), argb('#000000'))
    impl.native.setBackground(drawable)
    impl.native.setBackgroundTintList(ColorStateList.valueOf(argb(background)))
    impl.native.setTextColor(argb('#ffffff' if filled else '#000000'))
    impl.native.setStateListAnimator(None)
    impl.native.setElevation(0)


def paint_eink_switch(impl):
    if eink_enabled():
        if not hasattr(impl, '_eink_switch_style'):
            impl._eink_switch_style = (impl.native.getThumbDrawable(), impl.native.getTrackDrawable(),
                impl.native.getThumbTintList(), impl.native.getTrackTintList())
        from android.graphics.drawable import GradientDrawable
        thumb, track = GradientDrawable(), GradientDrawable()
        thumb.setColor(argb('#000000'))
        thumb.setSize(impl.scale_in(20), impl.scale_in(24))
        track.setColor(argb('#ffffff'))
        track.setStroke(max(1, impl.scale_in(1)), argb('#000000'))
        track.setSize(impl.scale_in(44), impl.scale_in(24))
        impl.native.setThumbTintList(None)
        impl.native.setTrackTintList(None)
        impl.native.setThumbDrawable(thumb)
        impl.native.setTrackDrawable(track)
        impl.native.jumpDrawablesToCurrentState()
    elif hasattr(impl, '_eink_switch_style'):
        thumb, track, thumb_tint, track_tint = impl._eink_switch_style
        impl.native.setThumbDrawable(thumb)
        impl.native.setTrackDrawable(track)
        impl.native.setThumbTintList(thumb_tint)
        impl.native.setTrackTintList(track_tint)
        del impl._eink_switch_style
