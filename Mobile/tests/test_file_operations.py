"""Captured file commands, shared cancellation and late UI publication boundaries."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, get_ident
import unittest
from unittest.mock import AsyncMock, patch

from commonUtils.runtime.local_files import LocalFiles
from commonUtils.runtime.operations import check_cancelled, MutationIncomplete, MutationResult
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.file_operations import FileDestination, FileOperationRequest, FileOperations, FileOperationsHost
from logisticsmobile import file_operations


class FileOperationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        LogisticsMobile.storage_root = self.root
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.run_async = self.app.loop.run_until_complete
        self.run_async(self.app.show_files())
        self.source = self.app.file_provider
        (self.source.root / 'first.txt').write_text('First')
        (self.source.root / 'second.txt').write_text('Second')
        destination = self.root / 'destination'
        destination.mkdir()
        self.destination = LocalFiles(destination)
        self.app.file_roots['Destination'] = self.destination
        self.app.file_destination.items = ['Destination']
        self.app.file_destination.value = 'Destination'
        self.run_async(self.app.browse_files())
        self.select('first.txt')

    def tearDown(self):
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.temporary.cleanup()

    def select(self, name):
        self.app.file_selection.value = next(key for key, row in self.app.file_rows.items() if row['name'] == name)

    def test_create_rename_move_and_confirmed_delete_use_existing_resource_operations(self):
        app = self.app
        app.file_name.value = 'New folder'
        self.run_async(app.new_file_folder())
        self.assertTrue((self.source.root / 'New folder').is_dir())
        self.select('first.txt')
        app.file_name.value = 'renamed.txt'
        self.run_async(app.rename_file())
        self.assertEqual((self.source.root / 'renamed.txt').read_text(), 'First')
        self.select('renamed.txt')
        app.file_target.value = 'moved.txt'
        self.run_async(app.move_file())
        self.assertEqual((self.destination.root / 'moved.txt').read_text(), 'First')
        self.assertFalse((self.source.root / 'renamed.txt').exists())
        self.select('New folder')
        with patch.object(app.main_window, 'dialog', AsyncMock(return_value=True)):
            self.run_async(app.delete_file())
        self.assertFalse((self.source.root / 'New folder').exists())
        self.assertFalse(app.cloud_busy)
        self.assertIsNone(app._crypt_cancel)

    def test_row_actions_stay_in_browser_and_retire_when_listing_changes(self):
        browser = self.app.file_browser
        row = next(row for row in browser.native_list.data if row.entry.payload['name'] == 'first.txt')
        view = self.app.body
        self.run_async(browser._select_row(row))
        menu = browser._item_menu
        self.assertIs(self.app.body, view)
        titles = [title for title, _ in menu.actions]
        self.assertIn('Rename…', titles)
        self.assertIn('Move…', titles)
        with patch.object(self.app, 'show_file_actions') as show:
            menu.invoke(next(callback for title, callback in menu.actions if title == 'Rename…'))
            show.assert_called_once_with(operation='rename')
        self.run_async(self.app.browse_files())
        self.assertTrue(menu.disposed)
        self.assertEqual(menu.actions, ())

    def test_delete_keeps_the_confirmed_target_if_selection_changes_in_dialog(self):
        async def confirm(dialog):
            self.select('second.txt')
            return True
        with patch.object(self.app.main_window, 'dialog', side_effect=confirm):
            self.run_async(self.app.delete_file())
        self.assertFalse((self.source.root / 'first.txt').exists())
        self.assertEqual((self.source.root / 'second.txt').read_text(), 'Second')

    def test_refused_confirmation_has_no_side_effects(self):
        with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value=False)):
            self.run_async(self.app.delete_file())
        self.assertTrue((self.source.root / 'first.txt').exists())
        self.assertFalse(self.app.cloud_busy)
        self.assertFalse(hasattr(self.app, '_file_operations'))

    def test_move_does_not_overwrite_an_existing_destination(self):
        (self.destination.root / 'existing.txt').write_text('Keep destination')
        self.app.file_target.value = 'existing.txt'
        self.run_async(self.app.move_file())
        self.assertEqual((self.source.root / 'first.txt').read_text(), 'First')
        self.assertEqual((self.destination.root / 'existing.txt').read_text(), 'Keep destination')
        self.assertIn('Operation failed:', self.app.file_status.value)
        self.assertTrue(self.app.file_actions_button.enabled)

    def test_worker_uses_captured_source_and_name_and_leaves_new_screen_status_alone(self):
        started, release = Event(), Event()
        original = file_operations.rename_resource
        ui_thread = get_ident()
        def rename(*args, **kwargs):
            self.assertNotEqual(get_ident(), ui_thread)
            started.set()
            if not release.wait(4):
                raise RuntimeError('Worker fixture was not released')
            return original(*args, **kwargs)
        async def exercise():
            self.app.file_name.value = 'captured.txt'
            task = asyncio.create_task(self.app.rename_file())
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                self.app.file_provider = self.destination
                self.app.file_path = 'another-folder'
                self.app.file_name.value = 'wrong.txt'
                self.app.file_status.value = 'New screen status'
                release.set()
                await task
            finally:
                release.set()
                await task
        with patch('logisticsmobile.file_operations.rename_resource', side_effect=rename), \
                patch.object(self.app, 'browse_files', AsyncMock()) as browse:
            self.run_async(exercise())
        self.assertEqual((self.source.root / 'captured.txt').read_text(), 'First')
        self.assertFalse((self.destination.root / 'wrong.txt').exists())
        self.assertEqual(self.app.file_status.value, 'New screen status')
        browse.assert_not_awaited()
        self.assertFalse(self.app.cloud_busy)

    def test_destination_resolution_runs_in_worker_with_captured_mapping_and_target(self):
        started, release = Event(), Event()
        original = FileDestination.resolve
        ui_thread = get_ident()
        def resolve(destination):
            self.assertNotEqual(get_ident(), ui_thread)
            started.set()
            if not release.wait(4):
                raise RuntimeError('Worker fixture was not released')
            return original(destination)
        async def exercise():
            self.app.file_target.value = 'captured.txt'
            task = asyncio.create_task(self.app.move_file())
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                self.app.file_roots['Destination'] = self.source
                self.app.file_target.value = 'wrong.txt'
                release.set()
                await task
            finally:
                release.set()
                await task
        # The post-operation browse resolves providers on the UI thread by design.
        with patch.object(FileDestination, 'resolve', resolve), \
                patch.object(self.app, 'browse_files', AsyncMock()), \
                patch.object(self.app, 'refresh_crypt', AsyncMock()):
            self.run_async(exercise())
        self.assertEqual((self.destination.root / 'captured.txt').read_text(), 'First')
        self.assertFalse((self.source.root / 'wrong.txt').exists())

    def test_busy_transfer_and_dirty_reader_guards_do_not_start_worker(self):
        work = unittest.mock.Mock()
        self.app.cloud_busy = self.app.transfer_busy = True
        self.assertFalse(self.run_async(self.app.file_work(work)))
        self.app.cloud_busy = self.app.transfer_busy = False
        with patch.object(self.app, 'clear_private_reader', return_value=False):
            self.assertFalse(self.run_async(self.app.file_work(work)))
        work.assert_not_called()
        self.assertIsNone(self.app.file_operations().cancel_event)

    def check_cancel(self, cancel_task):
        started, release = Event(), Event()
        observed = []
        def work(cancelled):
            observed.append(cancelled)
            started.set()
            if not release.wait(4):
                raise RuntimeError('Worker fixture was not released')
            check_cancelled(cancelled)
        async def exercise():
            task = asyncio.create_task(self.app.file_work(work))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                self.assertIs(self.app._crypt_cancel, self.app.file_operations().cancel_event)
                if cancel_task:
                    task.cancel()
                    await asyncio.sleep(0)
                else:
                    self.app.cancel_cloud()
                self.assertTrue(observed[0]())
                self.assertTrue(self.app.cloud_busy)
                self.assertFalse(self.app.file_actions_button.enabled)
                self.assertFalse(await self.app.file_work(lambda cancelled: self.fail('Parallel operation')))
                release.set()
                if cancel_task:
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                else:
                    self.assertFalse(await task)
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)
        self.run_async(exercise())
        self.assertFalse(self.app.cloud_busy)
        self.assertIsNone(self.app._crypt_cancel)
        self.assertIsNone(self.app.file_operations().task)
        self.assertTrue(self.app.file_actions_button.enabled)
        self.assertTrue((self.source.root / 'first.txt').exists())

    def test_existing_cancel_control_signals_the_owned_worker(self):
        self.check_cancel(False)

    def test_task_cancellation_keeps_busy_guard_until_worker_retires(self):
        self.check_cancel(True)

    def test_partial_failure_keeps_specific_warning_and_restores_controls(self):
        def fail(cancelled):
            raise MutationIncomplete('Source partly removed.', MutationResult(source_state='partial'))
        self.assertFalse(self.run_async(self.app.file_work(fail)))
        self.assertEqual(self.app.file_status.value, 'Source partly removed.\nRefresh before retrying.')
        self.assertEqual(self.app.file_action_status.text, self.app.file_status.value)
        self.assertFalse(self.app.cloud_busy)
        self.assertTrue(self.app.file_actions_button.enabled)

    def test_capture_failure_is_reported_and_can_be_retried(self):
        self.app.file_destination.items = ['Missing location']
        self.app.file_destination.value = 'Missing location'
        self.run_async(self.app.move_file())
        self.assertIn('Missing location', self.app.file_status.value)
        self.assertTrue(self.app.file_actions_button.enabled)
        self.assertIsNone(self.app.file_operations().cancel_event)
        self.app.file_destination.items = ['Destination']
        self.app.file_destination.value = 'Destination'
        self.app.file_target.value = 'retried.txt'
        self.run_async(self.app.move_file())
        self.assertTrue((self.destination.root / 'retried.txt').exists())

    def test_late_error_does_not_replace_status_after_navigation_or_host_retirement(self):
        for invalidation in ('navigation', 'host'):
            with self.subTest(invalidation=invalidation):
                started, release = Event(), Event()
                def work(cancelled):
                    started.set()
                    if not release.wait(4):
                        raise RuntimeError('Worker fixture was not released')
                    raise OSError('Obsolete operation error')
                async def exercise():
                    task = asyncio.create_task(self.app.file_work(work))
                    try:
                        self.assertTrue(await asyncio.to_thread(started.wait, 3))
                        if invalidation == 'navigation':
                            self.app.navigation_generation += 1
                        else:
                            self.app.active_host = False
                        self.app.file_status.value = 'Current status'
                        self.app.file_action_status.text = 'Current actions'
                        release.set()
                        self.assertFalse(await task)
                    finally:
                        release.set()
                        await task
                        self.app.active_host = True
                self.run_async(exercise())
                self.assertEqual(self.app.file_status.value, 'Current status')
                self.assertEqual(self.app.file_action_status.text, 'Current actions')
                self.assertFalse(self.app.cloud_busy)

    def test_captured_encrypted_destination_rejects_replaced_credentials_before_resolution(self):
        from types import SimpleNamespace
        client = SimpleNamespace(generation=1)
        destination = FileDestination(self.root, client, 'Secret', client.generation)
        client.generation = 2
        with patch('logisticsmobile.file_operations.encrypted_storage') as resolve:
            with self.assertRaisesRegex(ValueError, 'Connection changed'):
                destination.resolve()
        resolve.assert_not_called()

    def test_invalid_names_and_protected_root_never_mutate_storage(self):
        for request in (FileOperationRequest('new', self.source, '', '../bad'),
                        FileOperationRequest('rename', self.source, 'first.txt', '../bad'),
                        FileOperationRequest('delete', self.source, '')):
            with self.subTest(kind=request.kind), self.assertRaises(ValueError):
                request.execute(lambda: False)
        self.assertTrue((self.source.root / 'first.txt').exists())
        self.assertTrue(self.source.root.exists())

    def test_begin_failure_does_not_latch_the_coordinator_busy(self):
        begin = unittest.mock.Mock(side_effect=[RuntimeError('Could not bind controls'), object()])
        host = FileOperationsHost(allowed=lambda mutation: True, begin=begin,
            current=lambda view: True, report=unittest.mock.Mock(), finish=unittest.mock.Mock())
        coordinator = FileOperations(host)
        with self.assertRaisesRegex(RuntimeError, 'Could not bind controls'):
            self.run_async(coordinator.run(lambda: lambda cancelled: None))
        self.assertIsNone(coordinator.cancel_event)
        self.assertIsNone(coordinator.task)
        self.assertTrue(self.run_async(coordinator.run(lambda: lambda cancelled: None)))
        self.assertEqual(host.finish.call_count, 1)

    def test_retired_operation_cannot_release_another_cancellation_owner(self):
        started, release = Event(), Event()
        replacement = Event()
        def work(cancelled):
            started.set()
            if not release.wait(4):
                raise RuntimeError('Worker fixture was not released')
        async def exercise():
            task = asyncio.create_task(self.app.file_work(work))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                self.app._crypt_cancel = replacement
                self.app.file_status.value = 'New operation status'
                release.set()
                self.assertFalse(await task)
                self.assertTrue(self.app.cloud_busy)
                self.assertIs(self.app._crypt_cancel, replacement)
                self.assertEqual(self.app.file_status.value, 'New operation status')
            finally:
                release.set()
                await task
                self.app._crypt_cancel = None
                self.app.set_cloud_busy(False)
        self.run_async(exercise())
