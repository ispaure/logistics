"""Image documents retain their provider and old pixels on failed navigation."""
from pathlib import Path
from unittest.mock import patch, Mock
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceChoice
from features.images.ui.viewer import ImageWindow
from desktop.documents import DocumentsPage


class ImageViewerTests(QtTestCase):
    def test_navigation_and_storage_chrome_survive_failed_replacement(self):
        root = Path(self.temporary_directory().name)
        image = qt.QImage(32, 20, qt.QImage.Format.Format_RGB32)
        image.fill(qt.QColor('red'))
        for name in ('image2.png', 'image10.png'):
            self.assertTrue(image.save(str(root / name)))
        (root / 'image11.png').write_bytes(b'broken')
        (root / 'nested').mkdir()
        self.assertTrue(image.save(str(root / 'nested/image3.png')))
        release = Mock()
        provider = LocalFiles(root)
        provider.remote_storage = True
        provider.remote = 'Photos'
        provider.session_only = True
        window = ImageWindow(ResourceChoice(provider, 'image2.png', release))
        host = qt.QMainWindow()
        page = DocumentsPage(lambda: None, host)
        host.setCentralWidget(page)
        page.present(window)
        self.wait_until(lambda: not window.operation.busy)
        self.assertFalse(window.pixmap.isNull())
        self.assertFalse(window.previous.isEnabled())
        self.assertTrue(window.following.isEnabled())
        pane = page.records[window]['container']
        self.assertEqual(pane.view_title, 'image2.png (🕵️ Session-Only)')
        self.assertIn('Cloud · Photos · 🕵️ Session-Only · (Read-Only)', pane.storage_location.label.text())
        window.following.click()
        self.wait_until(lambda: not window.operation.busy)
        self.assertEqual(window.choice.path, 'image10.png')
        self.assertEqual(pane.view_title, 'image10.png (🕵️ Session-Only)')
        pixels = window.pixmap.cacheKey()
        with patch.object(qt.QMessageBox, 'warning') as warning:
            window.following.click()
            self.wait_until(lambda: not window.operation.busy)
            warning.assert_called_once()
        self.assertEqual(window.choice.path, 'image10.png')
        self.assertEqual(window.pixmap.cacheKey(), pixels)
        window.previous.click()
        self.wait_until(lambda: not window.operation.busy)
        self.assertEqual(window.choice.path, 'image2.png')
        window.close()
        self.wait_until(lambda: release.called, drain_deferred=True)
