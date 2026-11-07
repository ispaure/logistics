"""Durable provider locations through the real mobile host and a new process."""

import asyncio
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from mobile.document_sources import _reopen_file
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
from mobile_build.tests.support.app import mobile_app
from mobile_build.tests.support.pdf import PDF, native_pdf
from services.documents.mobile_storage import open_provider_document

TEST_STAGE = TestStage.REGRESSION


async def close_reader(app, owner):
    app.request_reader_close(owner.session.id)
    async with asyncio.timeout(5):
        while owner.session.id in app.workspace.sessions:
            await asyncio.sleep(.01)


def read_checkpoints(root):
    """Child process enters through Home after the parent opened through Local."""
    with mobile_app(root=root) as app, patch('features.pdf.document.PDFDocument.open', native_pdf):
        async def exercise():
            for suffix in ('.epub', '.cbz', '.zip', '.pdf'):
                path = root / 'LocalFiles' / 'Shelf' / ('Fixture' + suffix)
                assert await _reopen_file(app, dict(type='local', path=str(path)))
                owner = app.private_sessions.active
                assert owner._provider_displayed_index == (0 if suffix == '.epub' else 1)
                if suffix == '.epub':
                    assert owner.provider_epub_view.offset == int((root / 'expected-offset').read_text())
                    assert owner.provider_epub_view.text.value.startswith('🐈')
                await close_reader(app, owner)
        app.loop.run_until_complete(exercise())


