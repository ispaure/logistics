import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.resource_picker import ResourcePicker
from commonUtils.ui.resource_editor import ResourceTextWindow
from commonUtils.runtime.local_files import LocalFiles
from commonUtils.runtime.resource_selection import ResourceChoice, ResourceTextSession


class EditorResourcePickerTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_picker_and_editor_open_save_as_and_release(self):
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            (root / 'note.txt').write_text('baseline')
            provider = LocalFiles(root)
            released = []
            picker = ResourcePicker([('Storage', lambda: (provider, lambda: released.append('picker')))], name='note.txt')
            self.wait_until(lambda: not picker.browser.operation.busy)
            picker.choose()
            self.wait_until(lambda: not picker.operation.busy)
            self.assertEqual(picker.choice.path, 'note.txt')
            self.assertEqual(released, [])
            choice = picker.choice
            editor = ResourceTextWindow(choice, ResourceTextSession.open(provider, choice.path),
                         lambda *args: ResourceChoice(provider, 'copy.txt', lambda: released.append('copy')), lambda *args: None)
            self.assertEqual(editor.windowTitle(), '🕵️ Private - note.txt — Text Editor')
            editor.editor.setPlainText('private draft')
            editor.save_as()
            self.wait_until(lambda: not editor.operation.busy)
            self.assertEqual(editor.session.path, 'copy.txt')
            self.assertEqual(editor.windowTitle(), '🕵️ Private - copy.txt — Text Editor')
            self.assertEqual((root / 'copy.txt').read_text(), 'private draft')
            self.assertEqual((root / 'note.txt').read_text(), 'baseline')
            self.assertEqual(released, ['picker'])
            editor.editor.setPlainText('retained on conflict')
            (root / 'copy.txt').write_text('external')
            editor.save()
            self.wait_until(lambda: not editor.operation.busy)
            self.assertEqual(editor.editor.toPlainText(), 'retained on conflict')
            self.assertIn('retained', editor.status.text())
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Discard):
                editor.close()
            self.assertEqual(released, ['picker', 'copy'])
            picker.deleteLater()

    def test_private_markdown_loads_images_without_disk_cache(self):
        from services.editor_resources import prepare_editor, make_private_editor
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            (root / 'note.md').write_text('# Private\n![image](image.png)')
            (root / 'image.png').write_bytes(b'image fixture')
            choice = ResourceChoice(LocalFiles(root), 'note.md')
            session = prepare_editor(choice, markdown=True)
            self.assertEqual(session.resources[root / 'image.png'], b'image fixture')
            window = make_private_editor(choice, session, markdown=True)
            self.assertTrue(window.viewer.storage.private)
            self.assertEqual(window.windowTitle(), '🕵️ Private - note.md — Markdown')
            self.assertTrue(window.viewer.open_action.isEnabled())
            window.close()

    def test_picker_storage_titles_and_breadcrumb_navigation(self):
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            (root / 'folder').mkdir()
            local = LocalFiles(root)
            private = LocalFiles(root)
            private.private = True
            picker = ResourcePicker([('Local', lambda: (local, lambda: None)),
                                     ('Crypt', lambda: (private, lambda: None))])
            self.wait_until(lambda: not picker.browser.operation.busy)
            self.assertEqual(picker.windowTitle(), 'Open')
            picker.switch(1)
            self.wait_until(lambda: not picker.browser.operation.busy)
            self.assertEqual(picker.windowTitle(), '🕵️ Private - Open')
            browser = picker.browser
            with patch.object(qt.QFileIconProvider, 'icon', side_effect=AssertionError('Virtual path icon lookup')):
                browser.navigate(root / 'folder')
                self.wait_until(lambda: not browser.operation.busy)
            self.assertEqual(browser.breadcrumbs.paths, [root, root / 'folder'])
            browser.breadcrumbs.root_button.click()
            self.wait_until(lambda: not browser.operation.busy)
            self.assertEqual(browser.navigation.directory, root)
            browser.back.click()
            self.wait_until(lambda: not browser.operation.busy)
            self.assertEqual(browser.navigation.directory, root / 'folder')
            picker.switch(0)
            self.wait_until(lambda: not picker.browser.operation.busy)
            self.assertEqual(picker.windowTitle(), 'Open')
            picker.reject()
            picker.deleteLater()

    def test_reader_launchers_use_shared_picker_with_format_filters(self):
        from features.books.contributions import launch
        from features.comics.ui_contributions import _launch_reader
        with patch('services.reader_resources.choose_editor_resource', return_value=None) as picker:
            self.assertIsNone(launch(None))
            self.assertEqual(picker.call_args.kwargs['extensions'], ('.epub',))
            self.assertIsNone(_launch_reader(None))
            self.assertEqual(picker.call_args.kwargs['extensions'], ('.cbz',))

    def test_reader_picker_local_handoff_closes_choice_before_opening(self):
        from services.reader_resources import choose_reader_document
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            released = []
            choice = ResourceChoice(LocalFiles(root), 'book.epub', lambda: released.append(True))
            def opened(path):
                self.assertEqual(released, [True])
                self.assertEqual(path, root / 'book.epub')
                return 'opened'
            with patch('services.reader_resources.choose_editor_resource', return_value=choice):
                self.assertEqual(choose_reader_document(None, 'epub', open_local=opened), 'opened')

    def test_cancelled_private_reader_open_releases_choice_without_presenting(self):
        from threading import Event
        from commonUtils.ui.resource_picker import ResourceTaskDialog
        from services.reader_resources import open_reader_choice
        release_worker = Event()
        def dialog(parent, title):
            value = ResourceTaskDialog(parent, title)
            qt.QTimer.singleShot(0, value.operation.request_cancel)
            qt.QTimer.singleShot(20, release_worker.set)
            return value
        def read(*args, **kwargs):
            release_worker.wait(2)
            return object()
        with self.temporary_directory() as directory:
            released = []
            provider = LocalFiles(Path(directory))
            provider.private = True
            choice = ResourceChoice(provider, 'book.epub', lambda: released.append(True))
            with patch('services.reader_resources.ResourceTaskDialog', side_effect=dialog), \
                 patch('features.books.epub.EPUBBook', side_effect=read), \
                 patch('services.reader_resources.retain') as present:
                self.assertIsNone(open_reader_choice(choice, None, 'epub'))
            self.assertEqual(released, [True])
            present.assert_not_called()

    def test_failed_private_reader_open_releases_choice(self):
        from services.reader_resources import open_reader_choice
        with self.temporary_directory() as directory:
            released = []
            provider = LocalFiles(Path(directory))
            provider.private = True
            choice = ResourceChoice(provider, 'missing.epub', lambda: released.append(True))
            with patch.object(qt.QMessageBox, 'warning') as warning:
                self.assertIsNone(open_reader_choice(choice, None, 'epub'))
            warning.assert_called_once()
            self.assertEqual(released, [True])
