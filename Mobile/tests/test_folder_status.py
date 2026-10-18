"""Folder identity is independent of listing, download and failure messages."""
import unittest

from logisticsmobile.browser_ui import FileBrowser
from logisticsmobile.control_icons import icon_button


class FolderStatusTests(unittest.TestCase):
    def test_operations_update_only_the_smaller_line_below_the_folder(self):
        browser = FileBrowser()
        self.addCleanup(browser.stop)
        status = browser.status_label('')
        header = browser.location_header(status, icon_button('up', 'Parent folder'))
        header.update('Books/Fiction')
        for message in ('Loading folder contents…', 'Downloading chapter.epub · 1.2 MiB',
                        'Displaying 8 items', 'Download failed: connection interrupted', ''):
            status.value = message
            self.assertEqual(header.folder_name.value, 'Fiction')
            self.assertEqual(header.status.value, message)
            self.assertEqual(header.caption.children, [header.folder_name, status] if message else [header.folder_name, header.storage_identity])
            self.assertLess(status.style.font_size, header.folder_name.style.font_size)
            self.assertEqual(status.style.height, 18)
        self.assertGreaterEqual(header.folder_name.style.font_size, 20)
        self.assertFalse(header.folder_name._impl._surface_eink_outlined)
        self.assertFalse(status._impl._surface_eink_outlined)
        status.value = 'Opening folder…'
        self.assertEqual(header.caption.children, [header.folder_name, status])

    def test_remote_and_local_roots_keep_their_storage_name(self):
        browser = FileBrowser()
        self.addCleanup(browser.stop)
        status = browser.status_label('Listing…')
        header = browser.location_header(status, icon_button('up', 'Parent folder'))
        for name, remote in (('Local files', False), ('My remote', True)):
            header.update('', remote=remote, name=name)
            status.value = 'Downloading…'
            self.assertEqual(header.folder_name.value, name)
            self.assertEqual(header.parent_button.control_icon, 'back')
