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


class ProjectTests(__import__('unittest').TestCase):
    def test_roundtrip_missing_root_sources_and_conflicting_instance(self):
        from features.ide.projects import Project, ProjectStore
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(Path(directory) / 'IDE' / 'workspace.json')
            project = Project('Example', str(Path(directory) / 'missing'), source_paths=['.', 'src', 'src'])
            store.projects[project.id] = project
            store.open_ids = [project.id]
            store.save()
            restored = ProjectStore(store.path)
            self.assertEqual(restored.open_ids, [project.id])
            self.assertEqual(len(restored.projects[project.id].sources()), 2)
            restored.active_id = project.id
            restored.save()
            with self.assertRaises(OSError):
                store.save()

    def test_malformed_store_is_not_overwritten(self):
        from features.ide.projects import ProjectStore
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'workspace.json'
            path.write_text('{bad')
            store = ProjectStore(path)
            with self.assertRaises(ValueError):
                store.save()
            self.assertEqual(path.read_text(), '{bad')


class WorkspaceTests(DocumentTests):
    def wait(self, view):
        import time
        deadline = time.monotonic() + 5
        while view.worker or view.queue:
            self.app.processEvents()
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.001)

    def test_canonical_buffer_moves_and_group_close_preserves_unsaved_text(self):
        from features.ide.projects import Project
        from features.ide.workspace import ProjectWorkspace
        from unittest.mock import patch
        from commonUtils.ui import pyside as qt
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'a.py'
            path.write_text('value = 1\n')
            view = ProjectWorkspace(Project('one', directory))
            view.open_path(path)
            self.wait(view)
            doc = view.current
            doc.insertPlainText('# changed\n')
            view.move(1)
            view.open_path(path)
            self.wait(view)
            self.assertEqual(len(view.documents), 1)
            self.assertIs(view.current, doc)
            view.close_group()
            self.assertEqual(len(view.groups), 1)
            self.assertTrue(doc.document().isModified())
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
                self.assertFalse(view.can_close())
                self.assertFalse(view.close_document(doc))
            self.assertTrue(view.save_document(doc))
            self.assertTrue(view.can_close())
            self.assertTrue(view.prepare_close())
            view.close()
