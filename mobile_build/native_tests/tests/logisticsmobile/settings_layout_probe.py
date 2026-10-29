"""Disposable native Settings geometry checks, with explicit hinge injection."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

import toga
from mobile.app import LogisticsMobile
from . import start_native_check
from .settings import PROBE_ROTATION_SETTLE
from .rotation_checks import rotate


class SettingsLayoutProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('settings-layout-' + uuid4().hex)
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).probe)

    async def probe(self):
        from rubicon.objc import Block, objc_id
        from toga_iOS.libs import UIGraphicsImageRenderer
        from toga_iOS.images import nsdata_to_bytes
        output = Path(self.paths.cache) / 'settings-layout-probe'
        output.mkdir(exist_ok=True)
        report = {'success': False, 'samples': []}
        try:
            await asyncio.sleep(1)
            window = self.main_window._impl.native
            await rotate(self, 'landscape-right', settle=PROBE_ROTATION_SETTLE)
            report['observed_hinge_status'] = getattr(self, '_hinge_status', None)
            report['window'] = [float(window.bounds.size.width), float(window.bounds.size.height)]
            report['orientation'] = int(window.windowScene.interfaceOrientation)
            self._hinge_status = 2
            self.show_settings()
            await asyncio.sleep(.5)
            self.resize_workspace()
            await asyncio.sleep(.5)
            nav = self.settings_navigation
            for title in nav.sections:
                nav.choose(title)
                self.settings_status.text = 'Preferences saved automatically on this device; changes are ready.'
                await asyncio.sleep(.3)
                self.resize_workspace()
                await asyncio.sleep(.2)
                detail = nav.detail._impl.native
                pane = detail.convertRect(detail.bounds, toView=window)
                sidebar = nav.sidebar._impl.native
                left = sidebar.convertRect(sidebar.bounds, toView=window)
                sample = dict(category=title, join=float(left.origin.x + left.size.width),
                              expected=float(window.bounds.size.width / 2), controls=[])
                def inspect(widget):
                    if isinstance(widget, (toga.Label, toga.Button, toga.Switch, toga.Selection)):
                        native = widget._impl.native
                        rect = native.convertRect(native.bounds, toView=window)
                        item = dict(text=getattr(widget, 'text', ''), x=float(rect.origin.x),
                                    width=float(rect.size.width), height=float(rect.size.height))
                        sample['controls'].append(item)
                        assert item['x'] >= pane.origin.x - 1, item
                        assert item['x'] + item['width'] <= pane.origin.x + pane.size.width + 1, item
                        if isinstance(widget, (toga.Label, toga.Button)):
                            from rubicon.objc import ObjCClass, CGSize
                            ruler = ObjCClass('UILabel').new()
                            ruler.font = native.titleLabel.font if isinstance(widget, toga.Button) else native.font
                            for line in widget.text.split('\n'):
                                ruler.text = line
                                assert ruler.sizeThatFits(CGSize(100000, 100000)).width <= rect.size.width + 1, item
                    for child in widget.children:
                        inspect(child)
                inspect(nav.sections[title])
                renderer = UIGraphicsImageRenderer.alloc().initWithSize(window.bounds.size)
                def draw(context):
                    window.drawViewHierarchyInRect(window.bounds, afterScreenUpdates=True)
                (output / (title.replace(' ', '-').replace('&', 'and') + '.png')).write_bytes(
                    nsdata_to_bytes(renderer.PNGDataWithActions(Block(draw, None, objc_id))))
                report['samples'].append(sample)
                assert abs(sample['join'] - sample['expected']) <= 1, sample
                view = nav.options[title]
                view.vertical_position = view.max_vertical_position
                await asyncio.sleep(.1)
                assert view.vertical_position == view.max_vertical_position
                sample['bottom_reachable'] = True
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))


def main():
    SettingsLayoutProbe('Settings Probe', 'io.github.ispaure.logisticssettingsprobe').main_loop()
