"""Folder identity follows actual storage and root navigation returns to the Hub."""
from unittest.mock import AsyncMock, patch
import unittest

import toga
from logisticsmobile.browser_ui import FolderLocationHeader
from logisticsmobile.control_icons import icon_button
from test_obsidian import ObsidianTests


class FolderLocationTests(unittest.TestCase):
    setUp = ObsidianTests.setUp
    tearDown = ObsidianTests.tearDown
    run_async = ObsidianTests.run_async

    def test_header_replaces_source_identity_when_location_changes(self):
        button = icon_button('up', 'Parent folder')
        header = FolderLocationHeader(toga.Label('Folder path'), button)
        for path, online, encrypted, expected in (
                ('', False, False, ['storage_local']),
                ('Books', True, True, ['storage_remote', 'storage_crypt']),
                ('Books', False, True, ['storage_local', 'storage_crypt']),
                ('', True, False, ['storage_remote']),
                ('', False, False, ['storage_local'])):
            header.update(path, remote=online, encrypted=encrypted)
            self.assertEqual([child.control_icon for child in header.storage_icons.children], expected)
            self.assertEqual(button.control_icon, 'up' if path else 'back')
            self.assertEqual(button.accessible_name, 'Parent folder' if path else 'Back to Folder Hub')

    def test_root_navigation_returns_to_hub_even_when_cloud_busy(self):
        self.app.show_cloud(present=False)
        self.app.file_path = self.app.cloud_path = ''
        self.app.cloud_busy = True
        with patch.object(self.app, 'show_locations') as hub:
            self.run_async(self.app.parent_file_folder())
            self.run_async(self.app.parent_cloud())
            self.assertEqual(hub.call_count, 2)

    def test_parent_remote_navigation_stays_in_current_storage(self):
        self.app.show_cloud(present=False)
        self.app.cloud_busy = False
        self.app.cloud_path = 'Books/Reference'
        with patch.object(self.app, 'browse_cloud', new=AsyncMock(return_value=True)) as browse, \
                patch.object(self.app, 'show_locations') as hub:
            self.run_async(self.app.parent_cloud())
            self.assertEqual(self.app.cloud_location.value, 'Books')
            browse.assert_awaited_once()
            hub.assert_not_called()

    def test_hub_transfer_banner_only_reports_relevant_rclone_work(self):
        self.app.show_cloud(present=False)
        self.app.folder_source = 'rclone'
        view = self.app.build_folder_picker()
        bar = view.transfer_banner
        self.app.transfer_notification = False
        self.app.transfer_busy = True
        self.app.refresh_transfer_status()
        self.assertIn(bar, view.children)
        for source in ('Local', 'Network shares', 'rclone'):
            self.app.change_folder_source(source)
            self.assertEqual(bar in view.children, source == 'rclone')
        self.app.transfer_busy = False
        self.app.transfer_notification = self.app.transfer_complete = True
        self.app.refresh_transfer_status()
        self.assertNotIn(bar, view.children)
        self.app.transfer_complete = False
        self.app.refresh_transfer_status()
        self.assertIn(bar, view.children)
        self.app.dismiss_transfer_status()
        self.assertNotIn(bar, view.children)
