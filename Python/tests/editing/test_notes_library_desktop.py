"""Real desktop Notes Library documents: lazy providers, navigation and revocation."""
from pathlib import Path
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.ui.notes_library import NotesLibraryWindow
from features.text_editor.notes_actions import actions
from models.folder_entry import FolderEntry
from models.local_folder import LocalFolder


class RemoteFiles(LocalFiles):
    private = remote_storage = True
    def __init__(self, root):
        super().__init__(root);self.calls=[];self.closed=False
    def list(self, path='', **kw):
        self.calls.append(path);return super().list(path, **kw)
    def _check_active(self):
        if self.closed:raise ValueError('Credentials revoked')
    def acquire(self):return self.close
    def close(self):self.closed=True


class NotesLibraryDesktopTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_real_localcrypt_and_crypt_remote_open_and_read_notes(self):
        from io import BytesIO
        from features.rclone import executable, session
        from features.rclone.remote_resources import RemoteResources
        from features.rclone.localcrypt.backend import CryptResources
        from tests.local_crypt_fixture import crypt_fixture
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone executable not installed')
        with self.temporary_directory() as directory, crypt_fixture(directory, binary) as fixture:
            fixture.provider.mkdir('.obsidian')
            fixture.provider.mkdir('Nested')
            fixture.provider.create_file('Nested/Next.md', BytesIO(b'# Nested note'))
            fixture.provider.create_file('Nested/Tech.md', BytesIO(b'# Tech'))
            from features.rclone.localcrypt.ui.views import CryptBrowserView
            with patch('features.rclone.executable.get_rclone_path', return_value=binary):
                view = CryptBrowserView(fixture.item)
            view.show()
            offer = view.notes_offer
            self.wait_until(lambda: offer.location is not None and not offer.progress.busy)
            self.assertIsNotNone(offer.candidate, offer.progress.message.text())
            self.assertFalse(offer.isHidden())
            view.close()
            # Seed the synthetic cloud crypt with the same vault marker and nested note.
            environment, source, destination = session.launch(
                fixture.context, str(fixture.item.data), str(fixture.cloud))
            from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
            run_bytes([str(binary), '--config', session.NULL_CONFIG,
                       'copy', '--create-empty-src-dirs', source, destination], environment=environment, max_output=0)
            for remote in (False, True):
                with self.subTest(remote=remote):
                    factory = (lambda: RemoteResources(fixture.context, 'Secret', binary=binary)) if remote else (
                        lambda: CryptResources(fixture.item, binary=binary))
                    window = NotesLibraryWindow(factory, 'Encrypted fixture', remote=remote)
                    window.show()
                    self.wait_until(lambda: not window.progress.busy)
                    self.assertIsNotNone(window.library, window.progress.message.text())
                    self.assertEqual(window.viewer.allow_edit, not remote)
                    self.assertEqual(window.viewer.edit_button.isChecked(), not remote)
                    self.assertIn('note.md', window.items)
                    window.open_note('note.md')
                    self.wait_until(lambda: not window.progress.busy)
                    self.assertIn('Original note', window.viewer.browser.toPlainText(), window.viewer.status.text())
                    self.assertEqual(len(window.storage.resources), 1)
                    url = window.viewer.browser.document().baseUrl().resolved(qt.QUrl('page.png'))
                    image = window.viewer.browser.document().resource(qt.QTextDocument.ResourceType.ImageResource, url)
                    self.assertFalse(image.isNull())
                    window.items['Nested'].setExpanded(True)
                    self.wait_until(lambda: not window.progress.busy)
                    window.open_note('Nested/Next.md')
                    self.wait_until(lambda: not window.progress.busy)
                    self.assertIn('Nested note', window.viewer.browser.toPlainText(), window.viewer.status.text())
                    window.viewer.follow_link(qt.QUrl('note.md'))
                    self.wait_until(lambda: not window.progress.busy)
                    self.assertEqual(window.storage.path, (window.provider.root / 'note.md').resolve(), window.viewer.status.text())
                    window.viewer.follow_link(qt.QUrl('Tech.md'))
                    self.wait_until(lambda: not window.progress.busy)
                    self.assertEqual(window.storage.path, (window.provider.root / 'Nested/Tech.md').resolve(), window.viewer.status.text())
                    window.open_note('Nested/Next.md')
                    self.wait_until(lambda: not window.progress.busy)
                    if not remote:
                        for mode in ('formatted', 'source'):
                            window.viewer.set_edit_mode(mode)
                            window.viewer.active_editor().insertPlainText('Edited ' + mode + '. ')
                            window.viewer.save_document()
                            self.wait_until(lambda: not window.progress.busy)
                            self.assertFalse(window.viewer.is_modified, window.viewer.status.text())
                            self.assertIn(('Edited ' + mode).encode(), fixture.provider.read_bytes('Nested/Next.md'))
                    from shiboken6 import isValid
                    provider = window.provider
                    session.forget(provider.context)
                    self.wait_until(lambda: not isValid(window) or window.locked)
                    self.assertEqual(window.storage.data, b'')
                    self.assertTrue(provider.closed)
                    if isValid(window):
                        window.close()

    def test_action_uses_only_selected_storage_context(self):
        from dataclasses import replace
        from features.text_editor.notes_actions import sources
        from features.rclone.desktop_service import service
        with self.temporary_directory() as directory:
            root = Path(directory)
            self.fixture(root)
            entry = FolderEntry('Notes', local=LocalFolder(root), remote_name='Notes',
                                remote_source='rclone', remote_context=root / 'keys.conf')
            with patch.object(service.remotes, 'open', side_effect=lambda location: LocalFiles(root)) as remote:
                local_actions = actions(replace(entry, storage_scope='local'))
                remote.assert_not_called()
                self.assertEqual([action.name for action in local_actions], ['Open as Notes Library'])
                cloud_actions = actions(replace(entry, storage_scope='remote'))
                remote.assert_called_once()
                self.assertEqual([action.name for action in cloud_actions], ['Open as Notes Library'])
                with patch('features.text_editor.ui.notes_library.open_notes') as opened:
                    cloud_actions[0].callback()
                    self.assertTrue(opened.call_args.kwargs['remote'])
                    local_actions[0].callback()
                    self.assertFalse(opened.call_args.kwargs['remote'])
            self.assertEqual([item[0] for item in sources(replace(entry, local=None, storage_scope='local'))], [])

    def test_workspace_library_starts_editing_and_saves_in_local_context(self):
        with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Discard):
            with self.temporary_directory() as directory:
                root = Path(directory)
                self.fixture(root)
                window = NotesLibraryWindow(lambda: LocalFiles(root), 'Notes')
                window.show()
                self.wait_until(lambda: not window.progress.busy)
                window.open_note('Home.md')
                self.wait_until(lambda: not window.progress.busy)
                self.assertTrue(window.viewer.allow_edit)
                self.assertTrue(window.viewer.edit_button.isChecked())
                window.viewer.set_edit_mode('source')
                window.viewer.editor.insertPlainText('Edited locally. ')
                window.viewer.save_document()
                self.wait_until(lambda: not window.progress.busy)
                self.assertIn('Edited locally.', (root / 'Home.md').read_text(), window.viewer.status.text())
                self.assertFalse(window.viewer.is_modified)
                window.viewer.editor.insertPlainText('Unsaved ')
                with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Cancel):
                    window.open_note('Nested/Next.md')
                    self.assertFalse(window.progress.busy)
                    self.assertFalse(window.prepare_close())
                    self.assertEqual(window.history[window.index], 'Home.md')
                with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Discard) as prompt:
                    window.open_note('Nested/Next.md')
                    self.wait_until(lambda: not window.progress.busy)
                    prompt.assert_called_once()
                self.assertTrue(window.viewer.edit_button.isChecked())
                window.viewer.editor.insertPlainText('Saved on close. ')
                with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Save):
                    self.assertFalse(window.prepare_close())
                from shiboken6 import isValid
                self.wait_until(lambda: not isValid(window) or not window.progress.busy)
                self.assertIn('Saved on close.', (root / 'Nested/Next.md').read_text())

    def test_note_reads_complete_short_chunks_and_enforce_the_total_preview_limit(self):
        from contextlib import contextmanager
        from io import BytesIO
        from features.text_editor.notes import NotesLibrary, MAX_NOTE
        class ShortReads(BytesIO):
            def read(self, count):
                return super().read(min(3, count))
        with self.temporary_directory() as directory:
            root = Path(directory)
            data = b'# Complete note\n'
            (root / 'Note.md').write_bytes(data)
            provider = LocalFiles(root)
            library = NotesLibrary(provider)
            @contextmanager
            def opened(path):
                with ShortReads(data) as stream:
                    yield stream
            for limit in (4, MAX_NOTE):
                with self.subTest(limit=limit), patch.object(provider, 'open', side_effect=opened), \
                        patch('features.text_editor.notes.MAX_NOTE', limit):
                    if limit < len(data):
                        with self.assertRaisesRegex(ValueError, 'too large'):
                            library.read('Note.md')
                    else:
                        self.assertEqual(library.read('Note.md'), data)

    def fixture(self, root):
        (root/'.obsidian').mkdir();(root/'Nested').mkdir()
        (root/'Home.md').write_text('# Home\n\n[Next](Nested/Next.md)')
        (root/'Nested/Next.md').write_text('# Next\n\nA nested note.')
        (root/'.obsidian/private.md').write_text('# Hidden')
        (root/'Other.txt').write_text('Not Markdown')

    def test_location_action_and_documents_host_open_library(self):
        from commonUtils.ui.document_host import register_document_host
        from desktop.documents import DocumentsPage
        with self.temporary_directory() as directory:
            root=Path(directory);self.fixture(root)
            commands=actions(FolderEntry('Notes',local=LocalFolder(root)))
            self.assertEqual([item.name for item in commands], ['Open as Notes Library'])
            host=DocumentsPage(lambda: None);host.show();register_document_host(host)
            try:
                window=commands[0].callback()
                self.wait_until(lambda:not window.progress.busy)
                self.assertIn(window,host.records)
                self.assertIsNotNone(window.search)
                self.assertEqual(window.tree.topLevelItemCount(),2)
                window.open_note('Home.md');self.wait_until(lambda:not window.progress.busy)
                self.assertIn('Home',window.viewer.browser.toPlainText())
                window.open_note('Nested/Next.md');self.wait_until(lambda:not window.progress.busy)
                self.assertIn('nested note',window.viewer.browser.toPlainText())
                window.navigate(-1);self.wait_until(lambda:not window.progress.busy)
                self.assertEqual(window.history[window.index],'Home.md')
                window.search.setText('Home')
                self.assertFalse(window.items['Home.md'].isHidden())
            finally:
                self.app._commonutils_document_host = lambda: None
                host.close()

    def test_remote_no_search_no_recursive_index_and_revoked_text_clears(self):
        with self.temporary_directory() as directory:
            root=Path(directory);self.fixture(root)
            provider=RemoteFiles(root)
            window=NotesLibraryWindow(lambda:provider,'Remote',remote=True)
            window.show();self.wait_until(lambda:not window.progress.busy)
            self.assertIsNone(window.search)
            self.assertFalse(window.viewer.find_action.isVisible())
            self.assertFalse(window.viewer.find_action.isEnabled())
            self.assertEqual(provider.calls,[''])
            self.assertNotIn('Nested/Next.md',window.items)
            window.items['Nested'].setExpanded(True)
            self.wait_until(lambda:not window.progress.busy)
            self.assertEqual(provider.calls,['','Nested'])
            window.open_note('Nested/Next.md');self.wait_until(lambda:not window.progress.busy)
            self.assertIn('nested note',window.viewer.browser.toPlainText())
            window.retire()
            self.assertEqual(window.storage.data,b'')
            self.assertIsNone(window.viewer.document_state.source_bytes)
            self.assertTrue(provider.closed)

    def test_marker_file_and_escape_never_open(self):
        with self.temporary_directory() as directory:
            root=Path(directory);(root/'.obsidian').write_text('not directory')
            self.assertEqual(actions(FolderEntry('Not a vault',local=LocalFolder(root))),[])
            (root/'.obsidian').unlink();self.fixture(root)
            window=NotesLibraryWindow(lambda:LocalFiles(root),'Notes')
            window.show();self.wait_until(lambda:not window.progress.busy)
            window.open_note('../outside.md')
            self.assertFalse(window.progress.busy)
            self.assertEqual(window.storage.data,b'')
            window.open_note('.obsidian/private.md')
            self.assertEqual(window.storage.data,b'')

    def test_closing_during_listing_waits_for_worker_and_releases_provider(self):
        from threading import Event
        from shiboken6 import isValid
        with self.temporary_directory() as directory:
            root = Path(directory);self.fixture(root)
            provider = RemoteFiles(root)
            entered, released = Event(), Event()
            original = provider.list
            def blocked(path='', **kwargs):
                entered.set()
                if not released.wait(5):raise RuntimeError('Fixture timed out')
                return original(path, **kwargs)
            with patch.object(provider, 'list', side_effect=blocked):
                window = NotesLibraryWindow(lambda: provider, 'Slow remote', remote=True)
                window.show()
                try:
                    self.wait_until(entered.is_set)
                    window.close()
                    self.assertTrue(window.closing)
                    self.assertTrue(window.progress.busy)
                finally:
                    released.set()
                self.wait_until(lambda: not isValid(window) or not window.progress.busy)
                self.assertTrue(provider.closed)

    def test_late_private_read_does_not_publish_after_provider_revocation(self):
        from contextlib import contextmanager
        with self.temporary_directory() as directory:
            root = Path(directory);self.fixture(root)
            provider = RemoteFiles(root)
            window = NotesLibraryWindow(lambda: provider, 'Remote', remote=True)
            window.show();self.wait_until(lambda:not window.progress.busy)
            original = provider.open
            @contextmanager
            def revoked_read(path):
                with original(path) as stream:
                    yield stream
                provider.closed = True
            with patch.object(provider, 'open', side_effect=revoked_read):
                window.open_note('Home.md')
                from shiboken6 import isValid
                self.wait_until(lambda:not isValid(window) or not window.progress.busy)
                if isValid(window):
                    self.assertEqual(window.storage.data, b'')
                    self.assertIsNone(window.viewer.document_state.source_bytes)

    def test_provider_library_embeds_load_from_memory_in_both_modes(self):
        from PIL import Image
        from commonUtils.formats.markdown.images import image_targets
        from services.documents.markdown import prepare_markdown
        for remote in (False, True):
            with self.subTest(remote=remote), self.temporary_directory() as directory:
                root = Path(directory)
                self.fixture(root)
                (root / 'Attachments').mkdir()
                embeds = []
                for kind in ('PNG', 'JPEG', 'WEBP', 'GIF'):
                    filename = 'photo #1.' + kind.lower()
                    Image.new('RGB', (800, 400), 'blue').save(root / 'Attachments' / filename, kind)
                    embeds.append('![[Attachments/' + filename + '|900]]')
                source = '\n\n'.join(embeds) + '\n\nFollowing text'
                path = root / 'Nested/Next.md'
                path.write_text(source)
                provider = RemoteFiles(root) if remote else LocalFiles(root)
                window = NotesLibraryWindow(lambda: provider, 'Images', remote=remote)
                window.show()
                self.wait_until(lambda: not window.progress.busy)
                window.open_note('Nested/Next.md')
                self.wait_until(lambda: not window.progress.busy)
                self.assertEqual(len(window.storage.resources), 4)
                for editing in ((False,) if remote else (False, True)):
                    window.viewer.set_editing(editing)
                    window.viewer.set_edit_mode('formatted')
                    surface = window.viewer.formatted_editor if editing else window.viewer.browser
                    for target in image_targets(source):
                        url = surface.document().baseUrl().resolved(qt.QUrl(target))
                        image = surface.document().resource(qt.QTextDocument.ResourceType.ImageResource, url)
                        self.assertIsInstance(image, qt.QImage)
                        self.assertFalse(image.isNull(), target)
                    self.assertFalse(window.viewer.is_modified)
                if remote:
                    self.assertEqual(provider.calls, [''])
                    window.retire()
                    self.assertEqual(window.storage.resources, {})
                window.close()
                # Direct provider Markdown also collects wiki images, references,
                # spaces and literal hashes, ignoring fenced code.
                sibling = root / 'Nested/photo #1.png'
                Image.new('RGB', (800, 400), 'blue').save(sibling)
                direct = b'![[photo #1.png|500]]\n\n![Reference][pic]\n\n[pic]: <photo #1.png>\n\n```\n![[absent.png]]\n```'
                _, resources = prepare_markdown(LocalFiles(root), path, data=direct)
                self.assertEqual(set(resources), {sibling.resolve()})
