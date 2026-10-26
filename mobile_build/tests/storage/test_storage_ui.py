"""Storage settings gate switching on permission, active work and confirmation."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from mobile.app import LogisticsMobile
from services.documents.locations import collection_path, switch_location


class StorageUITests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.card = root / 'card'
        self.card.mkdir()
        private = root / 'app'
        private.mkdir()
        LogisticsMobile.storage_root = private
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
        sdk = patch('mobile.storage_ui.android_sdk', return_value=30)
        sdk.start()
        self.addCleanup(sdk.stop)
        with patch('mobile.storage_ui.android_drives', return_value={'App internal storage': None, 'SD card': self.card}):
            self.app.show_collection_storage()
        self.app.collection_drive.value = 'SD card'

    def test_android9_sd_card_copy_needs_no_all_files_grant(self):
        source = collection_path(self.app.private_root)
        source.mkdir(exist_ok=True)
        (source / 'book.txt').write_bytes(b'keep this')
        with patch('mobile.storage_ui.android_sdk', return_value=28), \
                patch('mobile.storage_ui.android_drives', return_value={'App internal storage': None, 'SD card': self.card}), \
                patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)), \
                patch.object(self.app, 'exit') as exit_app:
            self.app.show_collection_storage()
            text = ' '.join(str(getattr(child, 'text', '')) for child in self.app.collection_storage_page.children)
            self.assertIn('No storage permission is needed', text)
            self.assertIn('uninstall', text)
            self.assertNotIn('Allow SD card / shared storage access', text)
            self.app.collection_drive.value = 'SD card'
            self.app.loop.run_until_complete(self.app.change_collection_storage())
        self.assertEqual((self.card / 'Logistics/Local/book.txt').read_bytes(), b'keep this')
        self.assertEqual((source / 'book.txt').read_bytes(), b'keep this')
        self.assertEqual(collection_path(self.app.private_root), self.card / 'Logistics/Local')
        exit_app.assert_called_once()

    def test_android9_permission_action_refreshes_without_opening_settings(self):
        with patch('mobile.storage_ui.android_sdk', return_value=28), \
                patch.object(self.app, 'show_collection_storage') as refresh:
            self.app.allow_collection_storage()
        refresh.assert_called_once_with()

    def test_permission_is_required_without_writing_files(self):
        with patch('mobile.storage_ui.all_files_allowed', return_value=False):
            self.app.loop.run_until_complete(self.app.change_collection_storage())
        self.assertIn('enable permission', ' '.join(self.app.collection_storage_status.text.split()))
        self.assertFalse((self.card / 'Logistics').exists())

    def test_confirmation_cancel_does_not_switch(self):
        with patch('mobile.storage_ui.all_files_allowed', return_value=True), \
                patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=False)):
            self.app.loop.run_until_complete(self.app.change_collection_storage())
        self.assertFalse((self.card / 'Logistics').exists())

    def test_confirmation_rechecks_work_and_restores_controls_without_running_storage(self):
        for action in ('copy', 'recover', 'empty', 'wipe'):
            for changed_state in ('busy', 'checkpoint'):
                with self.subTest(action=action, changed_state=changed_state):
                    async def confirm(dialog):
                        self.assertTrue(self.app._storage_changing)
                        self.assertFalse(self.app.collection_drive.enabled)
                        self.assertFalse(self.app.collection_copy.enabled)
                        if changed_state == 'busy':
                            self.app.transfer_busy = True
                        else:
                            checkpoint.return_value = False
                        return True

                    with patch('mobile.storage_ui.all_files_allowed', return_value=True), \
                            patch.object(self.app, 'checkpoint', return_value=True) as checkpoint, \
                            patch.object(self.app.main_window, 'dialog', new=AsyncMock(side_effect=confirm)), \
                            patch('mobile.storage_ui.asyncio.to_thread', new_callable=AsyncMock) as worker:
                        operation = {'copy': self.app.change_collection_storage,
                                     'recover': self.app.recover_collection_storage,
                                     'empty': self.app.start_empty_collection,
                                     'wipe': self.app.wipe_collection_storage}[action]
                        self.app.loop.run_until_complete(operation(self.app.collection_copy))
                    worker.assert_not_awaited()
                    self.assertFalse(self.app._storage_changing)
                    self.assertTrue(self.app.collection_drive.enabled)
                    self.assertTrue(self.app.collection_copy.enabled)
                    self.assertFalse(self.app.cloud_busy)
                    self.assertFalse((self.card / 'Logistics').exists())
                    self.app.transfer_busy = False

    def test_switch_verifies_data_and_closes_app_for_restart(self):
        source = collection_path(self.app.private_root)
        source.mkdir(exist_ok=True)
        (source / 'book.txt').write_bytes(b'keep this')
        with patch('mobile.storage_ui.all_files_allowed', return_value=True), \
                patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)), \
                patch.object(self.app, 'exit') as exit_app:
            self.app.loop.run_until_complete(self.app.change_collection_storage())
        self.assertEqual((self.card / 'Logistics/Local/book.txt').read_bytes(), b'keep this')
        self.assertFalse(self.app.cloud_busy)
        exit_app.assert_called_once()

    def test_worker_progress_is_rendered_and_failure_keeps_retry_available(self):
        import threading
        ui_thread = threading.get_ident()
        def fail(root, volume, *, progress):
            self.assertNotEqual(threading.get_ident(), ui_thread)
            progress(dict(phase='Copying Local', path='Local/book.epub', bytes=1024, total=2048, files=0))
            raise OSError('Card disconnected')
        with patch('mobile.storage_ui.all_files_allowed', return_value=True), \
                patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)), \
                patch('mobile.storage_ui.switch_location', side_effect=fail):
            self.app.loop.run_until_complete(self.app.change_collection_storage())
        page = self.app.collection_storage_page
        text = ' '.join(str(getattr(child, 'text', '')) for child in page.children)
        self.assertIn('Card disconnected', text)
        self.assertIn('Stopped before completion', text)
        self.assertTrue(page.children[-1].enabled)
        self.assertFalse(self.app._storage_changing)
        self.assertFalse(self.app.cloud_busy)
        self.assertFalse((self.card / 'Logistics').exists())

    def test_busy_operation_prevents_switch(self):
        self.app.transfer_busy = True
        self.app.loop.run_until_complete(self.app.change_collection_storage())
        self.assertIn('Wait', self.app.collection_storage_status.text)
        self.assertFalse((self.card / 'Logistics').exists())

    def test_preview_identifies_target_and_never_offers_erasing_active_location(self):
        self.assertIn('NOT CURRENTLY IN USE', self.app.collection_target_status.text)
        self.assertTrue(self.app.collection_erase.enabled)
        self.app.collection_drive.value = 'App internal storage'
        self.assertIn('CURRENTLY IN USE', self.app.collection_target_status.text)
        self.assertFalse(self.app.collection_erase.enabled)
        self.assertFalse(self.app.collection_copy.enabled)

    def test_start_empty_keeps_current_files_and_closes_after_confirming(self):
        old = collection_path(self.app.private_root)
        old.mkdir(exist_ok=True)
        (old / 'keep.txt').write_text('old')
        with patch('mobile.storage_ui.all_files_allowed', return_value=True), \
                patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)), \
                patch.object(self.app, 'exit') as exit_app:
            self.app.loop.run_until_complete(self.app.start_empty_collection())
        self.assertEqual((old / 'keep.txt').read_text(), 'old')
        self.assertFalse(list(collection_path(self.app.private_root).iterdir()))
        exit_app.assert_called_once()

    def test_recover_internal_after_card_removal_without_cloud_browser(self):
        source = collection_path(self.app.private_root)
        source.mkdir(exist_ok=True)
        (source / 'book.txt').write_bytes(b'backup')
        switch_location(self.app.private_root, self.card)
        self.card.rename(self.card.parent / 'removed')
        self.app.collection_drive.value = 'App internal storage'
        with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)), \
                patch.object(self.app, 'exit') as exit_app:
            self.app.loop.run_until_complete(self.app.recover_collection_storage())
        self.assertEqual(collection_path(self.app.private_root), source)
        self.assertFalse(self.app.cloud_busy)
        exit_app.assert_called_once()

    def test_cancel_wipe_preserves_files_and_success_keeps_app_open(self):
        target = self.card / 'Logistics/Local/old.txt'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'old')
        with patch('mobile.storage_ui.all_files_allowed', return_value=True), \
                patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=False)):
            self.app.loop.run_until_complete(self.app.wipe_collection_storage())
        self.assertTrue(target.exists())
        self.assertFalse(self.app._storage_changing)
        with patch('mobile.storage_ui.all_files_allowed', return_value=True), \
                patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)), \
                patch.object(self.app, 'exit') as exit_app:
            self.app.loop.run_until_complete(self.app.wipe_collection_storage())
        self.assertFalse(target.exists())
        self.assertIn('erased', self.app.collection_storage_status.text)
        self.assertFalse(self.app.cloud_busy)
        exit_app.assert_not_called()
