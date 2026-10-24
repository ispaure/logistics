"""Verify visible received storage and native intake in a disposable iOS QA app."""
import asyncio
import json
from pathlib import Path
import traceback

from mobile.app import LogisticsMobile
from mobile.incoming_files import inbox_path
from mobile.ios_storage import prepare_for_app
from .fixtures import capture_window


class ReceivedFilesProbe(LogisticsMobile):
    def startup(self):
        from types import SimpleNamespace
        self.storage_root = Path(self.paths.config).parent / 'Logistics'
        legacy = self.storage_root / 'Inbox'
        legacy.mkdir(parents=True, exist_ok=True)
        (legacy / 'legacy.txt').write_bytes(b'legacy native bytes')
        prepare_for_app(SimpleNamespace(paths=self.paths))
        super().startup()

    def on_running(self):
        if not getattr(self, '_received_probe_started', False):
            self._received_probe_started = True
            self.loop.create_task(self.probe())

    async def probe(self):
        output = Path(self.paths.cache) / 'received-files-evidence'
        output.mkdir(exist_ok=True)
        report = dict(success=False, backend=type(self._impl).__module__)
        try:
            from rubicon.objc import ObjCClass
            received = inbox_path(self.private_root)
            assert received == Path(self.paths.data) / 'Received Files'
            assert (received / 'legacy.txt').read_bytes() == b'legacy native bytes'
            assert (self.private_root / 'Inbox/legacy.txt').read_bytes() == b'legacy native bytes'
            report['migration_preserved_original'] = True
            await self.show_files(location=('Shared files', ''))
            names = {row['name'] for row in self.file_rows.values()}
            assert {'Local', 'Received Files'} <= names, names
            report['shared_documents_folders'] = sorted(names)
            row = next(row for row in self.file_rows.values() if row['name'] == 'Received Files')
            await self.browser_file_folder(row)
            assert {row['name'] for row in self.file_rows.values()} == {'legacy.txt'}
            report['browse_all_navigation'] = True
            source = output / 'native-received.txt'
            source.write_bytes(b'native received bytes')
            ObjCClass('LogisticsIncomingFiles').receiveURL(ObjCClass('NSURL').fileURLWithPath(str(source)))
            for _ in range(100):
                if (received / source.name).exists():
                    break
                await asyncio.sleep(.1)
            assert (received / source.name).read_bytes() == b'native received bytes'
            report['native_url_intake'] = True
            await self.show_files(location=('Received Files', ''))
            assert self.file_provider.root == received
            assert {row['name'] for row in self.file_rows.values()} == {'legacy.txt', source.name}
            await capture_window(self, output / 'received-files.png')
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))


def main():
    return ReceivedFilesProbe('Received Files QA', 'io.github.ispaure.logisticsreceivedfilesqa')
