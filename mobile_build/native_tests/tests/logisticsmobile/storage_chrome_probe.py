"""Disposable Android proof for collection storage, Legacy visibility and system bars."""
import asyncio
import json
from pathlib import Path
import struct
import traceback
import zlib
from uuid import uuid4
from zipfile import ZipFile

from commonUtils.runtime.resources.documents import LocalDocuments
from features.rclone.mobile.storage_location import CollectionFiles, collection_path, switch_location
from mobile.app import LogisticsMobile
from mobile.storage_ui import android_drives


class StorageChromeProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('storage-chrome-validation-' + uuid4().hex)
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        report = dict(success=False, cases=[])
        path = Path(self.paths.cache) / 'storage-chrome-result.json'
        try:
            from java import jclass
            ViewCompat = jclass('androidx.core.view.ViewCompat')
            Types = jclass('androidx.core.view.WindowInsetsCompat$Type')
            decor = self._impl.native.getWindow().getDecorView()
            await asyncio.sleep(.7)
            self.show_settings()
            assert self.show_legacy_choice.parent is not None
            self.show_legacy_choice.value = False
            assert not self.folder_path_visible('Books/Legacy-old')
            self.show_legacy_choice.value = True
            assert self.folder_path_visible('Books/Legacy-old')
            report['cases'].append('android_legacy_toggle')
            drives = android_drives(self)
            assert len(drives) > 1
            self.show_collection_storage()
            report['drives'] = {label: str(root) for label, root in drives.items()}
            report['cases'].append('native_storage_volume_settings')
            # A disposable app-specific external directory validates actual Android
            # filesystem behavior without granting broad storage permission.
            drive = Path(str(self._impl.native.getExternalFilesDir(None).getAbsolutePath())) / ('storage-proof-' + uuid4().hex)
            drive.mkdir(exist_ok=True)
            source = CollectionFiles(self.private_root).root
            (source / 'proof.txt').write_bytes(b'native copied bytes')
            collection_path(self.private_root, True).mkdir(exist_ok=True)
            (collection_path(self.private_root, True) / 'opaque').write_bytes(b'ciphertext proof')
            switch_location(self.private_root, drive)
            assert (collection_path(self.private_root) / 'proof.txt').read_bytes() == b'native copied bytes'
            assert (collection_path(self.private_root, True) / 'opaque').read_bytes() == b'ciphertext proof'
            report['cases'].append('native_external_copy_verified')
            comic = self.private_root / 'Fullscreen.cbz'
            def chunk(kind, data):
                return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
            png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
                   + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00\xff')) + chunk(b'IEND', b''))
            with ZipFile(comic, 'w') as archive:
                archive.writestr('page.png', png)
            record = self.reader_manager().catalog.library_store.import_book(LocalDocuments(), comic)
            assert await self.open_book(record['id'])
            owner = self.readers.active
            await asyncio.sleep(1)
            insets = ViewCompat.getRootWindowInsets(decor)
            assert not insets.isVisible(Types.statusBars()), 'Status bar remains visible'
            assert not insets.isVisible(Types.navigationBars()), 'Navigation bar remains visible'
            image = owner.book_content.children[0]._impl.native
            report['fullscreen_size'] = [int(image.getWidth()), int(image.getHeight())]
            report['window_size'] = [int(decor.getWidth()), int(decor.getHeight())]
            assert image.getHeight() >= decor.getHeight() - 2, str(report)
            report['cases'].append('native_comic_fills_window_and_hides_system_bars')
            owner.set_reading_mode(False)
            await asyncio.sleep(.7)
            assert ViewCompat.getRootWindowInsets(decor).isVisible(Types.statusBars())
            assert ViewCompat.getRootWindowInsets(decor).isVisible(Types.navigationBars())
            owner.set_reading_mode(True)
            await asyncio.sleep(.5)
            self.show_home()
            await asyncio.sleep(.7)
            assert ViewCompat.getRootWindowInsets(decor).isVisible(Types.statusBars())
            report['cases'].append('native_bars_restore_on_controls_and_route_exit')
            self.show_settings()
            await self.open_android_developer_settings()
            await asyncio.sleep(.7)
            report['cases'].append('developer_settings_intent_dispatched')
            report['success'] = True
        except Exception:
            traceback.print_exc()
            report['error'] = traceback.format_exc()
        report['backend'] = type(self._impl).__module__
        path.write_text(json.dumps(report, indent=2))
        print('STORAGE_CHROME_PROOF=' + json.dumps(report), flush=True)


def main():
    StorageChromeProbe('Logistics Mobile', 'io.github.ispaure.logisticsmobile').main_loop()
