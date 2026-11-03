"""Focused native accent controls and palette invariants on disposable apps."""
import asyncio
import json
from pathlib import Path
import traceback

from commonUtils.testing.stages import TestStage
from mobile.app import LogisticsMobile
from . import start_native_check
from .fixtures import capture_window

TEST_STAGE = TestStage.EXTENDED


def apple_color_sample(native, color, expected):
    """Read UIKit's resolved channels, including alpha and inherited dimming."""
    from ctypes import byref, c_double
    channels = [c_double() for _ in range(4)]
    resolved = color.resolvedColorWithTraitCollection(native.traitCollection)
    assert resolved.getRed(byref(channels[0]), green=byref(channels[1]),
                           blue=byref(channels[2]), alpha=byref(channels[3]))
    rgba = [value.value for value in channels]
    wanted = [int(expected[index:index + 2], 16) / 255 for index in (1, 3, 5)] + [1.0]
    assert all(abs(actual - target) < 1 / 255 for actual, target in zip(rgba, wanted)), (rgba, wanted)
    return dict(expected=expected, rgba=rgba, tint_adjustment=int(native.tintAdjustmentMode))


class AccentProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'accent-fixture'
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).check)

    async def check(self):
        result = dict(success=False, samples=[])
        try:
            if getattr(self, 'startup_task', None) is not None:
                await asyncio.shield(self.startup_task)
            from mobile.palette import LIGHT, DARK
            before = [dict(colors) for colors in (LIGHT, DARK)]
            self.show_settings()
            self.settings_navigation.choose('Appearance')
            await asyncio.sleep(.5)
            controls = self.accent_controls
            apple = type(self._impl).__module__.startswith('toga_iOS.')
            cases = [(f'{name}-{mode}', hue, saturation, mode)
                     for mode in ((1, 2) if apple else (0,))
                     for name, hue, saturation in (('green', 150, 75), ('purple', 249, 100))]
            evidence = Path(self.paths.cache) / 'viewer-layout'
            evidence.mkdir(exist_ok=True)
            for name, hue, saturation, mode in cases:
                if apple:
                    self.main_window._impl.native.overrideUserInterfaceStyle = mode
                    await asyncio.sleep(.4)
                    if name == 'green-2':
                        # Existing artwork must adapt without moving a slider
                        # or calling the application's repaint helper.
                        await capture_window(self, evidence / 'accent-dark-transition.png')
                controls.set_values(hue, saturation)
                controls.hue.on_release()
                await asyncio.sleep(.4)
                assert float(self.preferences.values['accent_hue']) == hue
                assert LIGHT['accent'] != '#2563eb'
                for original, colors in zip(before, (LIGHT, DARK)):
                    assert {key: value for key, value in original.items() if key not in ('accent', 'primary')} == {
                        key: value for key, value in colors.items() if key not in ('accent', 'primary')}
                sample = dict(name=name, light=LIGHT['accent'], dark=DARK['accent'])
                if apple:
                    native = controls.selected._impl.native
                    expected = DARK['accent'] if native.traitCollection.userInterfaceStyle == 2 else LIGHT['accent']
                    sample['preview'] = apple_color_sample(native, native.textColor, expected)
                    tab_bar = self.native_host.adapter.controller.tabBar
                    sample['tab_bar'] = apple_color_sample(tab_bar, tab_bar.tintColor, expected)
                result['samples'].append(sample)
                await capture_window(self, evidence / f'accent-{name}.png')
            controls.reset()
            assert LIGHT['accent'] == '#2563eb'
            assert DARK['accent'] == '#2563eb'
            result['success'] = True
        except BaseException:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'accent-result.json').write_text(json.dumps(result, indent=2))


def main():
    return AccentProbe('Accent QA', 'io.github.ispaure.logisticsstorageqa')
