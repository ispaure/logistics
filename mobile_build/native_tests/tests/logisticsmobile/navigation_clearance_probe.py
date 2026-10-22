"""Isolated iOS page geometry and screenshots with Duo rail/bottom adaptation.

Use this module's main in a disposable simulator probe bundle. Ordinary app
storage is never opened; screenshots/results live under the probe's cache.
"""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from mobile.app import LogisticsMobile


class NavigationClearanceProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('navigation-clearance-' + uuid4().hex)
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        from rubicon.objc import ObjCClass
        from .fixtures import capture_window
        report = {'success': False, 'samples': []}
        try:
            await asyncio.sleep(1)
            window = self.main_window._impl.native
            for orientation, mask in (('portrait', 2), ('landscape', 8), ('portrait-return', 2)):
                preferences = ObjCClass('UIWindowSceneGeometryPreferencesIOS').alloc().initWithInterfaceOrientations(mask)
                window.windowScene.requestGeometryUpdateWithPreferences(preferences, errorHandler=None)
                await asyncio.sleep(1)
                for name, show in (('home', self.show_home), ('documents', self.show_documents_hub),
                                   ('settings', self.show_settings), ('files', self.show_locations),
                                   ('chat', self.show_chat)):
                    show()
                    await asyncio.sleep(.5)
                    body = self.routes.body()
                    view = body.children[0]
                    container = view._impl.container
                    bar = self.native_host.adapter.controller.tabBar
                    rail = float(bar.bounds.size.height) > float(bar.bounds.size.width)
                    height = float(view._impl.native.frame.size.height)
                    available = float(container.height)
                    sample = dict(orientation=orientation, page=name, rail=rail,
                                  height=height, available_height=available,
                                  bottom_margin=view.style.margin_bottom,
                                  bar_width=float(bar.bounds.size.width),
                                  bar_height=float(bar.bounds.size.height))
                    report['samples'].append(sample)
                    assert height >= available * .6, sample
                    if rail:
                        assert view.style.margin_bottom <= 24, sample
                    await capture_window(self, self.storage_root / f'{orientation}-{name}.png')
            self.show_documents_hub()
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        report['backend'] = type(self._impl).__module__
        (Path(self.paths.cache) / 'navigation-clearance-result.json').write_text(json.dumps(report, indent=2))


def main():
    NavigationClearanceProbe('Logistics Mobile', 'io.github.ispaure.logisticsmobile').main_loop()
