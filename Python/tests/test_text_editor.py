"""Editor document lifecycle and independence from optional reading features."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic,sleep
import unittest
from unittest.mock import patch,Mock
from commonUtils.ui import pyside as qt
from features.text_editor.window import EditorWindow


class TextEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=qt.QApplication.instance() or qt.QApplication([])
    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name);self.addCleanup(self.temp.cleanup)
        self.window=EditorWindow(history_path=self.root/'recent.json')
        self.addCleanup(self.cleanup)
    def cleanup(self):
        self.wait()
        for doc in self.window.documents:doc.editor.document().setModified(False)
        self.window.close();self.window.deleteLater();self.app.processEvents()
    def wait(self):
        deadline=monotonic()+5
        while self.window.task.busy or self.window._queue:
            self.assertLess(monotonic(),deadline);self.app.processEvents();sleep(.005)
        self.app.processEvents()
    def open(self,name,data):
        path=self.root/name;path.write_bytes(data);self.window.open_path(path);self.wait();return path,self.window.current
    def test_open_save_round_trip_and_duplicate_tabs(self):
        for name,data in [('script.py',b'print(1)\r\n'),('.env',b'VAR=1\r'),('bom',b'\xef\xbb\xbfcaf\xc3\xa9')]:
            path,doc=self.open(name,data);count=self.window.tabs.count()
            self.window.open_path(path);self.wait();self.assertEqual(self.window.tabs.count(),count)
            self.window.save_document();self.wait();self.assertEqual(path.read_bytes(),data)
            doc.editor.moveCursor(qt.QTextCursor.MoveOperation.End);doc.editor.insertPlainText(' more')
            self.window.save_document();self.wait();self.assertTrue(path.read_bytes().endswith(b' more'))
    def test_unsaved_close_cancel_discard_save(self):
        doc=self.window.current;doc.editor.insertPlainText('untitled')
        with patch.object(qt.QMessageBox,'question',return_value=qt.QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.window.close_tab(0));self.assertTrue(doc.modified)
        path=self.root/'saved.txt'
        with patch.object(qt.QMessageBox,'question',return_value=qt.QMessageBox.StandardButton.Save),patch.object(qt.QFileDialog,'getSaveFileName',return_value=(str(path),'')):
            self.window.close_tab(0);self.wait()
        self.assertEqual(path.read_text(),'untitled');self.assertEqual(self.window.tabs.count(),0)
    def test_conflict_readonly_missing_and_binary_keep_buffer(self):
        path,doc=self.open('file',b'original');doc.editor.insertPlainText('edit')
        path.write_bytes(b'external')
        with patch.object(self.window,'show_error') as error:
            self.window.save_document();self.wait();error.assert_called_once()
        self.assertEqual(path.read_bytes(),b'external');self.assertTrue(doc.modified)
        doc.snapshot=__import__('commonUtils.text_files',fromlist=['read_text_file']).read_text_file(path)
        path.chmod(0o444)
        with patch.object(self.window,'show_error') as error:
            self.window.save_document();self.wait();self.assertIn('read-only',error.call_args.args[0])
        path.chmod(0o644);path.unlink()
        with patch.object(self.window,'show_error') as error:
            self.window.save_document();self.wait();self.assertIn('deleted',error.call_args.args[0])
        binary=self.root/'binary';binary.write_bytes(b'a\0b');count=self.window.tabs.count()
        with patch.object(qt.QMessageBox,'warning',return_value=qt.QMessageBox.StandardButton.Cancel):
            self.window.open_path(binary);self.wait()
        self.assertEqual(self.window.tabs.count(),count)
        self.window.open_path(binary,force=True);self.wait();self.assertEqual(self.window.current.editor.toPlainText(),'a\0b')
    def test_feature_has_no_dependencies_and_preserves_markdown_activation(self):
        from features import registry,text_editor
        from features.text_editor.contributions import activate_text
        from commonUtils.features import ActionContext
        from commonUtils.fileTypes.markdownType import MarkdownFile
        from commonUtils.fileUtils import File
        self.assertEqual(registry.get_feature_dependencies(text_editor),())
        path=self.root/'note.md';path.write_text('# note')
        self.assertFalse(activate_text(ActionContext(None,None,None,(MarkdownFile(path),))))
        self.assertTrue(activate_text(ActionContext(None,None,None,(File(path),))))
        with patch.object(registry,'load_features',return_value=[text_editor]),patch.object(registry,'_disabled_features',set()),patch.object(registry,'_initialized_features',set()):
            registry.set_feature_enabled('text_editor',False);self.assertFalse(registry.is_feature_enabled('text_editor'))
            registry.set_feature_enabled('text_editor',True);self.assertTrue(registry.is_feature_enabled('text_editor'))
