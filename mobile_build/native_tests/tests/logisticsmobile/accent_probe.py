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
            if not apple:
                from android.os import SystemClock
                from android.view import MotionEvent
                from time import perf_counter
                from unittest.mock import patch
                from mobile.settings.accent import refresh_appearance
                result['android_drag'] = {}
                for slider_name, slider in (('hue', controls.hue), ('saturation', controls.saturation)):
                    native = slider._impl.native
                    density = native.getResources().getDisplayMetrics().density
                    assert native.getHeight() / density >= 64
                    assert native.getThumb().getIntrinsicWidth() / density >= 32
                    thumb, track = native.getThumb().hashCode(), native.getProgressDrawable().hashCode()
                    down = SystemClock.uptimeMillis()
                    left, right = native.getPaddingLeft(), native.getWidth() - native.getPaddingRight()
                    y = native.getHeight() / 2
                    elapsed = []
                    def touch(action, fraction):
                        event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action,
                                                   left + (right - left) * fraction, y, 0)
                        try:
                            started = perf_counter()
                            assert native.dispatchTouchEvent(event)
                            elapsed.append((perf_counter() - started) * 1000)
                        finally:
                            event.recycle()
                    with patch('mobile.settings.accent.refresh_appearance', wraps=refresh_appearance) as repaint:
                        touch(MotionEvent.ACTION_DOWN, (slider.value - slider.min) / (slider.max - slider.min))
                        for fraction in (.7, .75, .8, .85):
                            touch(MotionEvent.ACTION_MOVE, fraction)
                            await asyncio.sleep(.02)
                            assert controls._dragging
                            assert native.getThumb().hashCode() == thumb
                            assert native.getProgressDrawable().hashCode() == track
                            repaint.assert_not_called()
                        touch(MotionEvent.ACTION_UP, .85)
                        assert not controls._dragging
                        repaint.assert_called_once_with(self)
                    result['android_drag'][slider_name] = dict(touch_height_dp=native.getHeight() / density,
                        thumb_dp=native.getThumb().getIntrinsicWidth() / density,
                        event_ms=elapsed, artwork_retained_during_drag=True, refreshes_on_release=1)
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
                assert LIGHT['accent'] != '#3363cc'
                for original, colors in zip(before, (LIGHT, DARK)):
                    assert {key: value for key, value in original.items() if key not in ('accent', 'primary')} == {
                        key: value for key, value in colors.items() if key not in ('accent', 'primary')}
                sample = dict(name=name, light=LIGHT['accent'], dark=DARK['accent'])
                if apple:
                    tab_bar = self.native_host.adapter.controller.tabBar
                    expected = DARK['accent'] if tab_bar.traitCollection.userInterfaceStyle == 2 else LIGHT['accent']
                    sample['tab_bar'] = apple_color_sample(tab_bar, tab_bar.tintColor, expected)
                result['samples'].append(sample)
                await capture_window(self, evidence / f'accent-{name}.png')
            controls.reset()
            assert LIGHT['accent'] == '#3363cc'
            assert DARK['accent'] == '#3363cc'
            result['success'] = True
        except BaseException:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'accent-result.json').write_text(json.dumps(result, indent=2))


def main():
    return AccentProbe('Accent QA', 'io.github.ispaure.logisticsstorageqa')
