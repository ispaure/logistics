"""Review command affordances in a disposable iOS/Android workspace."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
import traceback
from pathlib import Path

import toga
from mobile.app import LogisticsMobile
from mobile.appearance import refresh_appearance
from mobile.palette import set_eink_enabled
from tests.logisticsmobile.fixtures import capture_window


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'isolated-command-workspace'
        try:
            super().startup()
        except BaseException:
            (Path(self.paths.cache) / 'command-startup-error.txt').write_text(traceback.format_exc())
            raise

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        output = Path(self.paths.cache) / 'command-evidence'
        output.mkdir(exist_ok=True)
        report = dict(success=False, checks=[])
        apple = type(self._impl).__module__.startswith('toga_iOS.')
        try:
            for mode in ('light', 'dark'):
                if apple:
                    self.main_window._impl.native.overrideUserInterfaceStyle = 1 if mode == 'light' else 2
                else:
                    from android.app import UiModeManager
                    from android.content import Context
                    self._impl.native.getSystemService(Context.UI_MODE_SERVICE).setApplicationNightMode(
                        UiModeManager.MODE_NIGHT_NO if mode == 'light' else UiModeManager.MODE_NIGHT_YES)
                await asyncio.sleep(.4)
                refresh_appearance(self)
                for name, show in (('home', self.show_home), ('documents', self.show_documents_hub),
                                   ('chat', self.show_chat), ('settings', self.show_settings),
                                   ('folders', self.show_locations)):
                    show()
                    await asyncio.sleep(.4)
                    await capture_window(self, output / f'{name}-{mode}.png')
                for button in (*self.home_actions.children, self.chat_setup):
                    self.assert_command(button, apple)
                # A long title can shrink inside the border, and disabling or
                # recolouring must not lose either its boundary or callback.
                command = toga.Button('Open a document with a long descriptive name',
                                      on_press=lambda widget: None)
                callback = command.on_press
                command.enabled = False
                command._impl.set_color(command.style.color)
                self.assert_command(command, apple)
                assert not command.enabled and command.on_press is callback
                command.enabled = True
                self.assert_command(command, apple)
                report['checks'].append(mode + '-commands-and-disabled-state')
            if not apple:
                set_eink_enabled(True)
                refresh_appearance(self)
                self.show_home()
                await asyncio.sleep(.4)
                for button in self.home_actions.children:
                    self.assert_command(button, False)
                await capture_window(self, output / 'home-eink.png')
                report['checks'].append('eink-commands')
                set_eink_enabled(False)
                refresh_appearance(self)
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))

    @staticmethod
    def assert_command(button, apple):
        impl = button._impl
        assert impl._surface_roles == ('surface', 'text', True), (button.text, impl._surface_roles)
        if apple:
            from rubicon.objc import CGPoint
            assert impl.native.layer.borderWidth == 1, button.text
            assert impl.native.configuration is None, button.text
            assert not impl.native.isSelected(), button.text
            bounds = impl.native.bounds.size
            if button.enabled and bounds.width > 52 and bounds.height > 0:
                for x in (2, bounds.width - 2):
                    assert impl.native.pointInside(CGPoint(x, bounds.height / 2), withEvent=None), button.text
        else:
            assert not impl.native.isSelected(), button.text
            assert impl.native.getBackground() is not None, button.text


def main():
    return Probe('Command Buttons Probe', 'io.github.ispaure.logisticscommandprobe')
