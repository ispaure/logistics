"""Closing a reader releases its slot and returns to the retained source folder."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import base64
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import toga

from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.resources import LocalTextCopies
from features.rclone.mobile.remote_readers import RemoteReaders
from mobile_build.tests.support.app import create_app
from mobile_build.tests.support.localcrypt import seed_offline_copy
from mobile_build.tests.support.readers import RemoteClient
from mobile_build.tests.support.pdf import PDF, native_pdf


class ReaderLifecycleTests(TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.app = create_app(self, root=self.root)
        self.app.show_cloud(present=False)
        self.run_async(self.app.show_files())
        self.origin = self.app.body
        self.copies = LocalTextCopies(LocalFiles(self.root))

    def run_async(self, operation):
        return self.app.loop.run_until_complete(operation)

    def answer_close(self, choice):
        tasks = list(self.app._document_close_tasks.values())
        self.app.main_window._impl.dialog_responses.setdefault('QuestionDialog', []).append(choice)
        return tasks[0]

    def assert_closed(self, owner):
        self.assertNotIn(owner.session.id, self.app.workspace.sessions)
        self.assertEqual(self.app.native_host.state.destination, 'files')
        self.assertIs(self.app.body, self.origin)
        self.assertFalse(any(name.startswith(('private:', 'reader:', 'close:', 'private-close:'))
                             for screens in self.app.routes.screens.values() for name, *_ in screens))

    def assert_close_control(self, view):
        button = view._reader_close_button
        self.assertEqual(button.control_icon, 'close')
        self.assertEqual(button.text, '×')
        self.assertEqual(button.accessible_name, 'Close document')

    def test_local_close_and_android_back_free_slots_without_leaving_stale_routes(self):
        path = self.root / 'note.txt'
        path.write_text('Saved text')
        for close_with_x in (True, False):
            self.assertTrue(self.run_async(self.app.open_crypt(copies=self.copies, key=path.name)))
            owner = self.app.private_sessions.active
            self.assert_close_control(owner.crypt_view)
            if close_with_x:
                owner.crypt_view._reader_close_button.on_press()
            else:
                self.assertTrue(self.app.routes.system_back())
            self.assert_closed(owner)
            self.assertIsNone(owner.crypt_reader)

    def test_dirty_exit_can_keep_editing_discard_or_save_and_returns_to_folder(self):
        path = self.root / 'edit.txt'
        path.write_text('Original')
        self.run_async(self.app.open_crypt(copies=self.copies, key=path.name))
        owner = self.app.private_sessions.active
        owner.crypt_text.value = 'Changed'
        owner.crypt_view._reader_close_button.on_press()
        self.assertIn(owner.session.id, self.app.workspace.sessions)
        self.run_async(self.answer_close('cancel'))
        self.assertEqual(owner.crypt_text.value, 'Changed')
        self.assertEqual(self.app.visible_reader(), owner.session.id)
        self.app.routes.system_back()
        self.run_async(self.answer_close('cancel'))
        self.assertEqual(owner.crypt_text.value, 'Changed')
        self.app.routes.system_back()
        self.run_async(self.answer_close('discard'))
        self.assert_closed(owner)
        self.assertEqual(path.read_text(), 'Original')
        self.run_async(self.app.open_crypt(copies=self.copies, key=path.name))
        owner = self.app.private_sessions.active
        owner.crypt_text.value = 'Saved change'
        owner.crypt_view._reader_close_button.on_press()
        self.run_async(self.answer_close('save'))
        self.assert_closed(owner)
        self.assertEqual(path.read_text(), 'Saved change')

    def test_failed_save_keeps_reader_and_draft(self):
        path = self.root / 'conflict.txt'
        path.write_text('Original')
        self.run_async(self.app.open_crypt(copies=self.copies, key=path.name))
        owner = self.app.private_sessions.active
        owner.crypt_text.value = 'Unsaved'
        path.write_text('External change')
        owner.crypt_view._reader_close_button.on_press()
        self.run_async(self.answer_close('save'))
        self.assertIn(owner.session.id, self.app.workspace.sessions)
        self.assertEqual(owner.crypt_text.value, 'Unsaved')
        self.assertIsNot(self.app.body, self.origin)
        self.assertIn('Save failed', owner.crypt_title.text)
        self.app.request_reader_close(owner.session.id)
        self.run_async(self.answer_close('cancel'))
        self.assertEqual(owner.crypt_text.value, 'Unsaved')

    def test_resuming_in_another_tab_updates_back_origin(self):
        self.app.create_chosen_document('txt')
        owner = self.app.editor_view
        key = owner.session.id
        self.app.show_home()
        origin = self.app.body
        self.app.session_opener(key)()
        self.assertTrue(self.app._document_tabs_hidden)
        self.assert_close_control(owner.document_view)
        owner.document_view._reader_close_button.on_press()
        self.assertNotIn(key, self.app.workspace.sessions)
        self.assertEqual(self.app.native_host.state.destination, 'home')
        self.assertIs(self.app.body, origin)
        self.assertFalse(self.app._document_tabs_hidden)

    def test_closing_hidden_provider_and_library_readers_retires_source_routes(self):
        from mobile_build.native_tests.tests.logisticsmobile.compact_reading_probe import epub_bytes
        app = self.app
        for name, content in (('hidden.txt', b'Saved text'), ('hidden.epub', epub_bytes())):
            with self.subTest(name=name):
                path = self.root / name
                path.write_bytes(content)
                self.assertTrue(self.run_async(app.open_download(path=path)))
                key = app.visible_reader()
                self.assertIsNotNone(key)
                app.routes.return_to('documents')
                self.assertIsNone(app.visible_reader())
                self.assertTrue(app.request_close_session(key))
                self.assertNotIn(key, app.workspace.sessions)
                self.assertFalse(any(route.startswith(('private:', 'reader:'))
                                     for route, *_ in app.routes.screens['files']))
                app.routes.return_to('files')
                self.assertIs(app.body, self.origin)
                self.assertIsNone(app.visible_reader())
                self.assertFalse(app._document_tabs_hidden)

    def test_resuming_from_a_new_screen_in_the_same_tab_updates_back_origin(self):
        self.app.create_chosen_document('txt')
        owner = self.app.editor_view
        key = owner.session.id
        self.app.show_documents_hub()
        self.app.routes.trim('files', 0)
        source = toga.Box(children=[toga.Label('Another retained folder')])
        self.app.show_view(source, destination='files', route='another-folder')
        origin = self.app.body
        self.app.session_opener(key)()
        owner.document_view._reader_close_button.on_press()
        self.assertIs(self.app.body, origin)
        self.assertIn(source, self.app.body.children)
        self.assertEqual(self.app.routes.screens['files'][-1][0], 'another-folder')

    def test_cancelling_close_preserves_each_documents_preview_or_edit_mode(self):
        for kind, mode in (('txt', 'preview'), ('md', 'edit'), ('md', 'preview'), ('txt', 'edit')):
            with self.subTest(kind=kind, mode=mode):
                self.app.create_chosen_document(kind)
                owner = self.app.editor_view
                owner.editor.value = '# Retained draft'
                if mode == 'preview':
                    self.app.show_preview()
                else:
                    self.app.show_documents(edit=True)
                view = self.app.body.children[0]
                self.assert_close_control(view)
                self.assertTrue(self.app.routes.back())
                self.assertFalse(any(route.startswith('close:') for route, *_ in self.app.routes.screens['files']))
                self.run_async(self.answer_close('cancel'))
                self.assertIs(self.app.body.children[0], view)
                self.assertEqual(owner.session.view['markdown_mode'], mode)
                self.assertEqual(owner.editor.value, '# Retained draft')
                self.assertTrue(self.app._document_tabs_hidden)
                self.app.request_reader_close(owner.session.id)
                self.run_async(self.answer_close('discard'))

    def test_imported_epub_close_flushes_latest_position_and_reopening_resumes(self):
        from mobile_build.native_tests.tests.logisticsmobile.compact_reading_probe import epub_bytes
        path = self.root / 'book.epub'
        path.write_bytes(epub_bytes())
        async def exercise():
            self.assertTrue(await self.app.open_download(path=path))
            owner = self.app.readers.active
            self.assert_close_control(owner.library_view)
            owner.epub_event(owner.book_reader, owner.book_epoch, 0, 'position', 120)
            owner.library_view._reader_close_button.on_press()
            await owner._exit_task
            self.assert_closed(owner)
            self.assertTrue(await self.app.open_download(path=path))
            resumed = self.app.readers.active
            self.assertEqual(resumed.epub_offset, 120)
            resumed.library_view._reader_close_button.on_press()
            self.assert_closed(resumed)
        self.run_async(exercise())

    def test_localcrypt_epub_close_keeps_passage_offset_without_retaining_reader(self):
        from mobile_build.native_tests.tests.logisticsmobile.compact_reading_probe import epub_bytes
        data = epub_bytes()
        class Client(RemoteClient):
            supports_streaming = False
            def request(self, action, **values):
                if action == 'crypt_describe':
                    return 'private.epub'
                if action == 'crypt_decode':
                    return dict(name='private.epub', data=base64.b64encode(data).decode())
                return super().request(action, **values)
        client = self.app.cloud_client = Client()
        self.app.crypt_copies.client = client
        key = seed_offline_copy(self.app.crypt_copies)
        async def exercise():
            self.assertTrue(await self.app.open_crypt(copies=self.app.crypt_copies, key=key))
            owner = self.app.private_sessions.active
            owner.provider_epub_view.offset = 120
            owner.crypt_view._reader_close_button.on_press()
            self.assert_closed(owner)
            self.assertIsNone(owner.crypt_reader)
            self.assertTrue(await self.app.open_crypt(copies=self.app.crypt_copies, key=key))
            resumed = self.app.private_sessions.active
            self.assertEqual(resumed.provider_epub_view.offset, 120)
            self.app.routes.system_back()
            self.assert_closed(resumed)
        self.run_async(exercise())

    def test_managed_editor_close_prompts_and_saves_then_returns_to_origin(self):
        self.app.create_chosen_document('txt')
        owner = self.app.editor_view
        owner.editor.value = 'Managed edit'
        self.assert_close_control(owner.document_view)
        owner.document_view._reader_close_button.on_press()
        self.assertIn(owner.session.id, self.app.workspace.sessions)
        self.run_async(self.answer_close('cancel'))
        self.assertEqual(self.app.visible_reader(), owner.session.id)
        self.app.routes.system_back()
        self.run_async(self.answer_close('save'))
        self.assert_closed(owner)

    def test_text_scroll_survives_close_without_retaining_content_in_position_cache(self):
        path = self.root / 'text-position.txt'
        path.write_text('Content must not enter the position cache')
        self.run_async(self.app.open_crypt(copies=self.copies, key=path.name))
        owner = self.app.private_sessions.active
        with patch('mobile.reader_lifecycle.scroll_position', return_value=(0, 345)):
            owner.crypt_view._reader_close_button.on_press()
        self.assert_closed(owner)
        self.assertNotIn('Content must not', repr(self.app.private_sessions.positions))
        with patch('mobile.reader_lifecycle.restore_scroll') as restore:
            self.run_async(self.app.open_crypt(copies=self.copies, key=path.name))
        restore.assert_any_call(self.app.private_sessions.active.crypt_text, (0, 345))

    def test_markdown_scroll_waits_for_loaded_preview_and_preserves_search_handler(self):
        path = self.root / 'preview-position.md'
        path.write_text('# Remember this passage')
        self.run_async(self.app.open_crypt(copies=self.copies, key=path.name))
        owner = self.app.private_sessions.active
        with patch('mobile.reader_lifecycle.scroll_position', return_value=(0, 345)):
            owner.crypt_view._reader_close_button.on_press()
        with patch('mobile.reader_lifecycle.restore_scroll') as restore:
            self.run_async(self.app.open_crypt(copies=self.copies, key=path.name))
            resumed = self.app.private_sessions.active
            self.run_async(resumed.crypt_preview.on_webview_load())
            resumed.crypt_preview_search.ready = False
            self.run_async(resumed.crypt_preview.on_webview_load())
        self.assertTrue(resumed.crypt_preview_search.ready)
        restore.assert_any_call(resumed.crypt_preview, (0, 345))

    def test_metadata_back_returns_to_document_and_reopening_keeps_draft(self):
        from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
        _, comic = make_books(self.root)
        self.run_async(self.app.open_download(path=comic))
        owner = self.app.readers.active
        owner.show_book_metadata()
        owner.book_metadata_fields['Title'].value = 'Keep this metadata draft'
        self.assertTrue(self.app.routes.back())
        self.assertIs(self.app.body.children[0], owner.library_view)
        self.assertIn(owner.session.id, self.app.workspace.sessions)
        self.assertFalse(getattr(self.app, '_document_close_tasks', {}))
        owner.show_book_metadata()
        self.assertEqual(owner.book_metadata_fields['Title'].value, 'Keep this metadata draft')
        self.assertTrue(self.app.routes.system_back())
        self.assertIs(self.app.body.children[0], owner.library_view)
        self.app.request_reader_close(owner.session.id)
        self.run_async(self.answer_close('discard'))

    def test_imported_metadata_draft_prompts_before_close(self):
        from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
        _, comic = make_books(self.root)
        async def exercise():
            self.assertTrue(await self.app.open_download(path=comic))
            owner = self.app.readers.active
            self.assert_close_control(owner.library_view)
            owner.show_book_metadata()
            owner.book_metadata_fields['Title'].value = 'Unsaved title'
            owner.show_library()
            owner.library_view._reader_close_button.on_press()
            self.assertIn(owner.session.id, self.app.workspace.sessions)
            await self.answer_close('cancel')
            self.assertEqual(owner.book_metadata_fields['Title'].value, 'Unsaved title')
            owner.show_library()
            owner.library_view._reader_close_button.on_press()
            await self.answer_close('discard')
            self.assert_closed(owner)
        self.run_async(exercise())

    def test_pdf_positions_resume_after_close_across_local_cloud_server_and_localcrypt(self):
        class Client(RemoteClient):
            supports_streaming = False
            def request(self, action, **values):
                if action == 'crypt_describe':
                    return 'secret.pdf'
                if action == 'crypt_decode':
                    return dict(name='secret.pdf', data=base64.b64encode(PDF).decode())
                return super().request(action, **values)
            def crypt_remotes(self):
                return []
        client = self.app.cloud_client = Client()
        self.app.crypt_copies.client = client
        client.files['remote.pdf'] = PDF
        path = self.root / 'local.pdf'
        path.write_bytes(PDF)
        key = seed_offline_copy(self.app.crypt_copies)
        async def exercise():
            for source in ('local', 'cloud', 'server', 'crypt'):
                async def open_file():
                    if source == 'local':
                        return await self.app.open_download(path=path)
                    if source == 'crypt':
                        return await self.app.open_crypt(copies=self.app.crypt_copies, key=key)
                    return await self.app.open_crypt(copies=RemoteReaders(client, source), key='remote.pdf')
                with self.subTest(source=source):
                    self.assertTrue(await open_file(), self.app.cloud_status.value)
                    owner = self.app.private_sessions.active
                    self.assert_close_control(owner.crypt_view)
                    await owner.move_private_page(2)
                    owner.crypt_view._reader_close_button.on_press()
                    self.assert_closed(owner)
                    self.assertTrue(await open_file(), self.app.cloud_status.value)
                    resumed = self.app.private_sessions.active
                    self.assertEqual(resumed._provider_displayed_index, 2)
                    self.app.routes.system_back()
                    self.assert_closed(resumed)
            self.app.clear_private_reader(discard=True)
            self.assertFalse(self.app.private_sessions.positions)
        with patch('features.pdf.document.PDFDocument.open', native_pdf):
            self.run_async(exercise())
