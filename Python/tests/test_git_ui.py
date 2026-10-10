"""Offscreen Qt tests with real repositories and asynchronous UI lifecycle."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from unittest.mock import patch
import unittest

from commonUtils.ui import pyside as qt
from commonUtils.tests.qt_test_case import QtTestCase
from features.git.repository import Repository, initialize
from features.git.preferences import Preferences
from features.git.graph import layout_graph
from features.git.models import Commit
from features.git.ui.page import GitPage
from ui_new.sidebar import DestinationRail


@unittest.skipUnless(shutil.which('git'), 'Git executable required')
class GitUITests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = Repository(initialize(self.root / 'repo'))
        self.repo.run(['config', 'user.name', 'UI Test'])
        self.repo.run(['config', 'user.email', 'test@example.invalid'])
        self.repo.run(['config', 'commit.gpgsign', 'false'])
        self.repo.run(['config', 'core.hooksPath', str(self.root / 'no-hooks')])
        self.repo.run(['symbolic-ref', 'HEAD', 'refs/heads/main'])
        self.page = GitPage(preferences_path=self.root / 'git.json')
        self.page.resize(1250, 800)
        self.page.show()
        self.addCleanup(self.release_page)

    def release_page(self):
        self.page.changes.message.clear()
        self.page.prepare_close()
        self.wait()
        self.page.close()
        self.page.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)

    def wait(self, timeout=10):
        deadline = monotonic() + timeout
        while self.page.busy:
            self.assertLess(monotonic(), deadline, 'Git worker did not finish')
            self.app.processEvents()
            sleep(.005)
        self.app.processEvents()

    def open(self):
        self.page.open_repository(self.repo.path)
        self.wait()
        self.assertIsNotNone(self.page.snapshot, self.page.status.text())

    def commit_fixture(self):
        (self.repo.path / 'file.txt').write_text('first\n')
        self.repo.stage(['file.txt'])
        self.repo.commit('First')

    def test_open_empty_repository_and_persist_bookmark(self):
        self.open()
        self.assertTrue(self.page.toolbar.isEnabled())
        self.assertIn('main', self.page.repository_label.text())
        saved = Preferences(self.root / 'git.json')
        self.assertEqual(saved.last_repository, str(self.repo.root()))
        self.assertEqual(len(saved.repositories), 1)

    def test_stage_commit_history_and_blob_preview(self):
        self.open()
        (self.repo.path / 'file.txt').write_text('first\n')
        self.page.refresh(); self.wait()
        self.page.changes.stage_all(); self.wait()
        self.assertTrue(self.page.snapshot.status.changes[0].staged)
        self.page.changes.message.setPlainText('UI commit')
        self.page.changes.commit_button.click(); self.wait()
        self.assertEqual(self.page.changes.message.toPlainText(), '')
        self.assertEqual(self.page.snapshot.commits[0].subject, 'UI commit')
        self.page.views.setCurrentIndex(1); self.wait()
        self.assertIn('UI commit', self.page.preview.editor.toPlainText())
        item = self.page.history.tree.topLevelItem(0)
        self.assertIsNotNone(item)
        self.page.history.tree.setCurrentItem(item); self.wait()
        self.assertEqual(self.page.preview.editor.toPlainText(), 'first\n')

    def test_diff_and_staged_unstaged_selection(self):
        self.commit_fixture(); self.open()
        (self.repo.path / 'file.txt').write_text('second\n')
        self.page.refresh(); self.wait()
        section = self.page.changes.files.topLevelItem(1)
        self.page.changes.files.setCurrentItem(section.child(0)); self.wait()
        self.assertIn('+second', self.page.preview.editor.toPlainText())
        self.page.changes.stage_selected(); self.wait()
        staged = self.page.changes.files.topLevelItem(2).child(0)
        self.page.changes.files.setCurrentItem(staged); self.wait()
        self.page.changes.unstage_selected(); self.wait()
        self.assertFalse(self.page.snapshot.status.changes[0].staged)

    def test_failed_commit_preserves_draft_and_shows_diagnostics(self):
        self.open()
        self.page.changes.message.setPlainText('No staged files')
        self.page.changes.commit_button.click(); self.wait()
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
        self.assertIn('No such file', self.page.status.text())

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
        self.assertEqual(self.page.changes.files.topLevelItem(0).childCount(), 1)
        with patch.object(self.page, '_confirm', return_value=True): self.page.finish_operation(abort=True)
        self.wait()
        self.assertFalse(self.page.snapshot.operation)
        self.assertFalse(self.page.operation_bar.isVisible())

    def test_jobs_are_serialized_and_close_cancels_worker(self):
        self.open()
        started = []
        def slow(runner):
            started.append(True)
            while not runner.cancel.wait(.01): pass
            return 'cancelled'
        self.page._job('Slow operation', slow)
        self.assertFalse(self.page._job('Overlapping job', lambda runner: 'bad'))
        self.assertFalse(self.page.prepare_close())
        self.wait()
        self.assertTrue(self.page.prepare_close())

    def test_history_search_hides_graph_to_avoid_false_edges(self):
        self.commit_fixture(); self.open()
        self.page.history.search.setText('First')
        self.assertTrue(self.page.history.table.isColumnHidden(0))
        self.page.history.search.clear()
        self.assertFalse(self.page.history.table.isColumnHidden(0))

    def test_sidebar_workspace_order_with_optional_sync(self):
        documents = qt.QWidget(); documents.count = 0
        documents.records = {}; documents.show = lambda: None
        rail = DestinationRail(documents)
        tabs = qt.QTabWidget()
        browser, hub, tool, sync = (qt.QWidget() for _ in range(4))
        sync.setProperty('navigation_icon', 'actions')
        sync.setProperty('navigation_position', 'workspace')
        sync.setProperty('navigation_order', 10)
        self.page.setProperty('navigation_icon', 'git')
        for page, name in ((browser, 'Browser'), (hub, 'Hub'), (tool, 'Tool'), (self.page, 'Git'), (sync, 'Sync')):
            tabs.addTab(page, name)
        rail.refresh(tabs, [(0, 'Browser', browser), (5, 'Hub', hub)])
        self.assertEqual([rail.workspace_destinations.itemAt(i).widget().text() for i in range(2)], ['Sync', 'Git'])
        self.assertLess(rail.layout().indexOf(rail.workspace_destinations), rail.layout().indexOf(rail.buttons['tools']))
        tabs.removeTab(tabs.indexOf(sync)); rail.refresh(tabs, [(0, 'Browser', browser), (5, 'Hub', hub)])
        self.assertFalse(rail.buttons[f'feature:{id(sync)}'].isVisible())
        # Return the fixture page to a top-level owner before destroying tabs.
        tabs.removeTab(tabs.indexOf(self.page)); self.page.setParent(None)
        rail.deleteLater(); tabs.deleteLater(); documents.deleteLater()

    def test_main_window_retries_close_when_git_worker_becomes_idle(self):
        from features.contributions import PageContribution, RegisteredContribution
        from ui_new import main_window
        # The page is separately owned by this fixture after the main window dies.
        contribution = RegisteredContribution('git', 'Git', PageContribution(
            'Git', 'git.workspace', lambda parent: self.page, navigation_icon='git'))
        with patch.object(main_window, 'CORE_TABS', ((0, 'Browser', qt.QWidget), (5, 'Hub', qt.QWidget))), \
             patch.object(main_window.registry, 'get_pages', return_value=[contribution]):
            window = main_window.MainWindow()
        window.dlg.show()
        self.page._job('Wait until cancelled', lambda runner: runner.cancel.wait(10))
        window.dlg.close()
        self.assertTrue(window.dlg.isVisible())
        self.wait()
        for _ in range(10): self.app.processEvents()
        self.assertFalse(window.dlg.isVisible())
        window.tabs.removeTab(window.tabs.indexOf(self.page))
        self.page.setParent(None)
        window.dlg.deleteLater()

    def test_subtree_help_exit_129_still_opens_dialog(self):
        self.commit_fixture(); self.open()
        with patch('features.git.ui.repository_tools.FormDialog.submitted', return_value=False) as accepted:
            self.page.repository_tools.subtree_dialog(); self.wait()
            if 'unavailable' in self.page.status.text(): self.skipTest('git subtree not installed')
            accepted.assert_called_once()

    def test_edit_working_file_reuses_text_editor_service(self):
        from unittest.mock import Mock
        self.commit_fixture(); self.open()
        service = Mock()
        with patch('features.registry.is_feature_enabled', return_value=True), \
             patch('features.text_editor.service.editor_service', return_value=service):
            self.page.edit_file('file.txt')
            self.page.edit_file('file.txt')
        self.assertEqual(service.open.call_count, 2)
        service.open.assert_called_with(self.repo.root() / 'file.txt')
        service.saved.connect.assert_called_once()

    def test_refresh_requested_during_read_job_runs_after_it(self):
        from threading import Event
        self.commit_fixture(); self.open()
        release = Event()
        self.page._job('Background read', lambda runner: release.wait(2))
        (self.repo.path / 'file.txt').write_text('external edit\n')
        self.page.refresh()
        self.assertTrue(self.page._refresh_pending)
        release.set(); self.wait()
        self.assertEqual(len(self.page.snapshot.status.changes), 1)
        self.assertFalse(self.page._refresh_pending)

    def test_all_repository_tool_dialogs_use_workspace_as_parent(self):
        self.commit_fixture(); self.open()
        for method in (self.page.repository_tools.worktrees_dialog, self.page.repository_tools.submodules_dialog):
            with patch('features.git.ui.repository_tools.FormDialog.submitted', return_value=False) as submitted:
                method(); self.wait(); submitted.assert_called_once()

    def test_tag_preview_selects_its_commit_instead_of_current_head(self):
        self.commit_fixture()
        first = self.repo.status().oid
        self.repo.create_tag('first', oid=first)
        (self.repo.path / 'file.txt').write_text('second\n')
        self.repo.stage(['file.txt']); self.repo.commit('Second')
        self.open()
        ref = next(r for r in self.page.snapshot.refs if r.name == 'refs/tags/first')
        self.page.show_ref_commit(ref); self.wait()
        self.assertEqual(self.page.history.selected_commit().oid, first)
        self.assertEqual(self.page.preview.title.text(), 'refs/tags/first')
        self.assertIn('First', self.page.preview.editor.toPlainText())

    def test_edit_remote_reads_and_prefills_current_url(self):
        self.repo.remote_add('origin', '/example/remote.git')
        self.open()
        captured = []
        def submitted(dialog):
            captured.extend(edit.text() for edit in dialog.findChildren(qt.QLineEdit))
            return False
        with patch('features.git.ui.page.FormDialog.submitted', submitted):
            self.page.remote_dialog('origin'); self.wait()
        self.assertIn('/example/remote.git', captured)

    def test_carriage_return_progress_cannot_grow_log_without_bound(self):
        for _ in range(20): self.page._append_log('x' * 65536)
        self.assertLessEqual(self.page.log.document().characterCount(), 1024 * 1024)


class GitPreferencesTests(unittest.TestCase):
    def test_roundtrip_pin_and_subtree_mapping(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'git.json'
            prefs = Preferences(path)
            prefs.remember('/repo')
            prefs.repositories[0]['pinned'] = True
            prefs.subtrees['/repo'] = [{'prefix': 'vendor', 'url': '/upstream', 'branch': 'main'}]
            prefs.save()
            copy = Preferences(path)
            self.assertTrue(copy.repositories[0]['pinned'])
            self.assertEqual(copy.subtrees, prefs.subtrees)

    def test_malformed_settings_preserved(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'git.json'; path.write_text('broken')
            prefs = Preferences(path)
            self.assertTrue(prefs.warning)
            with self.assertRaises(OSError): prefs.save()
            self.assertEqual(path.read_text(), 'broken')


class GitGraphTests(unittest.TestCase):
    def commit(self, oid, *parents): return Commit(oid, parents, '', '', '')

    def test_merge_lanes_converge_on_shared_parent(self):
        rows = layout_graph([self.commit('merge', 'a', 'b'), self.commit('a', 'base'),
                             self.commit('b', 'base'), self.commit('base')])
        self.assertEqual(rows[0].outgoing, ((0, 0), (0, 1)))
        self.assertEqual(rows[2].outgoing, ((0, 0), (1, 0)))
        self.assertEqual(rows[-1].outgoing, ())

    def test_disconnected_histories_and_unloaded_parent(self):
        rows = layout_graph([self.commit('a', 'unloaded'), self.commit('other')])
        self.assertEqual(rows[1].lane, 1)
        self.assertEqual(rows[1].outgoing, ((0, 0),))


if __name__ == '__main__': unittest.main()
