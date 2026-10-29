"""Live editor identity and saved bytes across real resource mutations."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.resources import LocalTextCopies
from mobile.app import LogisticsMobile
from mobile.file_operations import FileDestination, FileOperationRequest, retiring_work
from mobile.document_mutations import prepare_document_mutation


class DocumentMutationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        LogisticsMobile.storage_root = self.root
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.run_async = self.app.loop.run_until_complete
        self.run_async(self.app.show_files(location=('Local files', '')))
        self.source = self.app.file_provider
        (self.root / 'destination').mkdir()
        self.destination = LocalFiles(self.root / 'destination')

    def tearDown(self):
        self.app.clear_private_reader(discard=True)
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.temp.cleanup()

    def open(self, path='first.txt', data=b'Original\r\n', *, provider=None):
        provider = provider or self.source
        full = provider.root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)
        self.assertTrue(self.run_async(self.app.open_crypt(copies=LocalTextCopies(provider), key=path, edit=True)))
        return self.app.private_sessions.active

    def move_request(self, path='first.txt', target='moved.txt'):
        return FileOperationRequest('move', self.source, path, target,
            FileDestination(self.root, None, self.destination, None))

    def move(self, request):
        async def execute():
            plan = await prepare_document_mutation(self.app, request)
            try:
                await retiring_work(plan.execute, Event(), completed=plan.apply)
            finally:
                plan.release()
        self.run_async(execute())

    def test_move_retains_draft_widget_session_and_subsequent_save_targets_destination(self):
        owner = self.open()
        owner.crypt_text.value = 'Unsaved\nchanges\n'
        widget, session = owner.crypt_text, owner.session
        identity = session.identity
        self.move(self.move_request())
        self.assertIs(owner.crypt_text, widget)
        self.assertIs(owner.session, session)
        self.assertNotEqual(session.identity, identity)
        self.assertTrue(session.dirty)
        self.assertEqual(widget.value, 'Unsaved\nchanges\n')
        self.assertEqual((self.destination.root / 'moved.txt').read_bytes(), b'Original\r\n')
        self.assertFalse((self.source.root / 'first.txt').exists())
        self.run_async(owner.save_crypt())
        self.assertEqual((self.destination.root / 'moved.txt').read_bytes(), b'Unsaved\r\nchanges\r\n')
        self.assertFalse((self.source.root / 'first.txt').exists())
        self.assertEqual(owner.crypt_reader.text, widget.value)
        self.assertEqual(session.history_source['path'], str(self.destination.root / 'moved.txt'))
        paths = [item.get('source', {}).get('path') for item in self.app.recent_documents.items]
        self.assertNotIn(str(self.source.root / 'first.txt'), paths)

    def test_rename_command_keeps_affected_and_unrelated_dirty_editors(self):
        owner = self.open()
        other = self.open('other.txt', b'Other')
        owner.crypt_text.value, other.crypt_text.value = 'first draft', 'other draft'
        self.run_async(self.app.show_files(location=('Local files', '')))
        self.app.file_selection.value = next(k for k, r in self.app.file_rows.items() if r['name'] == 'first.txt')
        self.app.file_name.value = 'renamed.txt'
        self.run_async(self.app.rename_file())
        self.assertEqual(owner.crypt_reader.key, 'renamed.txt', self.app.file_status.value)
        self.assertEqual(owner.crypt_text.value, 'first draft')
        self.assertEqual(other.crypt_text.value, 'other draft')
        self.assertEqual(len(self.app.private_sessions.controllers), 2)
        self.run_async(owner.save_crypt())
        self.assertEqual((self.source.root / 'renamed.txt').read_text(), 'first draft')

    def test_folder_move_retargets_descendants_opened_through_narrower_aliases(self):
        folder = self.source.root / 'Folder'
        folder.mkdir()
        owner = self.open('nested.txt', provider=LocalFiles(folder))
        owner.crypt_text.value = 'Nested draft'
        self.move(self.move_request('Folder', 'Moved folder'))
        self.assertEqual(owner.crypt_reader.key, 'Moved folder/nested.txt')
        self.run_async(owner.save_crypt())
        self.assertEqual((self.destination.root / 'Moved folder/nested.txt').read_text(), 'Nested draft')
        self.assertFalse(folder.exists())

    def test_external_change_and_destination_conflict_preserve_draft_and_bindings(self):
        owner = self.open()
        reader = owner.crypt_reader
        owner.crypt_text.value = 'Draft'
        (self.destination.root / 'moved.txt').write_text('Existing')
        with self.assertRaises(FileExistsError):
            self.move(self.move_request())
        self.assertIs(owner.crypt_reader, reader)
        (self.destination.root / 'moved.txt').unlink()
        (self.source.root / 'first.txt').write_text('External change')
        with self.assertRaisesRegex(ValueError, 'changed on disk'):
            self.move(self.move_request())
        self.assertIs(owner.crypt_reader, reader)
        self.assertEqual(owner.crypt_text.value, 'Draft')
        self.assertFalse((self.destination.root / 'moved.txt').exists())
        self.assertFalse(owner.operation_busy)
        self.assertFalse(owner.crypt_text.readonly)

    def test_editor_type_change_is_rejected_before_rename(self):
        owner = self.open()
        owner.crypt_text.value = 'Draft'
        for target in ('different.md', 'different.pdf', 'different.epub', 'different.exe'):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'editor type'):
                self.move(FileOperationRequest('rename', self.source, 'first.txt', target))
            self.assertFalse((self.source.root / target).exists())
        self.assertTrue((self.source.root / 'first.txt').exists())
        self.assertFalse((self.source.root / 'different.md').exists())

    def test_failed_reopen_retains_draft_and_never_recreates_removed_source(self):
        from commonUtils.runtime.operations import MutationIncomplete
        owner = self.open()
        owner.crypt_text.value = 'Recoverable draft'
        original = LocalTextCopies.open
        def unavailable(copies, key, **kwargs):
            if copies.provider is self.destination:
                raise OSError('Destination temporarily unavailable')
            return original(copies, key, **kwargs)
        with patch.object(LocalTextCopies, 'open', unavailable):
            with self.assertRaisesRegex(MutationIncomplete, 'file was moved'):
                self.move(self.move_request())
        self.assertEqual(owner.crypt_text.value, 'Recoverable draft')
        self.assertFalse((self.source.root / 'first.txt').exists())
        self.assertEqual((self.destination.root / 'moved.txt').read_bytes(), b'Original\r\n')
        self.run_async(owner.save_crypt())
        self.assertIn('edits retained', owner.crypt_title.text.replace('\n', ' '))
        self.assertFalse((self.source.root / 'first.txt').exists())

    def test_history_write_failure_does_not_leave_editor_bound_to_removed_source(self):
        owner = self.open()
        owner.crypt_text.value = 'Retained draft'
        with patch.object(self.app.recent_documents, 'forget', side_effect=OSError('History unavailable')):
            self.move(self.move_request())
        self.assertEqual(owner.crypt_reader.key, 'moved.txt')
        self.run_async(owner.save_crypt())
        self.assertEqual((self.destination.root / 'moved.txt').read_text(), 'Retained draft')

    def test_navigation_change_during_move_still_retargets_surviving_editor(self):
        owner = self.open()
        owner.crypt_text.value = 'Navigated draft'
        async def exercise():
            plan = await prepare_document_mutation(self.app, self.move_request())
            try:
                self.app.navigation_generation += 1
                await retiring_work(plan.execute, Event(), completed=plan.apply)
            finally:
                plan.release()
        self.run_async(exercise())
        self.assertEqual(owner.crypt_reader.key, 'moved.txt')
        self.run_async(owner.save_crypt())
        self.assertEqual((self.destination.root / 'moved.txt').read_text(), 'Navigated draft')

    def test_late_task_cancel_reconciles_committed_move_before_releasing_editor(self):
        owner = self.open()
        owner.crypt_text.value = 'Draft after cancel'
        published, release = Event(), Event()
        original = FileOperationRequest.execute
        def execute(request, *args, **kwargs):
            result = original(request, *args, **kwargs)
            published.set()
            if not release.wait(5):
                raise RuntimeError('Test worker was not released')
            return result
        async def exercise():
            plan = await prepare_document_mutation(self.app, self.move_request())
            task = asyncio.create_task(retiring_work(plan.execute, Event(), completed=plan.apply))
            try:
                self.assertTrue(await asyncio.to_thread(published.wait, 4))
                task.cancel()
                await asyncio.sleep(0)
                self.assertFalse(task.done())
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            finally:
                release.set()
                plan.release()
        with patch.object(FileOperationRequest, 'execute', execute):
            self.run_async(exercise())
        self.assertEqual(owner.crypt_reader.key, 'moved.txt')
        self.run_async(owner.save_crypt())
        self.assertEqual((self.destination.root / 'moved.txt').read_text(), 'Draft after cancel')

    def test_picker_move_keeps_dirty_document_and_updates_show_in_folder_source(self):
        owner = self.open()
        owner.crypt_text.value = 'Picker draft'
        picker = self.app.editor_picker()
        self.run_async(picker.show_destination('first.txt', FileOperationRequest('move', self.source, 'first.txt')))
        picker.editor_storage_roots['Destination'] = self.destination
        picker.save_as_storage.items = list(picker.editor_storage_roots)
        picker.save_as_storage.value = 'Destination'
        self.run_async(picker._storage_refresh)
        self.run_async(picker.complete_destination())
        self.assertIs(owner, self.app.private_sessions.controllers[owner.session.id])
        self.assertEqual(owner.crypt_text.value, 'Picker draft')
        from mobile.document_sources import folder_location
        location = folder_location(self.app, owner.session)
        self.assertIs(location['provider'], self.destination)
        self.assertEqual(location['key'], 'first.txt')
        self.run_async(owner.save_crypt())
        self.assertEqual((self.destination.root / 'first.txt').read_text(), 'Picker draft')

    def test_formatted_markdown_still_accepts_edits_after_move_and_save(self):
        from urllib.parse import quote
        owner = self.open('first.md', b'# Original\n')
        workflow = owner._provider_markdown
        formatted = workflow.formatted
        self.assertIsNotNone(formatted)
        formatted.navigate(None, formatted.bridge + '?text=' + quote('# First draft\n'))
        self.move(self.move_request('first.md', 'moved.md'))
        self.assertIs(workflow.formatted, formatted)
        self.assertFalse(formatted.closed)
        self.run_async(owner.save_crypt())
        formatted.navigate(None, formatted.bridge + '?text=' + quote('# Second draft\n'))
        self.assertEqual(owner.crypt_text.value, '# Second draft\n')
        self.run_async(owner.save_crypt())
        self.assertEqual((self.destination.root / 'moved.md').read_text(), '# Second draft\n')

    def test_downloaded_encrypted_copy_rename_keeps_its_record_identity_and_draft(self):
        import base64
        import json
        import os
        from uuid import uuid4
        from features.rclone.localcrypt.mobile.resources import DownloadedCryptFile
        class Client:
            generation = 0
            data = b'Offline original'
            def request(self, action, **values):
                name = 'offline.txt' if values.get('path') == 'encoded' else Path(values.get('path', '')).name
                if action == 'crypt_describe':
                    return name
                if action == 'crypt_path':
                    return dict(identity='a' * 64, path=values['path'])
                if action == 'crypt_decode':
                    return dict(name=name, data=base64.b64encode(self.data).decode())
                if action == 'crypt_encode':
                    self.data = base64.b64decode(values['data'])
                    os.write(values['fd'], b'opaque updated ciphertext')
                    return True
                raise AssertionError(action)
            def crypt_remotes(self): return []
            def cancel(self): pass
        app = self.app
        app.show_cloud(present=False)
        app.cloud_client = Client()
        app.crypt_copies.client = app.cloud_client
        key = uuid4().hex
        folder = app.crypt_copies.root / key
        folder.mkdir()
        (folder / 'data').write_bytes(b'opaque original ciphertext')
        (folder / 'record.json').write_text(json.dumps(dict(remote='Secret', identity='a' * 64, encrypted_path='encoded')))
        self.assertTrue(self.run_async(app.open_crypt(copies=app.crypt_copies, key=key)))
        owner = app.private_sessions.active
        identity = owner.session.identity
        owner.crypt_text.value = 'Offline draft'
        provider = DownloadedCryptFile(app.crypt_copies, key)
        self.move(FileOperationRequest('rename', provider, 'offline.txt', 'renamed.txt'))
        self.assertEqual(owner.session.identity, identity)
        self.assertEqual(owner.crypt_reader.name, 'renamed.txt')
        self.assertEqual(owner.crypt_text.value, 'Offline draft')
        self.run_async(owner.save_crypt())
        self.assertEqual(app.cloud_client.data, b'Offline draft')
        self.assertNotIn(b'Offline draft', (folder / 'data').read_bytes())
