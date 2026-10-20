"""Workspaces retain final palette/pressed state while amortizing native styling."""
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch

from logisticsmobile import appearance


class WorkspaceSurfacesTests(TestCase):
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
