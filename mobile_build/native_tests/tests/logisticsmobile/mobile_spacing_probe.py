"""Synthetic cross-platform checks for shared mobile content/outline geometry."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace as NS
import traceback

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from mobile import appearance
from mobile.control_icons import button_icons, icon_button
from mobile.hub_ui import HubUI
from mobile.palette import set_eink_enabled
from mobile.settings.forms import disclosure
from .fixtures import capture_window


class MobileSpacingProbe(toga.App):
    def startup(self):
        appearance.install_appearance(self)
        self.buttons = []
        self.content = toga.Box(style=Pack(direction=COLUMN, margin=16))
        facade = NS(workspace=NS(sessions={}), recent_opener=lambda session: lambda widget: None,
                    session_opener=lambda key: lambda widget: None,
                    session_closer=lambda key: lambda widget: None)
        facade.document_button_icons = lambda button, session: button_icons(button, [
            ('storage_remote', 'Cloud'), ('storage_crypt', 'Locked')])
        session = NS(id='synthetic', kind='text')
        summary = ('A long synthetic recent document with an extension.txt', 'text', [])
        for label, row in (('Home / Documents recent and saved', HubUI.recent_row(facade, session, summary)),
                           ('Documents open', HubUI.session_panel(facade, session, summary=summary, close=True))):
            self.content.add(toga.Label(label, style=Pack(margin_top=12)), row)
            self.buttons.append(row.children[0].children[0])
        settings = appearance.list_button(toga.Button('Connection and storage settings', style=Pack(height=52)))
        button_icons(settings, [('preferences', 'Preferences')])
        disclosure(settings)
        self.buttons.append(settings)
        self.content.add(toga.Label('Settings disclosure', style=Pack(margin_top=12)), settings)
        toolbar = toga.Box(style=Pack(direction=ROW, margin_top=12))
        for name in ('back', 'find', 'play', 'skip_back', 'more'):
            button = icon_button(name, name)
            toolbar.add(button)
            self.buttons.append(button)
        self.content.add(toga.Label('Browser / reader / speech controls'), toolbar)
        plain = toga.Button('An ordinary outlined action', style=Pack(height=48, margin_top=12))
        self.buttons.append(plain)
        self.content.add(plain)
        self.main_window = toga.MainWindow(title='Mobile spacing QA')
        self.main_window.content = self.content
        self.main_window.show()

    def on_running(self):
        self.loop.create_task(self.check())

    def geometry(self):
        result = []
        android = type(self._impl).__module__.startswith('toga_android.')
        for button in self.buttons:
            native = button._impl.native
            if android:
                bounds = getattr(button._impl, '_control_drawable', None)
                if bounds is not None:
                    bounds = bounds.getBounds()
                    assert native.getPaddingLeft() >= button._impl.scale_in(8)
                    assert native.getPaddingLeft() + bounds.width() < native.getWidth()
                result.append([native.getLeft(), native.getTop(), native.getWidth(), native.getHeight(),
                               native.getPaddingLeft(), native.getPaddingTop(), native.getPaddingRight(),
                               native.getPaddingBottom(), float(native.getTextSize())])
            else:
                native.layoutIfNeeded()
                frame, insets = native.frame, native.contentEdgeInsets
                image = native.imageRectForContentRect(native.contentRectForBounds(native.bounds))
                title = native.titleRectForContentRect(native.contentRectForBounds(native.bounds))
                if native.imageForState(0) is not None:
                    assert image.origin.x >= 7, (button.text, image)
                    assert image.origin.y >= 1, (button.text, image)
                    assert image.origin.y + image.size.height <= native.bounds.size.height - 1
                    if button.text:
                        assert image.origin.x + image.size.width <= title.origin.x + 1
                if getattr(button, '_settings_disclosure', False):
                    assert title.origin.x + title.size.width <= native.bounds.size.width - 31
                result.append([float(frame.origin.x), float(frame.origin.y), float(frame.size.width),
                               float(frame.size.height), float(insets.left), float(insets.right),
                               float(native.titleLabel.font.pointSize)])
        return result

    async def check(self):
        output = Path(self.paths.cache) / 'mobile-spacing'
        output.mkdir(exist_ok=True)
        result = {'success': False, 'modes': {}}
        try:
            android = type(self._impl).__module__.startswith('toga_android.')
            result['platform'] = 'android' if android else 'ios'
            for width in (320, 600):
                self.content.style.width = width
                baseline = None
                for mode in ('regular', 'contrast', 'regular-again') if android else ('light', 'dark', 'light-again'):
                    if android:
                        set_eink_enabled(mode == 'contrast')
                    else:
                        self.main_window._impl.native.overrideUserInterfaceStyle = 2 if mode == 'dark' else 1
                    appearance.refresh_appearance(self)
                    await asyncio.sleep(.5)
                    geometry = self.geometry()
                    if baseline is None:
                        baseline = geometry
                    assert geometry == baseline, 'theme changed content geometry'
                    result['modes'][str(width) + '-' + mode] = geometry
                    await capture_window(self, output / (str(width) + '-' + mode + '.png'))
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(result, indent=2))
        print('MOBILE_SPACING=' + json.dumps(result), flush=True)


def main():
    MobileSpacingProbe('Mobile spacing QA', 'io.github.ispaure.logisticsmobilespacingqa').main_loop()
