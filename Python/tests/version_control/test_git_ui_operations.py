"""Offscreen Qt tests with real repositories and asynchronous UI lifecycle."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from commonUtils.tests.qt_test_case import QtTestCase
from features.git.repository import initialize
from features.git.preferences import Preferences


from tests.version_control.fixtures import GitUIFixture


class GitUIOperationsTests(GitUIFixture, QtTestCase):
    def test_commit_then_push_to_origin_and_push_failure_keeps_commit(self):
        self.open()
        self.repo.remote_add('origin', str(self.root / 'missing-remote.git'))
        (self.repo.path / 'file.txt').write_text('new')
        self.repo.stage(['file.txt']); self.page.refresh(); self.wait()
        checkbox = self.page.changes.push_immediately
        self.assertEqual(checkbox.text(), 'Push changes immediately to origin/main')
        self.assertTrue(checkbox.isEnabled()); checkbox.setChecked(True)
        self.page.changes.message.setPlainText('Saved despite push failure')
        self.page.changes.commit_button.click(); self.wait()
        self.assertEqual(self.repo.history()[0].subject, 'Saved despite push failure')
        self.assertEqual(self.page.changes.message.toPlainText(), '')
        self.assertIn('Push committed changes', self.page.log.toPlainText())
        self.assertTrue(self.page.log_toggle.isChecked())
        bare = self.root / 'origin.git'
        self.repo.runner.run(['init', '--bare', str(bare)])
        self.repo.remote_set_url('origin', str(bare))
        (self.repo.path / 'file.txt').write_text('second')
        self.repo.stage(['file.txt']); self.page.refresh(); self.wait()
        checkbox.setChecked(True)
        self.page.changes.message.setPlainText('Pushed commit')
        self.page.changes.commit_button.click(); self.wait()
        remote = self.repo.runner.run(['--git-dir=' + str(bare), 'rev-parse', 'refs/heads/main']).stdout.strip()
        self.assertEqual(remote.decode('ascii'), self.repo.status().oid)
        self.assertEqual(self.page.snapshot.status.ahead, 0)

    def test_conflict_merge_dialog_saves_and_optionally_stages(self):
        from commonUtils.ui.code_editor.merge import MergeDialog
        from features.git.runner import GitError
        path=self.repo.path/'conflict.txt'
        def commit(text):
            path.write_text(text); self.repo.stage([path.name]); self.repo.commit('Change')
        commit('base\n'); self.repo.create_branch('incoming'); commit('incoming\n')
        self.repo.switch('main'); commit('local\n')
        with self.assertRaises(GitError): self.repo.merge('incoming')
        self.open(); self.page.resolve_conflict(path.name); self.wait()
        dialog=self.page.findChildren(MergeDialog)[0]
        self.assertFalse(dialog.apply_button.isEnabled())
        dialog.widget.choose(0,'both')
        stage=next(box for box in dialog.findChildren(qt.QCheckBox) if box.text().startswith('Stage resolved'))
        stage.setChecked(True); dialog.apply_result(); self.wait()
        self.assertEqual(path.read_text(),'local\nincoming\n')
        self.assertFalse(any(change.conflict for change in self.repo.status().changes))

    def test_browser_remote_addresses_accept_http_and_ssh_only(self):
        from features.git.ui.chrome import browser_remote_url
        self.assertEqual(browser_remote_url('https://github.com/example/repo.git'),'https://github.com/example/repo')
        self.assertEqual(browser_remote_url('git@github.com:example/repo.git'),'https://github.com/example/repo')
        self.assertEqual(browser_remote_url('ssh://git@github.com/example/repo.git'),'https://github.com/example/repo')
        for address in ('/tmp/repo','file:///tmp/repo','ext::command','https://host:bad/repo','https://u:secret@host/repo','C:/repo'):
            self.assertEqual(browser_remote_url(address),'')

    def test_open_empty_repository_and_persist_bookmark(self):
        self.open()
        self.assertTrue(self.page.toolbar.isEnabled())
        self.assertIn('main', self.page.repository_label.text())
        saved = Preferences(self.root / 'git.json')
        self.assertEqual(saved.last_repository, str(self.repo.root()))
        self.assertEqual(len(saved.repositories), 1)

    def test_failed_commit_preserves_draft_and_shows_diagnostics(self):
        self.open()
        self.page.changes.message.setPlainText('No staged files')
        self.assertFalse(self.page.changes.commit_button.isEnabled())
        self.page.commit('No staged files', False); self.wait()
        self.assertEqual(self.page.changes.message.toPlainText(), 'No staged files')
        self.assertFalse(self.page.snapshot.commits)
        self.assertTrue(self.page.log_toggle.isChecked())
        self.assertIn('Commit staged changes', self.page.log.toPlainText())

    def test_invalid_repository_keeps_previous_workspace(self):
        self.commit_fixture(); self.open()
        original = self.page.path
        self.page.open_repository(self.root / 'missing'); self.wait()
        self.assertEqual(self.page.path, original)
        self.assertTrue(self.page.toolbar.isEnabled())
        self.assertIn('invalid' if os.name == 'nt' else 'No such file', self.page.status.text())
        error = self.page.status.text()
        self.page.files_changed(str(self.repo.path))
        self.wait()
        self.assertEqual(self.page.status.text(), error)

    def test_repository_switch_respects_commit_draft(self):
        self.open()
        other = initialize(self.root / 'other')
        self.page.changes.message.setPlainText('Draft')
        with patch.object(self.page, '_confirm', return_value=False): self.page.open_repository(other)
        self.assertEqual(self.page.path, self.repo.root())
        self.assertEqual(self.page.changes.message.toPlainText(), 'Draft')
        with patch.object(self.page, '_confirm', return_value=True): self.page.open_repository(other)
        self.wait()
        self.assertEqual(self.page.path, other.resolve())
        self.assertFalse(self.page.changes.message.toPlainText())

    def test_conflict_state_survives_failed_operation_and_can_abort(self):
        self.commit_fixture()
        self.repo.create_branch('other')
        (self.repo.path / 'file.txt').write_text('other\n')
        self.repo.stage(['file.txt']); self.repo.commit('Other')
        self.repo.switch('main')
        (self.repo.path / 'file.txt').write_text('main\n')
        self.repo.stage(['file.txt']); self.repo.commit('Main')
        self.open()
        self.page._operation('Merge branch', lambda repo: repo.merge('other')); self.wait()
        self.assertEqual(self.page.snapshot.operation, 'merge')
        self.assertTrue(self.page.operation_bar.isVisible())
        self.assertEqual(self.page.changes.unstaged_files.topLevelItemCount(), 1)
        with patch.object(self.page, '_confirm', return_value=True): self.page.finish_operation(abort=True)
        self.wait()
        self.assertFalse(self.page.snapshot.operation)
        self.assertFalse(self.page.operation_bar.isVisible())
