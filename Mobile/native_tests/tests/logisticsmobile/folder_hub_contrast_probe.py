"""Synthetic Android Folder Hub review; never loads credentials or user files."""
import asyncio
import json
from pathlib import Path
import traceback

from logisticsmobile.app import LogisticsMobile
from logisticsmobile.appearance import configure_android_eink
from .fixtures import capture_window


class FolderHubProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'isolated-folder-hub-review'
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        output = Path(self.paths.cache) / 'folder-hub-evidence'
        output.mkdir(exist_ok=True)
        report = {'success': False}
        try:
            self.show_cloud(present=False)
            choices = {}
            for name, sources in [('Books', ['Local', 'Remote']), ('Books-Reference', ['LocalCrypt', 'Remote']),
                                  ('Personal', ['Remote']), ('Studio', ['Remote']), ('Documents', ['Local'])]:
                copies = [dict(source=source, kind='local' if source == 'Local' else 'crypt' if source == 'LocalCrypt' else 'remote',
                               value=name, name=name, remote=name if source != 'Local' else None) for source in sources]
                choices[name] = dict(copies[0], copies=copies)
            owner = self.folder_controller()
            owner.folder_choices = lambda: choices
            owner.network_share_remotes = lambda: {'Studio'}
            self.preferences.values['android_eink'] = 'true'
            configure_android_eink(self)
            self.show_folder_picker(initialize=False)
            self.change_folder_source('rclone')
            await asyncio.sleep(.8)
            self.refresh_native_theme()
            await asyncio.sleep(.3)
            await capture_window(self, output / 'rclone.png')
            self.transfer_busy = True
            self.refresh_transfer_status()
            await asyncio.sleep(.2)
            await capture_window(self, output / 'rclone-transfer.png')
            for source in ('Local', 'Network shares'):
                self.change_folder_source(source)
                assert self.folder_source == source
                await asyncio.sleep(.3)
                await capture_window(self, output / (source.replace(' ', '-').lower() + '.png'))
            self.transfer_busy = False
            self.transfer_notification = True
            self.transfer_complete = True
            self.change_folder_source('rclone')
            await asyncio.sleep(.3)
            self.preferences.values['android_eink'] = 'false'
            configure_android_eink(self)
            self.refresh_native_theme()
            await asyncio.sleep(.3)
            await capture_window(self, output / 'slate.png')
            from features.rclone.mobile.storage_location import collection_path
            (collection_path(self.private_root) / 'Books').mkdir(parents=True, exist_ok=True)
            self.preferences.values['android_eink'] = 'true'
            configure_android_eink(self)
            self.refresh_native_theme()
            await self.show_files(local_root=True)
            assert self.file_browser.location_bar.parent_button.control_icon == 'back'
            await self.browser_file_location(('Local files', 'Books'))
            assert self.file_browser.location_bar.parent_button.control_icon == 'up'
            await asyncio.sleep(.3)
            await capture_window(self, output / 'local-path.png')
            await self.parent_file_folder()
            assert self.file_path == ''
            assert self.file_browser.location_bar.parent_button.control_icon == 'back'
            await asyncio.sleep(.3)
            await capture_window(self, output / 'local-root.png')
            await self.parent_file_folder()
            assert self.native_host.state.destination == 'files'
            assert not self.routes.screens['files']
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (output / 'report.json').write_text(json.dumps(report))
        print('FOLDER_HUB_PROBE=' + json.dumps(report), flush=True)


def main():
    FolderHubProbe('Folder Hub review', 'io.github.ispaure.logisticsfolderhubprobe').main_loop()
