"""Workspaces retain final palette/pressed state while amortizing native styling."""
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch

from logisticsmobile import appearance


class WorkspaceSurfacesTests(TestCase):
    def test_ios_icon_refresh_and_repaint_keep_disclosure_space(self):
        from logisticsmobile.control_icons import button_icons
        class Impl:
            __module__ = 'toga_iOS.widgets.button'
        impl = Impl()
        impl.native = MagicMock()
        impl._content_trailing_inset = 32
        button = NS(_impl=impl, on_press=lambda: None)
        impl.interface = button
        bridge = NS(ObjCClass=lambda name: NS(mainScreen=NS(scale=2)),
                    UIEdgeInsets=lambda *values: values)
        with patch.dict('sys.modules', {'rubicon.objc': bridge}), patch(
                'logisticsmobile.control_icons._apple_button_image', return_value=object()), patch.object(
                appearance, 'apple_color', return_value=MagicMock()):
            button_icons(button, [('storage_local', 'Local')])
            self.assertEqual(impl.native.contentEdgeInsets, (0, 12, 0, 32))
            appearance.surface(button, background='transparent')
            self.assertEqual(impl.native.contentEdgeInsets, (0, 12, 0, 32))

    def test_startup_labels_do_not_gain_tight_high_contrast_borders(self):
        from logisticsmobile.startup import StartupScreen
        screen = StartupScreen()
        labels = [screen.status, screen.detail, screen.view.children[0].children[0]]
        self.assertTrue(all(not label._impl._surface_eink_outlined for label in labels))

    def test_background_replacement_preserves_asymmetric_content_padding(self):
        class Native:
            padding = (12, 6, 32, 8)
            def getPaddingLeft(self): return self.padding[0]
            def getPaddingTop(self): return self.padding[1]
            def getPaddingRight(self): return self.padding[2]
            def getPaddingBottom(self): return self.padding[3]
            def setBackground(self, drawable):
                # Android applies drawable-supplied padding on replacement.
                self.padding = (0, 0, 0, 0)
            def setPadding(self, *padding): self.padding = padding
        native = Native()
        for _ in range(3):
            appearance._set_android_background(native, object())
            self.assertEqual(native.padding, (12, 6, 32, 8))

    def test_nested_offscreen_style_batch_applies_only_final_roles(self):
        class Impl:
            __module__ = 'toga_android.widgets.button'
        class Colors:
            def __new__(cls, states, colors):
                return NS(states=states, colors=colors)
        impl = Impl()
        impl.native = MagicMock()
        impl.native.getResources().getConfiguration().uiMode = 0x10
        impl.scale_in = lambda value: value
        button = NS(_impl=impl, on_press=lambda: None)
        impl.interface = button
        with patch.object(appearance, '_android_surface_resources', return_value=(
                NS(attr=NS(state_enabled=1)), Colors, None, None)), patch.object(
                appearance, '_android_background', return_value=object()) as background:
            with appearance.batch_surfaces():
                appearance.surface(button, radius=8, foreground='muted')
                with appearance.batch_surfaces():
                    appearance.surface(button, radius=4, background='alternate')
                appearance.surface(button, radius=0, background='transparent', foreground='text')
                background.assert_not_called()
            self.assertEqual(background.call_count, 1)
            self.assertEqual(background.call_args.kwargs['background'], 0)
            self.assertEqual(background.call_args.kwargs['radius'], 0)
            self.assertEqual(impl.native.setBackground.call_count, 1)
            tint = impl.native.setTextColor.call_args.args[0]
            self.assertEqual(tint.colors, [appearance.argb(appearance.LIGHT['muted']),
                                           appearance.argb(appearance.LIGHT['text'])])

    def test_cached_background_templates_never_share_mutable_drawables(self):
        created = []
        class State:
            def __init__(self, values):
                self.values = values
            def newDrawable(self):
                clone = object.__new__(Gradient)
                clone.values = deepcopy(self.values)
                return clone
        class Gradient:
            def __init__(self):
                self.values = {}
                created.append(self)
            def setColor(self, value):
                self.values['color'] = value
            def setCornerRadius(self, value):
                self.values['radius'] = value
            def setStroke(self, width, color):
                self.values['stroke'] = width, color
            def getConstantState(self):
                return State(deepcopy(self.values))
            def mutate(self):
                return self
        types = (None, object, Gradient, object)
        args = dict(background=1, radius=8, stroke=1, border=2, hover=3, button=False)
        first = appearance._android_background(types, **args)
        second = appearance._android_background(types, **args)
        self.assertEqual(len(created), 1)
        self.assertIsNot(first, second)
        first.setColor(99)
        self.assertEqual(second.values, {'color': 1, 'radius': 8, 'stroke': (1, 2)})
        changed = appearance._android_background(types, **dict(args, background=4, radius=16))
        self.assertEqual(len(created), 2)
        self.assertEqual(changed.values['color'], 4)
        self.assertEqual(changed.values['radius'], 16)
