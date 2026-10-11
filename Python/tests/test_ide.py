import tempfile
import unittest
from pathlib import Path
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.persistence.text import read_text_file, FileConflictError
from features.ide.documents import EditorDocument


class IDEQtTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        from commonUtils.ui import pyside as qt
        cls.app = qt.QApplication.instance() or qt.QApplication([])


class DocumentTests(IDEQtTests):
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
            editor.document().setModified(True)
            with self.assertRaises(FileConflictError):
                editor.save()
            self.assertEqual(path.read_bytes(), b'external\n')
            self.assertTrue(editor.document().isModified())
            path.unlink()
            with self.assertRaises(FileConflictError):
                editor.save()
            self.assertFalse(path.exists())
            editor.close()


class ProjectTests(unittest.TestCase):
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


class WorkspaceFixture(IDEQtTests):
    def wait(self, view):
        import time
        deadline = time.monotonic() + 5
        while view.worker or view.queue:
            self.app.processEvents()
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.001)


class WorkspaceTests(WorkspaceFixture):
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
            view.add_group()
            view.add_group()
            self.assertIsNone(view.add_group())
            self.assertEqual(len(view.groups), 3)
            view.activate(view.group_for(doc))
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
                self.assertFalse(view.can_close())
                self.assertFalse(view.close_document(doc))
            self.assertTrue(view.save_document(doc))
            self.assertTrue(view.can_close())
            self.assertTrue(view.prepare_close())
            view.close()


class NavigationTests(unittest.TestCase):
    def test_import_definition_with_src_layout_and_relative_import(self):
        from features.ide.projects import Project
        from features.ide.analysis import analyze, project_files
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'src' / 'sample'
            package.mkdir(parents=True)
            (package / '__init__.py').write_text('')
            (package / 'models.py').write_text('class Widget:\n    pass\n')
            path = package / 'main.py'
            code = 'from .models import Widget\nvalue = Widget()\n'
            path.write_text(code)
            project = Project('Example', directory, source_paths=['src'])
            result = analyze(project, path, code, 2, 10)
            self.assertEqual(result[0][:2], (str(package / 'models.py'), 1))
            code = 'from sample.models import Widget\nvalue = Widget()\n'
            self.assertEqual(Path(analyze(project, root / 'test.py', code, 2, 10)[0][0]).resolve(), (package / 'models.py').resolve())
            (root / '.venv').mkdir()
            (root / '.venv' / 'hidden.py').write_text('')
            self.assertFalse(any('.venv' in p for p in project_files(project)))

    def test_project_search_skips_binary_exclusions_and_supports_cancellation(self):
        from features.ide.projects import Project
        from features.ide.analysis import search_project
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.py').write_text('needle\n')
            (root / 'binary').write_bytes(b'needle\x00')
            (root / '.git').mkdir()
            (root / '.git' / 'secret').write_text('needle')
            project = Project('test', directory)
            results = search_project(project, 'NEEDLE')
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][1], 1)
            self.assertEqual(search_project(project, 'needle', cancelled=lambda: True), [])


class RestoreTests(WorkspaceFixture):
    def test_independent_projects_layout_and_missing_files_survive_restart(self):
        from features.ide.page import IDEPage
        from features.ide.projects import Project
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state = root / 'IDE' / 'workspace.json'
            a, b = root / 'a.py', root / 'b.py'
            a.write_text('a = 1\n')
            b.write_text('b = 2\n')
            page = IDEPage(store_path=state)
            first, second = Project('first', str(root)), Project('second', str(root))
            for p in (first, second):
                page.store.projects[p.id] = p
            one = page.open_project(first)
            one.open_path(a)
            self.wait(one)
            one.move(1)
            two = page.open_project(second)
            two.open_path(b)
            self.wait(two)
            self.assertIsNot(one.documents[a], two.documents[b])
            self.assertTrue(page.prepare_close())
            page.close()
            b.unlink()
            restored = IDEPage(store_path=state)
            for i in range(restored.tabs.count()):
                self.wait(restored.tabs.widget(i))
            self.assertEqual(restored.tabs.count(), 2)
            self.assertEqual(len(restored.tabs.widget(0).groups), 2)
            self.assertEqual(restored.tabs.widget(1).unavailable[0]['path'], str(b))
            self.assertTrue(restored.prepare_close())
            restored.close()

    def test_stale_analysis_result_does_not_navigate(self):
        from features.ide.workspace import ProjectWorkspace
        from features.ide.projects import Project
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'a.py'
            path.write_text('value = 1\nvalue\n')
            view = ProjectWorkspace(Project('test', directory))
            view.open_path(path)
            self.wait(view)
            pending = []
            with patch.object(view, 'run', side_effect=lambda work, done: pending.append(done)):
                view.query('definition')
            view.current.insertPlainText('# changed')
            with patch.object(view, 'open_path') as opened:
                pending[0]([(str(path), 1, 0, 'value')])
                opened.assert_not_called()
            view.current.document().setModified(False)
            self.assertTrue(view.prepare_close())
            view.close()
