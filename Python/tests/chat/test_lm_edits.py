"""Direct edits preserve disk revisions, live buffers, formatting and Git staging."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import subprocess

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.ide.projects import Project
from features.ide.ui.workspace import ProjectWorkspace
from features.lm.project_tools import ProjectTools
from features.lm.ui.project_edits import ProjectEditDispatcher


class LMEditTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.temp = self.temporary_directory()
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / 'main.py'
        self.path.write_bytes(b'\xef\xbb\xbfvalue = 1\r\nother = 2\r\n')
        self.project = Project('Fixture', str(self.root), autosave='off')
        self.owner = qt.QWidget()
        self.dispatcher = ProjectEditDispatcher(self.owner)
        self.workspace = ProjectWorkspace(self.project)
        self.addCleanup(self.dispose)
        self.pages = patch('features.lm.ui.project_edits.ide_pages',
                           return_value=[SimpleNamespace(views=[self.workspace])])
        self.pages.start()
        self.addCleanup(self.pages.stop)
        self.tools = ProjectTools(self.project, allow_edits=True, edit_dispatch=self.dispatcher.dispatch)

    def dispose(self):
        self.wait_until(lambda: self.workspace.worker is None)
        for doc in self.workspace.documents.values():
            doc.buffer.autosave.timer.stop()
            doc.document().setModified(False)
        self.workspace.prepare_close()
        self.workspace.deleteLater()
        self.owner.deleteLater()
        self.app.processEvents()

    def read(self):
        result = json.loads(self.tools.execute('read_file', json.dumps(dict(path='main.py', start_line=1, end_line=20))))
        self.assertNotIn('error', result)
        return result['version']

    def edit(self, version, **overrides):
        args = dict(path='main.py', version=version, old_text='value = 1', new_text='value = 3')
        args.update(overrides)
        return json.loads(self.tools.execute('edit_file', json.dumps(args)))

    def open_document(self):
        self.workspace.open_path(self.path)
        self.wait_until(lambda: self.path in self.workspace.documents)
        return self.workspace.documents[self.path]

    def test_direct_save_retains_bom_crlf_and_refreshes_editor_with_undo(self):
        doc = self.open_document()
        self.assertTrue(self.edit(self.read())['edited'])
        self.assertEqual(self.path.read_bytes(), b'\xef\xbb\xbfvalue = 3\r\nother = 2\r\n')
        self.assertEqual(doc.toPlainText(), 'value = 3\nother = 2\n')
        self.assertFalse(doc.document().isModified())
        self.assertEqual(doc.snapshot.original, self.path.read_bytes())
        doc.undo()
        self.assertIn('value = 1', doc.toPlainText())
        self.assertTrue(doc.document().isModified())

    def test_rejects_pending_typing_and_autosave_without_touching_either_copy(self):
        doc = self.open_document()
        version = self.read()
        original = self.path.read_bytes()
        doc.insertPlainText('# pending\n')
        draft = doc.toPlainText()
        self.assertIn('error', self.edit(version))
        self.assertEqual(doc.toPlainText(), draft)
        self.assertEqual(self.path.read_bytes(), original)
        doc.setPlainText('value = 1\nother = 2\n')
        doc.document().setModified(False)
        doc.buffer.autosave.busy = True
        self.assertIn('error', self.edit(version))
        doc.buffer.autosave.busy = False

    def test_rejects_stale_disk_and_allows_fresh_read(self):
        version = self.read()
        self.path.write_text('value = 1\nexternal = 4\n')
        self.assertIn('error', self.edit(version))
        self.assertIn('external', self.path.read_text())
        self.assertTrue(self.edit(self.read())['edited'])
        self.assertIn('external = 4', self.path.read_text())

    def test_requires_enable_read_version_unique_match_and_safe_path(self):
        self.assertIn('error', self.edit('unknown'))
        version = self.read()
        for changes in (dict(old_text=''), dict(old_text='missing'), dict(path='../escape'),
                        dict(path='.git/config'), dict(new_text='x' * (256 * 1024 + 1))):
            self.assertIn('error', self.edit(version, **changes))
        self.tools.allow_edits = False
        self.assertIn('error', self.edit(version))
        self.assertNotIn('edit_file', [s['function']['name'] for s in self.tools.specs])
        self.tools.allow_edits = True
        self.path.unlink()
        target = self.root / 'target.py'
        target.write_text('value = 1')
        self.path.symlink_to(target)
        self.assertIn('error', self.edit(version))
        self.assertEqual(target.read_text(), 'value = 1')

    def test_git_staged_and_unstaged_content_is_preserved(self):
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args])
        git('init', '-q')
        git('add', 'main.py')
        staged = git('show', ':main.py')
        self.path.write_text('value = 1\nmy_unstaged = 42\n')
        self.assertTrue(self.edit(self.read())['edited'])
        self.assertEqual(git('show', ':main.py'), staged)
        self.assertEqual(self.path.read_text(), 'value = 3\nmy_unstaged = 42\n')

    def test_worker_dispatch_and_cancellation_are_gui_thread_safe(self):
        version = self.read()
        from commonUtils.ui.tasks.operations import ResultWorker
        worker = ResultWorker(lambda: self.edit(version), self.owner)
        worker.start()
        self.wait_until(lambda: not worker.isRunning())
        self.assertIsNone(worker.error)
        self.assertTrue(worker.result['edited'])
        worker.deleteLater()
        original = self.path.read_bytes()
        result = self.tools.execute('edit_file', json.dumps(dict(path='main.py', version=version,
            old_text='value = 3', new_text='bad')), cancelled=lambda: True)
        self.assertIn('cancelled', result)
        self.assertEqual(self.path.read_bytes(), original)
