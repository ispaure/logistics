"""Turn Undo preserves later work, staging, pending editors and durable progress."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import subprocess
import unittest
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.ide.projects import Project
from features.ide.ui.workspace import ProjectWorkspace
from features.lm.changes import file_change
from features.lm.undo import reverse_patch
from features.lm.storage import Store
from features.lm.ui.page import LMPage


class ReversePatchTests(unittest.TestCase):
    def test_preserves_later_changes_and_line_shifts_across_multiple_hunks(self):
        before = ''.join(f'line {i}\n' for i in range(40))
        after = before.replace('line 5\n', 'AI five\nextra\n').replace('line 30\n', 'AI thirty\n')
        current = 'later prefix\n' + after.replace('line 17\n', 'later seventeen\n') + 'later suffix\n'
        expected = 'later prefix\n' + before.replace('line 17\n', 'later seventeen\n') + 'later suffix\n'
        self.assertEqual(reverse_patch(current, file_change('main.py', before, after)['patch']), expected)

    def test_conflicts_and_ambiguous_context_and_deletions_without_context(self):
        change = file_change('main.py', 'before\n', 'after\n')
        for text in ('after changed later\n', 'after\nafter\n', '', 'prefix after\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                reverse_patch(text, change['patch'])
        deletion = file_change('main.py', 'deleted\n', '')
        self.assertEqual(reverse_patch('', deletion['patch']), 'deleted\n')
        with self.assertRaises(ValueError):
            reverse_patch('later content\n', deletion['patch'])

    def test_insert_delete_and_missing_final_newline(self):
        for before, after in (('', 'inserted'), ('before', 'after\n'), ('before\n', 'after'),
                              ('a\nb\nc\n', 'a\nc\n'), ('a\n', 'a\nnew\n')):
            with self.subTest(before=before, after=after):
                self.assertEqual(reverse_patch(after, file_change('x', before, after)['patch']), before)

    def test_incomplete_and_malformed_patches_are_rejected(self):
        for patch_text in ('', 'not a patch', '--- a/x\n+++ b/x\n@@ -1,2 +1 @@\n-a\n+b\n',
                           '--- a/x\n+++ b/x\n@@ -1 +1 @@\ninvalid\n'):
            with self.assertRaises(ValueError):
                reverse_patch('b\n', patch_text)


class UndoUITests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = Project('Undo fixture', str(self.root / 'source'), autosave='off')
        self.project.root.mkdir()
        self.page = LMPage(store=Store(self.root / 'chat'))
        self.addCleanup(self.dispose)
        self.page.conversations.new_conversation()
        self.page.context_projects = lambda: {self.project.id: self.project}
        self.entry = self.page.session.begin_response(dict(project_id=self.project.id, project_root=str(self.project.root)))
        self.before = ''.join(f'value_{i} = {i}\n' for i in range(30))
        self.after = self.before.replace('value_5 = 5\n', 'value_5 = 50\n')
        self.paths = [self.project.root / 'one.py', self.project.root / 'two.py']
        for path in self.paths:
            path.write_text(self.after)
        self.page.record_changes([file_change(path.name, self.before, self.after) for path in self.paths])
        self.page.session.complete_response('complete', '', {})
        self.page.persist()
        self.page.render()
        self.page.update_controls()
        self.workspace = None

    def dispose(self):
        if self.workspace is not None:
            self.wait_until(lambda: self.workspace.worker is None)
            for doc in self.workspace.documents.values():
                doc.buffer.autosave.timer.stop()
                doc.document().setModified(False)
            self.workspace.prepare_close()
            self.workspace.deleteLater()
        self.page.prepare_close()
        self.page.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)

    def click_undo(self):
        from PySide6.QtTest import QTest
        self.page.resize(1400, 900)
        self.page.show()
        self.app.processEvents()
        button = self.page.transcript.bubbles[self.entry['id']].changes_card.undo_button
        self.assertTrue(button.isEnabled())
        QTest.mouseClick(button, qt.Qt.MouseButton.LeftButton)
        self.app.processEvents()
        return button

    def test_click_reverts_turn_retains_later_text_and_staged_bytes_and_persists(self):
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.project.root), *args])
        git('init', '-q'); git('add', 'one.py', 'two.py')
        staged = git('show', ':one.py')
        self.paths[0].write_text('later prefix\n' + self.after.replace('value_20 = 20', 'later = 20'))
        button = self.click_undo()
        self.assertEqual(self.paths[0].read_text(), 'later prefix\n' + self.before.replace('value_20 = 20', 'later = 20'))
        self.assertEqual(self.paths[1].read_text(), self.before)
        self.assertEqual(git('show', ':one.py'), staged)
        self.assertEqual(button.text(), 'Undone')
        card = self.page.transcript.bubbles[self.entry['id']].changes_card
        self.assertIn('Undone', card.files.item(0).text())
        self.assertFalse(button.isEnabled())
        key = self.page.data['id']
        self.page.session.release_lease()
        self.page.session.open(key)
        self.page.restore(); self.page.render(); self.page.update_controls()
        self.assertTrue(all(item['undone'] for item in self.page.data['messages'][-1]['changes']))
        button = self.page.transcript.bubbles[self.entry['id']].changes_card.undo_button
        self.assertFalse(button.isEnabled())
        self.assertEqual(self.page.data['messages'][-1]['changes'][0]['patch'], self.entry['changes'][0]['patch'])

    def test_any_conflict_preflights_every_file_before_mutating(self):
        self.paths[1].write_text(self.after.replace('value_5 = 50', 'later = 999'))
        self.click_undo()
        self.assertEqual(self.paths[0].read_text(), self.after)
        self.assertIn('later = 999', self.paths[1].read_text())
        self.assertIn('No files were reverted', self.page.status.text())
        self.assertFalse(any(item.get('undone') for item in self.entry['changes']))

    def test_pending_editor_is_refused_and_successful_undo_refreshes_live_editor(self):
        self.workspace = ProjectWorkspace(self.project)
        self.workspace.open_path(self.paths[0])
        self.wait_until(lambda: self.paths[0] in self.workspace.documents)
        doc = self.workspace.documents[self.paths[0]]
        with patch('features.lm.ui.project_edits.ide_pages', return_value=[SimpleNamespace(views=[self.workspace])]):
            doc.insertPlainText('# pending\n')
            self.click_undo()
            self.assertIn('# pending', doc.toPlainText())
            self.assertEqual(self.paths[0].read_text(), self.after)
            doc.setPlainText(self.after); doc.document().setModified(False)
            self.click_undo()
            self.assertEqual(doc.toPlainText(), self.before)
            self.assertFalse(doc.document().isModified())
            self.assertEqual(doc.snapshot.original, self.paths[0].read_bytes())

    def test_missing_registration_or_changed_root_and_busy_client_block_undo(self):
        self.page.context_projects = lambda: {}
        self.click_undo()
        self.assertEqual(self.paths[0].read_text(), self.after)
        self.assertIn('original IDE project', self.page.status.text())
        self.page.context_projects = lambda: {self.project.id: self.project}
        self.entry['request']['project_root'] = str(self.root / 'different')
        self.click_undo()
        self.assertEqual(self.paths[0].read_text(), self.after)
        self.page.client.active = True
        self.page.update_controls()
        self.assertFalse(self.page.transcript.bubbles[self.entry['id']].changes_card.undo_button.isEnabled())
        self.page.client.active = False

    def test_bom_crlf_and_permissions_are_preserved(self):
        path = self.paths[0]
        path.write_bytes(b'\xef\xbb\xbf' + self.after.replace('\n', '\r\n').encode())
        path.chmod(0o640)
        expected_mode = path.stat().st_mode & 0o777
        self.click_undo()
        self.assertEqual(path.read_bytes(), b'\xef\xbb\xbf' + self.before.replace('\n', '\r\n').encode())
        self.assertEqual(path.stat().st_mode & 0o777, expected_mode)

    def test_symlink_is_refused_before_any_other_file_changes(self):
        self.paths[1].unlink()
        outside = self.root / 'outside.py'
        outside.write_text(self.after)
        self.paths[1].symlink_to(outside)
        self.click_undo()
        self.assertEqual(self.paths[0].read_text(), self.after)
        self.assertEqual(outside.read_text(), self.after)
        self.assertIn('symbolic links', self.page.status.text())

    def test_racing_disk_write_is_not_overwritten_and_progress_is_saved(self):
        from commonUtils.persistence.text import write_text_file
        def race(path, content, **kwargs):
            if path == self.paths[1]:
                path.write_text('later writer\n')
            return write_text_file(path, content, **kwargs)
        with patch('commonUtils.persistence.text.write_text_file', side_effect=race):
            self.click_undo()
        self.assertEqual(self.paths[0].read_text(), self.before)
        self.assertEqual(self.paths[1].read_text(), 'later writer\n')
        saved = self.page.store.load(self.page.data['id'])['messages'][-1]['changes']
        self.assertTrue(saved[0]['undone'])
        self.assertFalse(saved[1].get('undone', False))
        self.assertIn('1 file(s) already reverted', self.page.status.text())

    def test_save_failure_stops_after_first_file_and_retains_retry_progress(self):
        save = self.page.store.save
        calls = 0
        def fail_once(data):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError('disk full')
            return save(data)
        with patch.object(self.page.store, 'save', side_effect=fail_once):
            self.click_undo()
        self.assertEqual(self.paths[0].read_text(), self.before)
        self.assertEqual(self.paths[1].read_text(), self.after)
        self.assertTrue(self.entry['changes'][0]['undone'])
        self.assertIn('1 file(s) already reverted', self.page.status.text())
        self.click_undo()
        self.assertEqual(self.paths[1].read_text(), self.before)
        self.assertTrue(all(item['undone'] for item in self.entry['changes']))
