
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceChoice


class EditorResourcePickerTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_private_markdown_loads_images_without_disk_cache(self):
        from services.documents.ui.editors import prepare_editor, make_private_editor
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            (root / 'note.md').write_text('# Private\n![image](image.png)')
            (root / 'image.png').write_bytes(b'image fixture')
            provider = LocalFiles(root)
            provider.private = True
            choice = ResourceChoice(provider, 'note.md')
            session = prepare_editor(choice, markdown=True)
            self.assertEqual(session.resources[root / 'image.png'], b'image fixture')
            window = make_private_editor(choice, session, markdown=True)
            self.assertTrue(window.viewer.storage.private)
            self.assertEqual(window.windowTitle(), '🕵️ Private - note.md — Markdown')
            self.assertTrue(window.viewer.open_action.isEnabled())
            window.close()

    def test_reader_launchers_use_shared_picker_with_format_filters(self):
        from features.books.contributions import launch
        from features.comics.ui_contributions import _launch_reader
        with patch('services.documents.ui.readers.choose_editor_resource', return_value=None) as picker:
            self.assertIsNone(launch(None))
            self.assertEqual(picker.call_args.kwargs['extensions'], ('.epub',))
            self.assertIsNone(_launch_reader(None))
            self.assertEqual(picker.call_args.kwargs['extensions'], ('.cbz',))

    def test_reader_picker_local_handoff_closes_choice_before_opening(self):
        from services.documents.ui.readers import choose_reader_document
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            released = []
            choice = ResourceChoice(LocalFiles(root), 'book.epub', lambda: released.append(True))
            def opened(path):
                self.assertEqual(released, [True])
                self.assertEqual(path, root / 'book.epub')
                return 'opened'
            with patch('services.documents.ui.readers.choose_editor_resource', return_value=choice):
                self.assertEqual(choose_reader_document(None, 'epub', open_local=opened), 'opened')

    def test_cancelled_private_reader_open_releases_choice_without_presenting(self):
        from threading import Event
        from commonUtils.ui.resources.picker import ResourceTaskDialog
        from services.documents.ui.readers import open_reader_choice
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
            with patch('services.documents.ui.readers.ResourceTaskDialog', side_effect=dialog), \
                 patch('features.books.epub.EPUBBook', side_effect=read), \
                 patch('services.documents.ui.readers.retain') as present:
                self.assertIsNone(open_reader_choice(choice, None, 'epub'))
            self.assertEqual(released, [True])
            present.assert_not_called()

    def test_failed_private_reader_open_releases_choice(self):
        from services.documents.ui.readers import open_reader_choice
        with self.temporary_directory() as directory:
            released = []
            provider = LocalFiles(Path(directory))
            provider.private = True
            choice = ResourceChoice(provider, 'missing.epub', lambda: released.append(True))
            with patch.object(qt.QMessageBox, 'warning') as warning:
                self.assertIsNone(open_reader_choice(choice, None, 'epub'))
            warning.assert_called_once()
            self.assertEqual(released, [True])
