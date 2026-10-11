import tempfile
from pathlib import Path
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.persistence.text import read_text_file, FileConflictError
from features.ide.documents import EditorDocument


class DocumentTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        from commonUtils.ui import pyside as qt
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_shared_editor_preserves_endings_and_refuses_external_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'example.py'
            path.write_bytes(b'x = 1\r\n')
            editor = EditorDocument(read_text_file(path))
            editor.setPlainText('x = 2\n')
            editor.save()
            self.assertEqual(path.read_bytes(), b'x = 2\r\n')
            path.write_bytes(b'external\n')
            editor.setPlainText('mine\n')
            with self.assertRaises(FileConflictError):
                editor.save()
            self.assertEqual(path.read_bytes(), b'external\n')
            editor.close()
