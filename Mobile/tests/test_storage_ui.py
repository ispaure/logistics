"""Storage settings gate switching on permission, active work and confirmation."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from logisticsmobile.app import LogisticsMobile
from features.rclone.mobile.storage_location import collection_path


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
        with patch('logisticsmobile.storage_ui.android_drives', return_value={'App internal storage': None, 'SD card': self.card}):
            self.app.show_collection_storage()
        self.app.collection_drive.value = 'SD card'

    def test_permission_is_required_without_writing_files(self):
        with patch('logisticsmobile.storage_ui.all_files_allowed', return_value=False):
            self.app.loop.run_until_complete(self.app.change_collection_storage())
        self.assertIn('enable permission', self.app.collection_storage_status.text)
        self.assertFalse((self.card / 'Logistics').exists())

    def test_confirmation_cancel_does_not_switch(self):
        with patch('logisticsmobile.storage_ui.all_files_allowed', return_value=True), \
                patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=False)):
            self.app.loop.run_until_complete(self.app.change_collection_storage())
        self.assertFalse((self.card / 'Logistics').exists())

    def test_switch_verifies_data_and_closes_app_for_restart(self):
        source = collection_path(self.app.private_root)
        source.mkdir(exist_ok=True)
        (source / 'book.txt').write_bytes(b'keep this')
        with patch('logisticsmobile.storage_ui.all_files_allowed', return_value=True), \
                patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)), \
                patch.object(self.app, 'exit') as exit_app:
            self.app.loop.run_until_complete(self.app.change_collection_storage())
        self.assertEqual((self.card / 'Logistics/Local/book.txt').read_bytes(), b'keep this')
        self.assertFalse(self.app.cloud_busy)
        exit_app.assert_called_once()

    def test_busy_operation_prevents_switch(self):
        self.app.transfer_busy = True
        self.app.loop.run_until_complete(self.app.change_collection_storage())
        self.assertIn('Wait', self.app.collection_storage_status.text)
        self.assertFalse((self.card / 'Logistics').exists())
