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
            for name, hue, saturation in (('green', 150, 75), ('purple', 285, 65)):
                controls.set_values(hue, saturation)
                controls.hue.on_release()
                await asyncio.sleep(.4)
                assert float(self.preferences.values['accent_hue']) == hue
                assert LIGHT['accent'] != '#2563eb'
                for original, colors in zip(before, (LIGHT, DARK)):
                    assert {key: value for key, value in original.items() if key not in ('accent', 'primary')} == {
                        key: value for key, value in colors.items() if key not in ('accent', 'primary')}
                result['samples'].append(dict(name=name, light=LIGHT['accent'], dark=DARK['accent']))
                await capture_window(self, Path(self.paths.cache) / f'accent-{name}.png')
            controls.reset()
            assert LIGHT['accent'] == '#2563eb'
            assert DARK['accent'] == '#75a7ff'
            result['success'] = True
        except BaseException:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'accent-result.json').write_text(json.dumps(result, indent=2))


def main():
    return AccentProbe('Accent QA', 'io.github.ispaure.logisticsstorageqa')
