"""Real desktop encryption with a storage-neutral notebook editor/checkpoint."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.runtime.resources.local import LocalFiles
from features.rclone import executable, session
from local_crypt_fixture import crypt_fixture
from features.notebooks.notebook import Notebook, MAX_ARCHIVE
from features.notebooks.storage import NotebookDocument
from features.notebooks.editor import Editor
from services.documents.storage import DocumentResource


class NotebookResourceTests(unittest.TestCase):
    def test_same_notebook_adapter_saves_local_and_encrypted_binary_resources(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, executable.get_rclone_path()) as fixture:
            for provider in (LocalFiles(fixture.plain), fixture.provider):
                with self.subTest(private=provider.private):
                    book = Notebook.new('Private notebook sentinel')
                    book.members['opaque.bin'] = os.urandom(1100000)
                    original = book.to_bytes()
                    DocumentResource.publish(provider, 'draft.rmdoc', original, max_bytes=MAX_ARCHIVE, validate=Notebook.read)
                    with DocumentResource(provider, 'draft.rmdoc', max_bytes=MAX_ARCHIVE) as resource:
                        loaded = Notebook.read(resource.read())
                        document = NotebookDocument(loaded, resource=resource)
                        editor = Editor(loaded, document.checkpoint)
                        editor.apply(dict(op='stroke', points=[[20,30,.3],[40,50,.8]], tool=12, width=3))
                        editor.apply(dict(op='add-page'))
                        self.assertTrue(document.dirty)
                        self.assertEqual(resource.read(), original)
                        document.save()
                        self.assertFalse(document.dirty)
                        saved = Notebook.read(resource.read())
                        self.assertEqual(len(saved.pages), 2)
                        self.assertEqual(len(saved.page(0).strokes), 1)
                        self.assertEqual(saved.members['opaque.bin'], book.members['opaque.bin'])
                        if provider.private:
                            self.assertNotIn(b'Private notebook sentinel', provider.encrypted_path('draft.rmdoc').read_bytes())
                            self.assertIsNone(document.recovery)

    def test_browser_lease_release_preserves_document_and_revocation_retires_it(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, executable.get_rclone_path()) as fixture:
            provider = fixture.provider
            DocumentResource.publish(provider, 'draft.rmdoc', Notebook.new().to_bytes(), max_bytes=MAX_ARCHIVE)
            browser_release = provider.acquire()
            resource = DocumentResource(provider, 'draft.rmdoc', max_bytes=MAX_ARCHIVE)
            self.addCleanup(resource.close)
            book = Notebook.read(resource.read())
            document = NotebookDocument(book, resource=resource)
            browser_release()
            Editor(book, document.checkpoint).apply(dict(op='add-page'))
            document.save()
            encrypted = provider.encrypted_path('draft.rmdoc')
            original = encrypted.read_bytes()
            session.forget(fixture.context)
            with self.assertRaises(ValueError):
                resource.read()
            with self.assertRaises(ValueError):
                document.save()
            self.assertEqual(encrypted.read_bytes(), original)

    def test_failed_encrypted_save_keeps_draft_baseline_and_ciphertext(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, executable.get_rclone_path()) as fixture:
            provider = fixture.provider
            DocumentResource.publish(provider, 'draft.rmdoc', Notebook.new().to_bytes(), max_bytes=MAX_ARCHIVE)
            encrypted = provider.encrypted_path('draft.rmdoc')
            original = encrypted.read_bytes()
            with DocumentResource(provider, 'draft.rmdoc', max_bytes=MAX_ARCHIVE) as resource:
                document = NotebookDocument(Notebook.read(resource.read()), resource=resource)
                Editor(document.book, document.checkpoint).apply(dict(op='add-page'))
                baseline = resource.revision
                with patch.object(provider, 'replace_created', side_effect=OSError('publication failed')):
                    with self.assertRaisesRegex(OSError, 'publication failed'):
                        document.save()
                self.assertTrue(document.dirty)
                self.assertEqual(len(document.book.pages), 2)
                self.assertEqual(resource.revision, baseline)
                self.assertEqual(encrypted.read_bytes(), original)
                self.assertFalse(any(path.name.startswith('.save-') for path in Path(fixture.item.data).iterdir()))

    def test_private_browser_routes_notebooks_and_source_text_without_opening_thumbnails(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        release = Mock()
        provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: Path(path).name,
                                   acquire=lambda: release)
        browser = SimpleNamespace(provider=provider, closing=False, open_operation=SimpleNamespace(busy=False))
        with patch('services.documents.ui.notebooks.open_notebook_choice') as opening:
            self.assertEqual(CryptBrowserView._thumbnail(browser, 'sample.rmdoc', (64,64), lambda: False), b'')
            opening.assert_not_called()
            CryptBrowserView.open_document(browser, Path('/virtual/sample.rmdoc'))
            choice = opening.call_args.args[0]
            self.assertIs(choice.provider, provider)
            self.assertEqual(choice.path, 'sample.rmdoc')
            choice.close()
            release.assert_called_once()
        with patch('services.documents.ui.editors.open_editor_choice') as opening:
            CryptBrowserView.open_document(browser, Path('/virtual/settings.ini'))
            choice = opening.call_args.args[0]
            self.assertEqual(choice.path, 'settings.ini')
            choice.close()
