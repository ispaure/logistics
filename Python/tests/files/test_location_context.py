"""Storage identity survives docking, navigation, Save As and private locking."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from desktop.documents import DocumentsPage
from desktop.location_context import (
    document_title, install_browser_location, location_catalog, location_context,
)


class LocationContextTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.root = Path(self.temporary_directory().name)
        self.catalog = location_catalog()
        original = self.catalog.roots, self.catalog._local_root
        self.addCleanup(self.restore_catalog, original)
        self.catalog.roots = ((self.root / 'Books', 'Books'),
                              (self.root / 'Books' / 'Nested', 'Nested'))
        self.catalog._local_root = self.root / 'Managed'

    def restore_catalog(self, original):
        self.catalog.roots, self.catalog._local_root = original

    def test_local_title_uses_deepest_workspace_and_follows_save_as(self):
        window = qt.QMainWindow()
        self.addCleanup(window.deleteLater)
        window.current = SimpleNamespace(path=self.root / 'Books' / 'guide.txt')
        window.setWindowTitle('guide.txt * — Text Editor')
        self.assertEqual(document_title(window), 'guide.txt * [Local: Books]')
        window.current.path = self.root / 'Books' / 'Nested' / 'renamed.txt'
        self.assertEqual(document_title(window), 'renamed.txt * [Local: Nested]')
        window.current.path = self.root / 'elsewhere.txt'
        self.assertEqual(document_title(window), 'elsewhere.txt *')
        window.current.path = self.root / 'Managed' / 'Server-Notes' / 'note.txt'
        self.assertEqual(document_title(window), 'note.txt * [Local: Server-Notes]')

    def test_unmanaged_document_titles_use_filename_with_extension(self):
        window = qt.QMainWindow()
        self.addCleanup(window.deleteLater)
        for name in ('A Book.epub', 'Comic.cbz', 'Guide.pdf', 'notes.md'):
            with self.subTest(name=name):
                path = self.root / 'unmanaged' / name
                window.setWindowFilePath(str(path))
                window.setWindowTitle(str(path))
                self.assertEqual(document_title(window), name)

    def test_remote_and_localcrypt_titles_use_provider_not_virtual_paths(self):
        window = qt.QMainWindow()
        self.addCleanup(window.deleteLater)
        provider = SimpleNamespace(root=self.root, remote='Library', remote_storage=True, private=True,
                                   session_only=True)
        window.choice = SimpleNamespace(path='guide.pdf', provider=provider)
        self.assertEqual(document_title(window), 'guide.pdf (🕵️ Session-Only)')
        provider.session_only = False
        self.assertEqual(document_title(window), 'guide.pdf')
        provider.connection = SimpleNamespace(remote='Private-Library')
        self.assertEqual(document_title(window), 'guide.pdf (🕵️ Session-Only)')
        window._private_view_guard = SimpleNamespace(locked=True)
        window.setWindowTitle('Private session locked')
        self.assertEqual(document_title(window), 'Private session locked')

    def test_document_title_survives_detaching_and_updates_in_both_hosts(self):
        host = qt.QMainWindow()
        page = DocumentsPage(lambda: None, host)
        host.setCentralWidget(page)
        self.addCleanup(host.deleteLater)
        window = qt.QMainWindow()
        window.setWindowFilePath(str(self.root / 'Books' / 'guide.pdf'))
        window.setWindowTitle('guide.pdf')
        page.present(window)
        dock = page.records[window]['dock']
        self.assertEqual(dock.windowTitle(), 'guide.pdf [Local: Books]')
        detached = page.workspace.detach_dock(dock)
        self.addCleanup(detached.deleteLater)
        self.assertEqual(detached.windowTitle(), 'Documents: guide.pdf [Local: Books]')
        window.setWindowFilePath(str(self.root / 'Books' / 'Nested' / 'other.pdf'))
        window.setWindowTitle('other.pdf')
        self.assertEqual(dock.windowTitle(), 'other.pdf [Local: Nested]')
        self.assertEqual(detached.windowTitle(), 'Documents: other.pdf [Local: Nested]')
        self.assertEqual(next(page.document_entries())[1], 'other.pdf [Local: Nested]')
        page.attach(window)
        self.assertEqual(dock.windowTitle(), 'other.pdf [Local: Nested]')

    def test_browser_status_updates_with_navigation_and_private_lock(self):
        class Browser(qt.QWidget):
            directory_changed = qt.Signal(object)
            def __init__(self, path):
                super().__init__()
                self.navigation = SimpleNamespace(directory=path)
                qt.QVBoxLayout(self).addWidget(qt.QLabel('Breadcrumbs'))
        browser = Browser(self.root / 'Books')
        self.addCleanup(browser.deleteLater)
        row = install_browser_location(browser)
        self.assertEqual(row.label.text(), 'Local · Books')
        browser.navigation.directory = self.root / 'elsewhere'
        browser.directory_changed.emit(browser.navigation.directory)
        self.assertEqual(row.label.text(), 'Local')
        provider = SimpleNamespace(remote_storage=True, private=True, remote='Books',
                                   encrypted=True, context=Path('keys.session'), closed=False,
                                   session_only=True)
        row.provider = provider
        with patch('features.rclone.session.credentials', return_value={'Books': {}}):
            row.refresh()
            self.assertEqual(row.label.text(), 'Cloud · Unlocked · Books · 🕵️ Session-Only')
            self.assertFalse(row.icon.pixmap().isNull())
            provider.session_only = False
            row.refresh()
            self.assertEqual(row.label.text(), 'Cloud · Unlocked · Books')
            provider.session_only = True
            provider.storage_label = 'Home Server'
            row.refresh()
            self.assertTrue(row.label.text().startswith('Home Server · Unlocked'))
            provider.storage_label = 'Cloud'
        with patch('features.rclone.session.credentials', return_value=None):
            row.refresh()
            self.assertEqual(row.label.text(), 'Cloud · Locked · 🕵️ Session-Only')
            self.assertNotIn('Books', row.toolTip())
        self.assertEqual(location_context(self.root / 'Books').storage, 'Local')
