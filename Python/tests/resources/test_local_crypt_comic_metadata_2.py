"""Ciphertext mirror, streaming readers/editors, private UI and credential lifetime."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from tempfile import TemporaryDirectory
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from features.rclone.localcrypt import backend as local_crypt
from features.rclone.localcrypt import mapping as copy_mapping
from features.rclone import actions
from features.comics.library import ComicDocument
from features.comics.pages import ComicPages
from tests.local_crypt_fixture import crypt_fixture


from tests.resources.localcrypt_cases import LocalCryptCase


class LocalCryptComicMetadataTests(LocalCryptCase):
    def test_ciphertext_mirror_and_both_comic_layers_survive_edits_without_plaintext_files(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            self.assertEqual({row['name'] for row in f.provider.list()}, {'note.md', 'plain.cbz', 'encrypted.cbz', 'remoteConfig.ini', 'page.png'})
            self.assertEqual(f.provider.read_bytes('note.md'), f.original)
            f.provider.write_bytes('note.md', b'# Private fixture\n\nEdited locally.\n', expected=f.original)
            for name in ('plain.cbz', 'encrypted.cbz'):
                doc = ComicDocument(f.item.data / name, source=f.provider)
                self.assertEqual(ComicPages(doc.path, doc).read_page(0)[0], f.image)
                doc.save({'Title': 'Private metadata sentinel'})
                reopened = ComicDocument(doc.path, source=f.provider)
                self.assertEqual(reopened.info.get_field('Title'), 'Private metadata sentinel')
                self.assertEqual(ComicPages(doc.path, reopened).read_page(0)[0], f.image)
                self.assertEqual(reopened.password is not None, name == 'encrypted.cbz')
            for file in f.item.data.rglob('*'):
                if file.is_file():
                    data = file.read_bytes()
                    self.assertNotIn(b'Edited locally.', data)
                    self.assertNotIn(b'Private metadata sentinel', data)
                    self.assertNotIn(f.image, data)
            before = {str(path.relative_to(f.item.data)): path.read_bytes() for path in f.item.data.rglob('*') if path.is_file()}
            self.assertTrue(actions.push_to_cloud(local_crypt.LocalCryptFolder(f.item), f.context))
            after = {str(path.relative_to(f.cloud)): path.read_bytes() for path in f.cloud.rglob('*') if path.is_file()}
            self.assertEqual(before, after)  # No double encryption on upload.
            record = json.loads(f.item.record.read_text())
            self.assertEqual(set(record), {'schema', 'package', 'remote'})
            self.assertEqual(record['schema'], 2)
            self.assertEqual(f.item.data, f.root / 'Application Support' / 'Logistics' / 'LocalCrypt' / 'Secret')
            self.assertEqual(copy_mapping.for_path(f.item.data), f.item)
            self.assertNotIn('password', f.item.record.read_text())

    def test_private_comic_picker_owns_provider_and_reused_reader_releases_extra_choice(self):
        from commonUtils.runtime.resources.selection import ResourceChoice
        from commonUtils.ui.readers.reader_menus import RecentFiles
        from services.documents.ui.readers import open_reader_choice
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            released = []
            def choice(label):
                lease = f.provider.acquire()
                def release():
                    released.append(label)
                    lease()
                return ResourceChoice(f.provider, 'encrypted.cbz', release)
            with patch.object(RecentFiles, 'add', side_effect=AssertionError('Private comic wrote recents')):
                window = open_reader_choice(choice('original'), None, 'comic')
                self.assertIsNotNone(window)
                try:
                    self.wait(lambda: not window.busy and not window.page_cache.busy)
                    self.assertTrue(window.pages.document.private)
                    self.assertTrue(window.windowTitle().startswith('🕵️ Private - '))
                    from services.documents.reader_positions import PrivateComicState
                    self.assertIsInstance(window._state, PrivateComicState)
                    with self.assertRaises(PermissionError):
                        _ = window._state.state.cipher.identity
                    with patch('commonUtils.persistence.atomic_write_bytes', side_effect=AssertionError('Passwordless checkpoint wrote disk')):
                        window._state.save(0, window.pages.pages)
                    self.assertEqual(window._state.state.memory['page'], 0)
                    self.assertTrue(window.menus.shared.open_action.isEnabled())
                    self.assertEqual(released, [])
                    reused = open_reader_choice(choice('extra'), None, 'comic')
                    self.assertIs(reused, window)
                    self.assertEqual(released, ['extra'])
                finally:
                    self.wait(lambda: not window.busy and not window.page_cache.busy)
                    window.shutdown()
                    window.close()
                    self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
                    self.app.processEvents()
                self.assertEqual(released, ['extra', 'original'])