class MobileProviderCheckpointTests(TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.shelf = self.root / 'LocalFiles' / 'Shelf'
        self.shelf.mkdir(parents=True)
        make_books(self.shelf, chapter_text='<p>' + '🐈 Read this passage. ' * 250 + '</p>')
        (self.shelf / 'Fixture.zip').write_bytes((self.shelf / 'Fixture.cbz').read_bytes())
        (self.shelf / 'Fixture.pdf').write_bytes(PDF)

    def test_page_and_passage_survive_a_separate_process(self):
        with mobile_app(root=self.root) as app, patch('features.pdf.document.PDFDocument.open', native_pdf):
            async def exercise():
                provider = LocalFiles(self.shelf.parent)
                for suffix in ('.epub', '.cbz', '.zip', '.pdf'):
                    self.assertTrue(await open_provider_document(app, provider, 'Shelf/Fixture' + suffix))
                    owner = app.private_sessions.active
                    if suffix == '.epub':
                        # Land at a Unicode character boundary measured in UTF-16.
                        panel = owner.provider_epub_view
                        offset = next(value for value, char in zip(panel.units, panel.chapter.text)
                                      if value >= 1234 and char == '🐈')
                        panel.seek(offset)
                        self.assertEqual(panel.offset, offset)
                        (self.root / 'expected-offset').write_text(str(offset))
                    else:
                        await owner.move_private_page(1)
                        self.assertEqual(owner._provider_displayed_index, 1)
                    await close_reader(app, owner)
            app.loop.run_until_complete(exercise())
        result = subprocess.run([sys.executable, __file__, str(self.root)], check=False,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_failed_page_and_background_keep_the_last_displayed_pdf(self):
        from unittest.mock import PropertyMock
        path = self.shelf / 'Fixture.pdf'
        with mobile_app(root=self.root) as app, patch('features.pdf.document.PDFDocument.open', native_pdf):
            async def exercise():
                self.assertTrue(await _reopen_file(app, dict(type='local', path=str(path))))
                owner = app.private_sessions.active
                await owner.move_private_page(1)
                with patch.object(type(owner), 'provider_page_content', new_callable=PropertyMock,
                                  return_value=lambda *_: (_ for _ in ()).throw(ValueError('Cannot decode'))):
                    await owner.move_private_page(2)
                self.assertEqual(owner._provider_displayed_index, 1)
                self.assertEqual(owner.crypt_page.value, owner.crypt_reader.labels[1])
                app.screen_privacy.conceal()
                await owner._provider_progress.flush()
                app.screen_privacy.reveal()
                await close_reader(app, owner)
                self.assertTrue(await _reopen_file(app, dict(type='local', path=str(path))))
                self.assertEqual(app.private_sessions.active._provider_displayed_index, 1)
                await close_reader(app, app.private_sessions.active)
            app.loop.run_until_complete(exercise())

    def test_rich_epub_waits_for_the_webview_to_confirm_a_seek(self):
        from mobile_build.tests.support.readers import MemoryWebView
        path = self.shelf / 'Fixture.epub'
        with mobile_app(root=self.root) as app, patch(
                'features.books.mobile.provider_reader.private_webview_supported', return_value=True), patch(
                'features.books.mobile.provider_reader.PrivateWebView', MemoryWebView):
            async def exercise():
                reference = dict(type='local', path=str(path))
                self.assertTrue(await _reopen_file(app, reference))
                owner = app.private_sessions.active
                progress, panel = owner._provider_progress, owner.provider_epub_view
                self.assertFalse(panel.position_ready)
                self.assertIsNone(progress.pending)
                panel.seek(1234)
                self.assertIsNone(progress.pending)
                panel.event('position', 1234)  # Acknowledgement from this WebView.
                self.assertEqual(progress.last_location['offset'], 1234)
                self.assertIsNotNone(progress.pending)
                await close_reader(app, owner)
                self.assertTrue(await _reopen_file(app, reference))
                owner = app.private_sessions.active
                self.assertEqual(owner.provider_epub_view.offset, 1234)
                self.assertFalse(owner.provider_epub_view.position_ready)
                self.assertIsNone(owner._provider_progress.pending)
                owner.provider_epub_view.event('position', 1234)
                self.assertIsNone(owner._provider_progress.pending)
                await close_reader(app, owner)

            app.loop.run_until_complete(exercise())

    def test_read_only_scenes_share_observation_order(self):
        import toga
        path = self.shelf / 'Fixture.pdf'
        with mobile_app(root=self.root) as app, patch('features.pdf.document.PDFDocument.open', native_pdf):
            manager = app.scene_manager
            manager.window_class = toga.Window
            child = manager.make_host('b' * 32)

            async def exercise():
                reference = dict(type='local', path=str(path))
                self.assertTrue(await _reopen_file(app, reference))
                self.assertTrue(await _reopen_file(child, reference))
                first, second = app.private_sessions.active, child.private_sessions.active
                self.assertEqual(first.session.identity, second.session.identity)
                self.assertTrue(first.session.shared_read)
                self.assertTrue(second.session.shared_read)
                await first.move_private_page(2)
                await second.move_private_page(1)
                # Closing the older window must not make page 3 newer again.
                await close_reader(app, first)
                await close_reader(child, second)
                self.assertTrue(await _reopen_file(app, reference))
                self.assertEqual(app.private_sessions.active._provider_displayed_index, 1)
                await close_reader(app, app.private_sessions.active)

            try:
                app.loop.run_until_complete(exercise())
            finally:
                manager.disconnect(child)

    def test_localcrypt_uses_only_the_credential_cipher_for_durable_progress(self):
        import base64
        import os
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from features.rclone.localcrypt.mobile.resources import CryptFiles
        from mobile_build.tests.support.localcrypt import ReaderClient
        from services.documents.progress import ProgressMode

        class Client(ReaderClient):
            # Exercise the production mobile credential transport with an
            # authenticated host fixture in place of the native ZIP service.
            package_records = ({'saved': False, 'document_cache_id': 'fixture-cache',                                'package_name': 'fixture.zip', 'remotes': ['Secret'],
                                'crypt_identities': {'Secret': ReaderClient.identity},
                                'identities': {'Secret': ReaderClient.connection}},)

            def request(self, action, **values):
                if action not in {'document_lists_open', 'document_lists_seal'}:
                    return super().request(action, **values)
                assert values['id'] == 'fixture-cache'
                cipher = AESGCM(b'f' * 32)
                data = base64.b64decode(values['data'])
                if action == 'document_lists_seal':
                    nonce = os.urandom(12)
                    result = nonce + cipher.encrypt(nonce, data, None)
                else:
                    result = cipher.decrypt(data[:12], data[12:], None)
                return base64.b64encode(result).decode()

        key = 'PrivateShelf/ProtectedBook.epub'
        for initialize in (True, False):
            with mobile_app(root=self.root) as app:
                app.cloud_client = Client()
                provider = CryptFiles(self.root / 'LocalCryptFolders', app.cloud_client, 'Secret')
                if initialize:
                    stored = provider._physical(key)
                    stored.parent.mkdir(parents=True, exist_ok=True)
                    stored.write_bytes((self.shelf / 'Fixture.epub').read_bytes()[::-1])

                async def exercise():
                    self.assertTrue(await open_provider_document(app, provider, key))
                    owner = app.private_sessions.active
                    self.assertIs(owner._provider_progress.state.mode, ProgressMode.ENCRYPTED)
                    if initialize:
                        await owner.move_private_page(1)
                        owner.toggle_private_bookmark()
                    else:
                        self.assertEqual(owner._provider_displayed_index, 1)
                        self.assertIn((1, 0), owner.epub_session_bookmarks)
                    await close_reader(app, owner)

                app.loop.run_until_complete(exercise())
        positions = self.root / 'ReaderPositions'
        self.assertFalse((positions / 'Local').exists())
        self.assertTrue(list(positions.rglob('*.zip')))
        for path in [*positions.rglob('*.zip'), *(self.root / 'ReaderBookmarks').rglob('*.zip')]:
            data = path.read_bytes()
            self.assertNotIn(b'ProtectedBook', data)
            self.assertNotIn(b'two.xhtml', data)

    def test_metadata_only_epub_change_keeps_utf16_locator(self):
        from zipfile import ZipFile
        path = self.shelf / 'Fixture.epub'
        with mobile_app(root=self.root) as app:
            async def exercise():
                reference = dict(type='local', path=str(path))
                self.assertTrue(await _reopen_file(app, reference))
                owner = app.private_sessions.active
                owner.provider_epub_view.seek(125)
                expected = owner.provider_epub_view.offset
                await close_reader(app, owner)
                with ZipFile(path) as archive:
                    entries = {name: archive.read(name) for name in archive.namelist()}
                entries['book.opf'] = entries['book.opf'].replace(b'Native Fixture', b'Edited title')
                with ZipFile(path, 'w') as archive:
                    for name, data in entries.items():
                        archive.writestr(name, data)
                self.assertTrue(await _reopen_file(app, reference))
                owner = app.private_sessions.active
                self.assertEqual(owner.crypt_reader.book.title, 'Edited title')
                self.assertEqual(owner.provider_epub_view.offset, expected)
                await close_reader(app, owner)
            app.loop.run_until_complete(exercise())


if __name__ == '__main__':
    read_checkpoints(Path(sys.argv[1]))
