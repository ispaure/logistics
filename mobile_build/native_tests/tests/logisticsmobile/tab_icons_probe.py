"""Exercise the actual iOS tab icons through backend item reconstruction."""
import asyncio
import json
import os
from pathlib import Path
import traceback

import toga

from mobile.app import LogisticsMobile
from tests.logisticsmobile.fixtures import capture_window


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'isolated-tab-icons'
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        output = Path(self.paths.cache) / 'tab-icons-evidence'
        output.mkdir(exist_ok=True)
        report = dict(success=False, probe_revision='retained-tab-icons-v1', pid=os.getpid(),
            source=json.loads((Path(__file__).parent / 'source.json').read_text()), samples=[])
        try:
            await asyncio.sleep(1)
            host = self.native_host
            adapter = host.adapter

            async def snapshot(name):
                await asyncio.sleep(.3)
                items = [navigation.tabBarItem for navigation in adapter.navigation]
                default = toga.Icon.OPTION_CONTAINER_DEFAULT_TAB_ICON._impl.native
                sample = dict(name=name, titles=[str(item.title) for item in items],
                    default_stars=[bool(item.image.isEqual(default)) for item in items],
                    retained_icons=[item.icon is not None for item in host.root.content],
                    model_images_match=[bool(native.image.isEqual(item.icon._impl.native)) if item.icon else False
                        for native, item in zip(items, host.root.content)])
                report['samples'].append(sample)
                await capture_window(self, output / (name + '.png'))

            await snapshot('cold-launch')
            # Toga recreates UITabBarItem from OptionItem.icon on a title/icon
            # update. Native-only image assignments must survive this boundary.
            for item, label in zip(host.root.content, host.labels):
                item.text = label
            await snapshot('rebuilt-items')
            for item in host.root.content:
                item.icon = item.icon
            await snapshot('reapplied-icons')
            for name, show in (('workspaces', self.show_locations),
                               ('documents', self.show_documents_hub),
                               ('settings', self.show_settings), ('home', self.show_home)):
                show()
                await snapshot(name)
            for mode in (1, 2):
                self.main_window._impl.native.overrideUserInterfaceStyle = mode
                self.refresh_native_theme()
                await snapshot('theme-' + str(mode))
            assert not any(any(sample['default_stars']) for sample in report['samples']), report['samples']
            assert all(all(sample['retained_icons']) for sample in report['samples'])
            assert all(all(sample['model_images_match']) for sample in report['samples'])
            assert all(sample['titles'] == list(host.labels) for sample in report['samples'])
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))


def main():
    return Probe('Tab Icons Probe', 'io.github.ispaure.logisticstabiconsprobe')
