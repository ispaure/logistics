"""Provider Markdown owns surfaces while sessions retain drafts and access policy."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import quote

from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.resources import LocalTextCopies
from mobile.app import LogisticsMobile


class ProviderMarkdownTests(unittest.TestCase):
    def test_source_controls_can_mount_after_opening_a_clean_formatted_document(self):
        owner = self.owner
        workflow = owner._provider_markdown
        self.assertIs(workflow.footer.parent, owner.crypt_view)
        self.assertEqual(workflow.footer.style.height, 0)
        workflow.edit_mode.value = 'Source'
        self.assertIs(workflow.edit_mode.parent, workflow.footer)
        self.assertIs(workflow.footer.parent, owner.crypt_view)
        self.assertNotEqual(workflow.footer.style.height, 0)

    def test_remote_markdown_opens_rendered_and_rejects_edit_and_save(self):
        remote = LocalFiles(self.files)
        remote.remote_storage = True
        async def exercise():
            self.assertTrue(await self.app.open_crypt(copies=LocalTextCopies(remote), key='First.md', edit=True))
            owner = self.app.private_sessions.active
            workflow = owner._provider_markdown
            self.assertTrue(owner.crypt_reader.read_only)
            self.assertEqual(owner.crypt_content.children, [workflow.preview])
            self.assertIsNone(workflow.edit_mode)
            await workflow.choose_mode('Formatted')
            self.assertIsNone(workflow.formatted)
            before = (self.files / 'First.md').read_bytes()
            owner.crypt_text.value = '# Programmatic mutation'
            await owner.save_crypt()
            self.assertEqual((self.files / 'First.md').read_bytes(), before)
        # This test covers supported-preview actions; unsupported private
        # backends are checked separately by the host privacy tests.
        import toga
        with patch('features.text_editor.mobile.provider_markdown.markdown_webview',
                   side_effect=lambda *, private, **options: toga.WebView(**options)):
            self.app.loop.run_until_complete(exercise())

    def test_preview_load_accepts_android_positional_url(self):
        workflow = self.owner._provider_markdown
        workflow.search.ready = False
        workflow.preview._font_binding._previous_load_handler(workflow.preview, "https://logistics.invalid/loaded/")
        self.assertTrue(workflow.search.ready)

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        LogisticsMobile.storage_root = self.root
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.files = self.root / 'notes'
        self.files.mkdir()
        self.copies = LocalTextCopies(LocalFiles(self.files))
        self.owner = self.open_note('First.md', b'# First\r\n\r\nUntouched.\r\n')

    def tearDown(self):
        self.app.private_sessions.clear(discard=True)
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.temporary.cleanup()

    def open_note(self, name, content):
        (self.files / name).write_bytes(content)
        self.assertTrue(self.app.loop.run_until_complete(self.app.open_crypt(copies=self.copies, key=name)))
        return self.app.private_sessions.active

    def test_sessions_keep_one_draft_and_independent_workflow_state(self):
        first = self.owner
        second = self.open_note('Second.md', b'# Second\n')
        a, b = first._provider_markdown, second._provider_markdown
        self.assertIsNot(a, b)
        self.assertIs(a.source, first.crypt_text)
        self.assertIs(b.source, second.crypt_text)
        self.assertNotIn('crypt_preview', vars(first))
        self.assertNotIn('_private_preview_token', vars(first))
        self.assertIs(first.crypt_preview, a.preview)
        first.resume_crypt()
        first.toggle_private_preview()
        bridge = first.crypt_formatted
        text = '# Changed\r\n\r\nUntouched.\r\n'
        bridge.navigate(None, bridge.bridge + '?text=' + quote(text, safe=''))
        self.assertEqual(first.crypt_text.value, text)
        self.assertEqual(second.crypt_text.value, '# Second\n')
        self.assertTrue(first.private_dirty())
        self.assertEqual((self.files / 'First.md').read_bytes(), b'# First\r\n\r\nUntouched.\r\n')

    def test_session_owns_state_and_close_veto_preserves_resources(self):
        owner = self.owner
        session = owner.provider_document()
        self.assertIs(session.reader, owner.crypt_reader)
        self.assertNotIn('crypt_reader', vars(owner))
        self.assertIs(session.metadata_fields, owner.crypt_metadata_fields)
        owner.crypt_text.value = '# Unsaved'
        with patch.object(owner.crypt_text, 'dispose', wraps=owner.crypt_text.dispose) as dispose:
            self.assertFalse(owner.clear_private_reader())
            self.assertFalse(session.closed)
            self.assertIsNotNone(session.reader)
            dispose.assert_not_called()
            self.assertTrue(owner.clear_private_reader(discard=True))
            self.assertTrue(owner.clear_private_reader(discard=True))
            dispose.assert_called_once_with()
        self.assertTrue(session.closed)
        self.assertIsNone(session.reader)
        self.assertEqual(session.metadata_fields, {})
        self.assertEqual(owner.crypt_text.value, '')

    def test_initial_native_text_notification_does_not_reload_rendered_preview(self):
        owner = self.owner
        with patch.object(owner.crypt_preview, 'set_content', wraps=owner.crypt_preview.set_content) as load:
            owner.private_source_changed(owner.crypt_text)
            self.app.loop.run_until_complete(asyncio.sleep(.35))
            load.assert_not_called()
            owner.crypt_text.value = '# Updated passage'
            self.app.loop.run_until_complete(asyncio.sleep(.4))
            self.assertIn('Updated passage', load.call_args.args[1])

    def test_close_retires_all_surfaces_and_formatted_callbacks(self):
        owner = self.owner
        workflow = owner._provider_markdown
        search, speech = owner.crypt_preview_search, owner.markdown_speech
        owner.toggle_private_preview()
        formatted = owner.crypt_formatted
        bridge = formatted.bridge
        self.assertTrue(search.closed)
        self.assertTrue(self.app.private_sessions.close(owner.session.id, discard=True))
        self.assertTrue(workflow.closed)
        self.assertTrue(workflow.actions_menu.disposed)
        self.assertTrue(formatted.closed)
        self.assertIsNone(workflow.preview)
        self.assertIsNone(workflow.pending)
        self.assertIsNone(workflow.token)
        self.assertNotIn(speech.button, workflow.toolbar.children)
        formatted.navigate(None, bridge + '?text=late-private-content')
        self.assertEqual(owner.crypt_text.value, '')

    def check_late_render(self, invalidate, *, failure=False):
        owner = self.owner
        workflow = owner._provider_markdown
        preview, title = owner.crypt_preview, owner.crypt_title
        started, release, finished = Event(), Event(), Event()
        def render(*args, **kwargs):
            started.set()
            try:
                if not release.wait(5):
                    raise RuntimeError('Preview fixture was not released')
                if failure:
                    raise ValueError('Late private error')
                return '<p>Late private preview</p>'
            finally:
                finished.set()
        async def exercise():
            workflow.schedule_preview()
            task = workflow.pending
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                invalidate(owner)
                retained_title = title.text
                release.set()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                self.assertTrue(await asyncio.to_thread(finished.wait, 3))
                self.assertEqual(title.text, retained_title)
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)
        with patch('mobile.preview.markdown_preview', side_effect=render), \
                patch.object(preview, 'set_content') as content:
            self.app.loop.run_until_complete(exercise())
        self.assertFalse(any('Late private preview' in call.args[-1] for call in content.call_args_list))

    def test_closed_document_cannot_receive_late_render(self):
        self.check_late_render(lambda owner: self.app.private_sessions.close(owner.session.id, discard=True))

    def test_replaced_reader_cannot_receive_late_render_or_error(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                reader = self.owner.crypt_reader
                try:
                    self.check_late_render(lambda owner: setattr(owner, 'crypt_reader',
                        self.copies.open('First.md')), failure=failure)
                finally:
                    self.owner.crypt_reader = reader

    def test_source_access_change_cannot_receive_late_render_or_error(self):
        client = SimpleNamespace(generation=1)
        def check():
            if client.generation != 1:
                raise ValueError('Source access revoked')
        self.owner.document_access = check
        for failure in (False, True):
            client.generation = 1
            with self.subTest(failure=failure):
                self.check_late_render(lambda owner: setattr(client, 'generation', 2), failure=failure)

    def test_unrelated_connection_change_keeps_local_document_available(self):
        self.app.cloud_client = SimpleNamespace(generation=10)
        self.assertTrue(self.app.private_sessions.available(self.owner.session.id))
        self.app.cloud_client.generation += 1
        self.assertTrue(self.app.private_sessions.available(self.owner.session.id))

    def test_lock_revokes_pending_work_and_search(self):
        client = SimpleNamespace(generation=1, cancel=lambda: None)
        self.owner.credential_client = self.app.cloud_client = client
        self.owner.credential_generation = 1
        self.copies.provider.private = True
        def check():
            if client.generation != 1:
                raise ValueError('Source access revoked')
        self.owner.document_access = check
        search = self.owner.crypt_preview_search
        def lock(owner):
            client.generation += 1
            self.app.private_sessions.revoke_stale()
        self.check_late_render(lock)
        self.assertTrue(search.closed)
        self.assertTrue(self.owner._provider_markdown.closed)
        self.assertEqual(self.owner.crypt_text.value, '')

    def test_newer_preview_wins_when_old_worker_finishes_last(self):
        owner = self.owner
        workflow = owner._provider_markdown
        started, release, finished = Event(), Event(), Event()
        original = owner.crypt_text.value
        def render(text, *args, **kwargs):
            if text == original:
                started.set()
                try:
                    if not release.wait(5):
                        raise RuntimeError('Preview fixture was not released')
                    return '<p>Superseded preview</p>'
                finally:
                    finished.set()
            return '<p>Latest preview</p>'
        async def exercise():
            workflow.schedule_preview()
            old_task = workflow.pending
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                owner.crypt_text.value = '# Latest'
                self.assertIsNot(workflow.pending, old_task)
                await workflow.pending
                release.set()
                await asyncio.gather(old_task, return_exceptions=True)
                self.assertTrue(await asyncio.to_thread(finished.wait, 3))
            finally:
                release.set()
                await asyncio.gather(old_task, return_exceptions=True)
        with patch('mobile.preview.markdown_preview', side_effect=render), \
                patch.object(owner.crypt_preview, 'set_content') as content:
            self.app.loop.run_until_complete(exercise())
        published = [call.args[-1] for call in content.call_args_list]
        self.assertIn('<p>Latest preview</p>', published)
        self.assertNotIn('<p>Superseded preview</p>', published)
        self.assertEqual(owner.crypt_text.value, '# Latest')

    def test_prepared_replacement_retires_old_workflow_and_can_return_to_plain_text(self):
        owner = self.owner
        for name in ('Replacement.md', 'Plain.txt'):
            previous = owner._provider_markdown
            (self.files / name).write_text('Replacement text')
            reader = self.copies.open(name)
            self.assertTrue(self.app.loop.run_until_complete(owner.provider_document().opening.open(
                copies=self.copies, key=name, prepared=(reader, 'text', reader.text))))
            self.assertTrue(previous.closed)
            if name.endswith('.md'):
                self.assertIsNot(previous, owner._provider_markdown)
                self.assertFalse(owner._provider_markdown.closed)
            else:
                self.assertIsNone(owner._provider_markdown)
                owner.crypt_text.value = 'Edited plain text'
                self.assertTrue(owner.crypt_save.enabled)
                self.assertIn(owner.crypt_save, owner.reader_toolbar.children)

    def test_resource_setup_failure_retains_source_and_reports_error(self):
        source = self.owner.crypt_text.value
        with patch('mobile.preview.reader_image_source', side_effect=ValueError('Image source unavailable')):
            self.owner.schedule_private_preview()
        self.assertEqual(self.owner.crypt_text.value, source)
        self.assertIn('Image source unavailable', self.owner.crypt_title.text)
        self.assertIsNone(self.owner._private_preview_pending)
