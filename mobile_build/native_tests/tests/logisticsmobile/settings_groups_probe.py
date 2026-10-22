"""Isolated native grouped-settings review on phone, iPad and a Duo crease."""
import asyncio
import json
from pathlib import Path
import traceback

import toga
from mobile.app import LogisticsMobile
from tests.logisticsmobile.fixtures import capture_window


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'isolated-settings-groups'
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        from rubicon.objc import ObjCClass
        output = Path(self.paths.cache) / 'settings-groups-evidence'
        output.mkdir(exist_ok=True)
        result = dict(success=False, samples=[])
        try:
            await asyncio.sleep(.5)
            window = self.main_window._impl.native
            duo = 'Duo' in str(ObjCClass('UIDevice').currentDevice.name)
            if duo:
                preferences = ObjCClass('UIWindowSceneGeometryPreferencesIOS').alloc().initWithInterfaceOrientations(16)
                window.windowScene.requestGeometryUpdateWithPreferences(preferences, errorHandler=None)
                await asyncio.sleep(1)
                self._hinge_status = 2
            for mode in (1, 2):
                window.overrideUserInterfaceStyle = mode
                self.show_settings()
                await asyncio.sleep(.5)
                self.resize_workspace()
                nav = self.settings_navigation
                for button in nav.buttons.values():
                    assert button._impl.native.imageForState(0) is not None, 'Category icon disappeared'
                await capture_window(self, output / f'categories-{mode}.png')
                for title in nav.sections:
                    nav.choose(title)
                    self.settings_status.text = 'Preferences saved on this device.'
                    await asyncio.sleep(.15)
                    self.resize_workspace()
                    sample = dict(mode=mode, category=title, wide=nav.wide, controls=[])
                    viewport = nav.options[title]._impl.native
                    pane = viewport.convertRect(viewport.bounds, toView=window)
                    def inspect(widget):
                        if isinstance(widget, (toga.Label, toga.Button, toga.Switch, toga.Selection)):
                            native = widget._impl.native
                            rect = native.convertRect(native.bounds, toView=window)
                            item = dict(text=getattr(widget, 'text', ''), x=float(rect.origin.x),
                                        width=float(rect.size.width), height=float(rect.size.height))
                            sample['controls'].append(item)
                            assert item['x'] >= pane.origin.x - 1, item
                            assert item['x'] + item['width'] <= pane.origin.x + pane.size.width + 1, item
                            assert item['height'] > 0, item
                        for child in widget.children:
                            inspect(child)
                    inspect(nav.sections[title])
                    view = nav.options[title]
                    view.vertical_position = view.max_vertical_position
                    await asyncio.sleep(.05)
                    assert view.vertical_position == view.max_vertical_position
                    view.vertical_position = 0
                    if title in ('App', 'Read aloud', 'Text & Markdown'):
                        await capture_window(self, output / (title.replace(' ', '-').replace('&', 'and') + f'-{mode}.png'))
                    result['samples'].append(sample)
                    if not nav.wide:
                        self.routes.back()
            result['duo_crease_injected'] = duo
            result['success'] = True
        except BaseException:
            result['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(result, indent=2))


def main():
    return Probe('Settings Groups Review', 'io.github.ispaure.logisticssettingsgroupsreview')
