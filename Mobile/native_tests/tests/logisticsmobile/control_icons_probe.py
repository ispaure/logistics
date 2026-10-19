"""Isolated control-icon review app; never reads a user workspace or remote."""
import asyncio, json, traceback
from pathlib import Path
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from logisticsmobile.control_icons import ICONS, icon_button, refresh_icons
from logisticsmobile.appearance import install_appearance
from tests.logisticsmobile.fixtures import capture_window

from logisticsmobile.app import LogisticsMobile

class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'isolated-icon-workspace'
        super().startup()

    def on_running(self):
        self.main_window.title = 'Mobile control icons'
        self.buttons = []
        rows = []
        for key in ICONS:
            button = icon_button(key, key.title(), on_press=lambda w: None)
            self.buttons.append(button)
            rows.append(toga.Box(children=[button, toga.Label(key.title(), style=Pack(flex=1))], style=Pack(direction=ROW)))
        panel = toga.Box(children=rows, style=Pack(direction=COLUMN, margin=20))
        self.show_view(panel, destination='documents', route='icon-probe', title='Mobile control icons')
        self.main_window.show()
        self.loop.create_task(self.probe())
    async def probe(self):
        output = Path(self.paths.cache) / 'icon-evidence'
        output.mkdir(exist_ok=True)
        report = {'success': False, 'probe_revision': 'appearance-v3'}
        try:
            backend = type(self._impl).__module__
            if backend.startswith('toga_android.'):
                from android.app import UiModeManager
                from android.content import Context
                self._impl.native.getSystemService(Context.UI_MODE_SERVICE).setApplicationNightMode(UiModeManager.MODE_NIGHT_NO)
                await asyncio.sleep(.7)
                self.refresh_native_theme()
            else:
                self.main_window._impl.native.overrideUserInterfaceStyle = 1
            await asyncio.sleep(1)
            for button in self.buttons:
                assert button.text == '', (button.control_icon, button.text)
                if backend.startswith('toga_iOS.'):
                    assert button._impl.native.imageForState(0) is not None
                    assert str(button._impl.native.accessibilityLabel) == button.accessible_name
                    assert button._impl.native.bounds.size.height >= 48
                else:
                    assert str(button._impl.native.getContentDescription()) == button.accessible_name
                    assert button._impl.native.getCompoundDrawablesRelative()[0] is not None
                    density = button._impl.native.getResources().getDisplayMetrics().density
                    assert button._impl.native.getHeight() / density >= 47.9
            await capture_window(self, output / 'light.png')
            self.buttons[0].enabled = False
            if backend.startswith('toga_android.'):
                from android.app import UiModeManager
                from android.content import Context
                self._impl.native.getSystemService(Context.UI_MODE_SERVICE).setApplicationNightMode(UiModeManager.MODE_NIGHT_YES)
                await asyncio.sleep(.7)
                self.refresh_native_theme()
                refresh_icons()
            else:
                self.main_window._impl.native.overrideUserInterfaceStyle = 2
            await asyncio.sleep(.5)
            await capture_window(self, output / 'dark-disabled.png')
            if backend.startswith('toga_android.'):
                from logisticsmobile.appearance import configure_android_eink
                self.preferences.values['android_eink'] = 'true'
                configure_android_eink(self)
                self.refresh_native_theme()
                await asyncio.sleep(.5)
                await capture_window(self, output / 'eink.png')
            report.update(success=True, backend=backend, icons=list(ICONS), checks=['native_images','accessibility_names','48_point_targets','dark_and_disabled_capture'])
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))

def main():
    return Probe('Control Icon Probe', 'io.github.ispaure.logisticsiconprobe')
