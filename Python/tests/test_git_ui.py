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
from features.git.ui.repository_view import RepositoryView
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
        self.page = RepositoryView(preferences_path=self.root / 'git.json')
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
        while True:
            self.app.processEvents()
            if not self.page.busy and not self.page.file_timer.isActive() and not self.page._refresh_pending:
                break
            self.assertLess(monotonic(), deadline, 'Git worker did not finish')
            sleep(.005)

    def open(self):
        self.page.open_repository(self.repo.path)
        self.wait()
        self.assertIsNotNone(self.page.snapshot, self.page.status.text())

    def commit_fixture(self):
        (self.repo.path / 'file.txt').write_text('first\n')
        self.repo.stage(['file.txt'])
        self.repo.commit('First')

    def test_commit_badge_and_commit_button_track_staged_files(self):
        from dataclasses import replace
        self.open()
        self.assertEqual(self.page.changes.commit_button.text(), 'Commit')
        self.assertFalse(self.page.changes.commit_button.isEnabled())
        (self.repo.path / 'new.txt').write_text('new')
        self.page.refresh(); self.wait()
        self.assertEqual(self.page.action_buttons['Commit'].property('badge_count'), 1)
        self.assertFalse(self.page.changes.commit_button.isEnabled())
        self.page.changes.stage_all(); self.wait()
        self.assertTrue(self.page.changes.commit_button.isEnabled())
        snapshot = self.page.snapshot
        self.page._render(replace(snapshot, status=replace(snapshot.status, upstream='origin/main', ahead=3, behind=2)))
        self.assertEqual(self.page.action_buttons['Push…'].property('badge_count'), 3)
        self.assertEqual(self.page.action_buttons['Pull…'].property('badge_count'), 2)

    def test_commit_then_push_to_origin_and_push_failure_keeps_commit(self):
        from features.git.runner import GitError
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

    def test_hunk_cards_stage_only_selected_hunk_and_refresh(self):
        lines = [f'Line {i}\n' for i in range(50)]
        (self.repo.path / 'file.txt').write_text(''.join(lines))
        self.repo.stage(['file.txt']); self.repo.commit('Base')
        lines[2] = 'first changed\n'; lines[40] = 'last changed\n'
        (self.repo.path / 'file.txt').write_text(''.join(lines))
        self.open()
        tree = self.page.changes.unstaged_files
        tree.setCurrentItem(tree.topLevelItem(0)); self.wait()
        cards = self.page.preview.cards
        self.assertTrue(cards.isVisible())
        self.assertEqual(len(cards.cards), 2)
        stage = next(button for button in cards.cards[0].findChildren(qt.QToolButton) if button.text() == 'Stage Hunk')
        stage.click(); self.wait()
        self.assertIn('+first changed', self.repo.diff('file.txt', staged=True))
        self.assertNotIn('last changed', self.repo.diff('file.txt', staged=True))
        self.assertEqual(len(cards.cards), 1)
        discard = next(button for button in cards.cards[0].findChildren(qt.QToolButton) if button.text() == 'Discard Hunk…')
        with patch.object(self.page, '_confirm', return_value=True):
            discard.click(); self.wait()
        self.assertIn('first changed', (self.repo.path / 'file.txt').read_text())
        self.assertNotIn('last changed', (self.repo.path / 'file.txt').read_text())

    def test_terminal_opens_at_active_repository_root(self):
        self.open()
        with patch('commonUtils.integrations.wrappers.cmdShellWrapper.terminal.exec_cmd_new_window') as launch:
            self.page.open_terminal()
        import shlex
        command = 'cd' if os.sys.platform == 'win32' else f'cd -- {shlex.quote(str(self.page.path))} && pwd'
        launch.assert_called_once_with(command, str(self.page.path))

    def test_repository_settings_dialog_saves_without_overwriting_draft(self):
        from features.git.ui.settings import RepositorySettingsDialog
        self.open()
        self.page.changes.message.setPlainText('Keep this draft')
        def accept(dialog):
            self.assertEqual([dialog.tabs.tabText(i) for i in range(dialog.tabs.count())],
                             ['Commit Template', 'Remotes', 'Security', 'Advanced'])
            dialog.template_mode.setCurrentIndex(2)
            dialog.template.setPlainText('New template')
            return qt.QDialog.DialogCode.Accepted
        with patch.object(RepositorySettingsDialog, 'exec', accept):
            self.page.settings_dialog(); self.wait()
        self.assertEqual(self.repo.template_text(), 'New template')
        self.assertEqual(self.page.changes.message.toPlainText(), 'Keep this draft')
        self.page.changes.message.clear()
        self.page.refresh(); self.wait()
        self.assertEqual(self.page.changes.message.toPlainText(), 'New template')
        self.assertTrue(self.page.can_close())

    def test_toolbar_icons_have_native_retina_resolution(self):
        from features.git.ui.chrome import action_icon
        for name in ('commit', 'branch', 'merge', 'stash', 'terminal', 'settings'):
            image = action_icon(name).pixmap(qt.QSize(28, 28), 2.0)
            self.assertEqual(image.width(), 56)
            self.assertEqual(image.devicePixelRatio(), 2.0)

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

    def test_workspace_navigation_reparents_preview_and_spans_commit_composer(self):
        self.commit_fixture(); self.open()
        self.assertEqual(self.page.refs.topLevelItem(0).text(0),'WORKSPACE')
        self.assertEqual(self.page.view_title, 'repo (Git)')
        tags = self.page.refs.topLevelItem(2)
        self.assertEqual(tags.text(0), 'TAGS')
        self.assertFalse(tags.isExpanded())
        tags.setExpanded(True)
        self.page.refresh(); self.wait()
        self.assertTrue(self.page.refs.topLevelItem(2).isExpanded())
        self.assertTrue(self.page.views.tabBar().isHidden())
        self.page._navigation_selected(self.page.workspace_items[1],0); self.wait()
        self.assertIs(self.page.preview.parentWidget(),self.page.history_preview_host)
        self.assertIn('First',self.page.history.metadata.toPlainText())
        self.page.action_buttons['Commit'].click(); self.wait()
        self.assertIs(self.page.preview.parentWidget(),self.page.change_preview_host)
        self.assertGreater(self.page.changes.composer.width(),self.page.changes.width())

    def test_uncommitted_history_row_stays_in_history_and_disappears_when_clean(self):
        self.commit_fixture()
        (self.repo.path / 'file.txt').write_text('changed\n')
        self.open(); self.page.views.setCurrentIndex(1); self.wait()
        history = self.page.history
        item = history.table.topLevelItem(0)
        self.assertEqual(item.text(1), 'Uncommitted changes')
        self.assertEqual(item.text(2), '*')
        self.assertEqual(history.selected_commit().subject, 'First')
        row = item.data(0, qt.Qt.ItemDataRole.UserRole)
        self.assertEqual(row.outgoing, ((0, 0),))
        history.table.setCurrentItem(item); self.wait()
        self.assertEqual(self.page.views.currentIndex(), 1)
        self.assertIs(self.page.preview.parentWidget(), self.page.history_preview_host)
        self.assertIsNone(history.selected_commit())
        self.assertEqual(history.tree.topLevelItem(0).text(0), 'file.txt')
        self.assertIn('+changed', self.page.preview.editor.toPlainText())
        self.repo.stage(['file.txt']); self.page.refresh(); self.wait()
        self.assertEqual(history.table.topLevelItem(0).text(1), 'Uncommitted changes')
        self.repo.commit('Second'); self.page.refresh(); self.wait()
        self.assertNotEqual(history.table.topLevelItem(0).text(1), 'Uncommitted changes')
        (self.repo.path / 'file.txt').unlink(); self.page.refresh(); self.wait()
        self.assertEqual(history.table.topLevelItem(0).text(1), 'Uncommitted changes')

    def test_untracked_history_row_in_empty_repository_and_dirty_tag_navigation(self):
        (self.repo.path / 'new.txt').write_text('new\n')
        self.open(); self.page.views.setCurrentIndex(1); self.wait()
        history = self.page.history
        self.assertEqual(history.table.topLevelItemCount(), 1)
        item = history.table.topLevelItem(0)
        self.assertEqual(item.text(1), 'Uncommitted changes')
        self.assertEqual(item.data(0, qt.Qt.ItemDataRole.UserRole).outgoing, ())
        self.assertIsNone(history.selected_commit())
        history.table.setCurrentItem(item); self.wait()
        self.assertEqual(self.page.views.currentIndex(), 1)
        self.assertEqual(history.tree.topLevelItem(0).text(0), 'new.txt')
        self.repo.stage(['new.txt']); self.repo.commit('Initial')
        self.repo.create_tag('v1', 'Release')
        (self.repo.path / 'new.txt').write_text('dirty\n')
        self.page.refresh(); self.wait()
        ref = next(ref for ref in self.page.snapshot.refs if ref.name == 'refs/tags/v1')
        self.page.show_ref_commit(ref); self.wait()
        self.assertEqual(history.selected_commit().subject, 'Initial')
        self.assertIn('Initial', history.metadata.toPlainText())

    def test_annotated_tag_navigation_moves_preview_to_history(self):
        self.commit_fixture()
        self.repo.create_tag('v1','Annotated release')
        self.open()
        group=self.page.refs.topLevelItem(2)
        self.page._navigation_selected(group.child(0),0); self.wait()
        self.assertEqual(self.page.views.currentIndex(),1)
        self.assertIs(self.page.preview.parentWidget(),self.page.history_preview_host)
        self.assertIn('First',self.page.history.metadata.toPlainText())
        self.assertEqual(self.page.history.tree.topLevelItemCount(),1)

    def test_file_checkboxes_stage_and_unstage_exact_path(self):
        self.commit_fixture(); self.open()
        (self.repo.path / 'file.txt').write_text('second\n')
        self.page.refresh(); self.wait()
        item=self.page.changes.unstaged_files.topLevelItem(0)
        from PySide6.QtTest import QTest
        rect=self.page.changes.unstaged_files.visualItemRect(item)
        QTest.mouseClick(self.page.changes.unstaged_files.viewport(),qt.Qt.MouseButton.LeftButton,
                        pos=qt.QPoint(rect.left()+8,rect.center().y()))
        self.wait()
        self.assertEqual(self.page.changes.staged_files.topLevelItemCount(),1)
        self.assertEqual(self.page.changes.unstaged_files.topLevelItemCount(),0)
        item=self.page.changes.staged_files.topLevelItem(0)
        item.setCheckState(0,qt.Qt.CheckState.Unchecked); self.wait()
        self.assertFalse(self.page.snapshot.status.changes[0].staged)

    def test_current_branch_filter_excludes_unmerged_branch_and_search_focus(self):
        self.commit_fixture()
        self.repo.create_branch('feature/other')
        (self.repo.path / 'other.txt').write_text('other')
        self.repo.stage(['other.txt']); self.repo.commit('Other branch')
        self.repo.switch('main'); self.open()
        self.page.history.branch_filter.setCurrentIndex(1)
        self.assertTrue(self.page.history.table.isColumnHidden(0))
        visible=[self.page.history.table.topLevelItem(i).text(1) for i in range(self.page.history.table.topLevelItemCount())
                 if not self.page.history.table.topLevelItem(i).isHidden()]
        self.assertEqual(len(visible),1)
        self.assertIn('First',visible[0])
        self.page._navigation_selected(self.page.workspace_items[2],0); self.wait()
        self.assertTrue(self.page.search_results.search.hasFocus())
        self.assertEqual(self.page.views.currentIndex(), 2)

    def test_search_modes_date_bounds_and_selected_commit_preview(self):
        self.commit_fixture(); self.open()
        self.page._navigation_selected(self.page.workspace_items[2], 0); self.wait()
        panel = self.page.search_results
        self.assertEqual([panel.mode.itemText(i) for i in range(panel.mode.count())],
                         ['Commit Message', 'Commit SHA', 'Branch', 'File Changes', 'User'])
        self.assertEqual(self.page.views.currentIndex(), 2)
        self.assertTrue(panel.table.isColumnHidden(0))
        panel.search.setText('file.txt')
        panel.mode.setCurrentText('File Changes')
        self.page.search_history(); self.wait()
        self.assertEqual(panel.table.topLevelItemCount(), 1)
        self.assertIn('First', panel.metadata.toPlainText())
        self.assertEqual(panel.tree.topLevelItem(0).text(0), 'file.txt')
        self.assertIs(self.page.preview.parentWidget().layout(), self.page.search_preview_layout)
        panel.from_date.setDate(qt.QDate(2099, 1, 1))
        panel.to_date.setDate(qt.QDate(2099, 12, 31))
        self.page.search_history(); self.wait()
        self.assertEqual(panel.table.topLevelItemCount(), 0)

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
        self.assertIn('UI commit', self.page.history.metadata.toPlainText())
        item = self.page.history.tree.topLevelItem(0)
        self.assertIsNotNone(item)
        self.page.history.tree.setCurrentItem(item); self.wait()
        self.assertIn('+first', self.page.preview.editor.toPlainText())
        self.page.history.file_mode.setCurrentIndex(1); self.wait()
        self.page.history.tree.setCurrentItem(self.page.history.tree.topLevelItem(0)); self.wait()
        self.assertEqual(self.page.preview.editor.toPlainText(), 'first\n')

    def test_commit_paths_search_metadata_and_parent_navigation(self):
        self.commit_fixture()
        parent = self.repo.history()[0].oid
        folder = self.repo.path / 'Python' / 'features' / 'git'
        folder.mkdir(parents=True)
        (folder / 'history.py').write_text('history\n')
        (folder / 'preview.py').write_text('preview\n')
        self.repo.stage(['Python'])
        self.repo.commit('Review <widgets>\n\nDetailed message & explanation.')
        self.open()
        self.page.views.setCurrentIndex(1); self.wait()
        history = self.page.history
        self.assertEqual(history.tree.topLevelItemCount(), 2)
        self.assertEqual(history.tree.topLevelItem(0).text(0), 'Python/features/git/history.py')
        self.assertEqual(history.tree.topLevelItem(0).childCount(), 0)
        metadata = history.metadata.toPlainText()
        self.assertTrue(metadata.startswith('Review <widgets>'))
        self.assertIn('Detailed message & explanation.', metadata)
        self.assertIn('UI Test <test@example.invalid>', metadata)
        self.assertNotIn('AuthorDate:', metadata)
        self.assertIn(parent, history.metadata.toHtml())
        selected = history.selected_commit().oid
        history.file_search.setText('PREVIEW')
        self.assertTrue(history.tree.topLevelItem(0).isHidden())
        self.assertFalse(history.tree.topLevelItem(1).isHidden())
        self.assertEqual(history.selected_commit().oid, selected)
        self.assertFalse(self.page.busy)
        history.tree.setCurrentItem(history.tree.topLevelItem(1)); self.wait()
        self.assertIn('+preview', self.page.preview.editor.toPlainText())
        history.file_search.clear()
        history.search.setText('Review')
        history.metadata.anchorClicked.emit(qt.QUrl(parent)); self.wait()
        self.assertEqual(history.selected_commit().oid, parent)
        self.assertEqual(history.search.text(), '')
        self.assertTrue(history.table.currentItem().isSelected())
        self.assertEqual(history.metadata.toPlainText().splitlines()[0], 'First')

    def test_parent_navigation_loads_parent_outside_current_history_page(self):
        self.commit_fixture()
        parent = self.repo.history()[0].oid
        (self.repo.path / 'file.txt').write_text('second\n')
        self.repo.stage(['file.txt']); self.repo.commit('Second')
        self.open(); self.page.views.setCurrentIndex(1); self.wait()
        self.page.history.set_commits(self.page.snapshot.commits[:1], True)
        self.page.history.metadata.anchorClicked.emit(qt.QUrl(parent)); self.wait()
        self.assertEqual(self.page.history.selected_commit().oid, parent)
        self.assertEqual(self.page.history.metadata.toPlainText().splitlines()[0], 'First')

    def test_diff_hunks_have_old_new_numbers_and_plain_files_reset_them(self):
        self.commit_fixture()
        (self.repo.path / 'file.txt').write_text('second\nthird\n')
        self.repo.stage(['file.txt']); self.repo.commit('Second')
        self.open(); self.page.views.setCurrentIndex(1); self.wait()
        editor = self.page.preview.editor
        self.assertIn(('1', '', 'remove'), editor.diff_rows)
        self.assertIn(('', '1', 'add'), editor.diff_rows)
        self.assertIn(('', '2', 'add'), editor.diff_rows)
        self.assertTrue(any(row[2] == 'hunk' for row in editor.diff_rows))
        self.assertTrue(any(s.format.property(qt.QTextFormat.Property.FullWidthSelection)
                            for s in editor.extraSelections()))
        self.page.history.file_mode.setCurrentIndex(1); self.wait()
        self.assertEqual(editor.toPlainText(), 'second\nthird\n')
        self.assertEqual(editor.diff_rows, [])
        from features.git.diff_view import present_diff
        editor.set_diff(present_diff('@@ -8,1 +9,1 @@\n-old\n+new\n@@ -30,1 +31,1 @@\n context'))
        self.assertIn(('8', '', 'remove'), editor.diff_rows)
        self.assertIn(('', '9', 'add'), editor.diff_rows)
        self.assertIn(('30', '31', ''), editor.diff_rows)
        self.page.preview.show_text('Ordinary text', '@@ -8 +9 @@\n-old\n+new')
        self.assertEqual(editor.diff_rows, [])

    def test_clean_staged_diff_raw_toggle_hunk_navigation_and_whitespace_review(self):
        self.commit_fixture()
        lines = [f'line {i}\n' for i in range(40)]
        (self.repo.path / 'file.txt').write_text(''.join(lines))
        self.repo.stage(['file.txt']); self.repo.commit('Lines')
        lines[2] = 'changed 2\n'; lines[30] = 'changed 30\n'
        (self.repo.path / 'file.txt').write_text(''.join(lines))
        self.repo.stage(['file.txt']); self.open()
        tree = self.page.changes.staged_files
        self.assertFalse(tree.topLevelItem(0).icon(0).isNull())
        tree.setCurrentItem(tree.topLevelItem(0)); self.wait()
        preview = self.page.preview
        self.assertEqual(len(preview.diff_view.hunks), 2)
        self.assertIn('Hunk 1', preview.editor.toPlainText())
        self.assertNotIn('diff --git', preview.editor.toPlainText())
        self.assertNotIn('@@', preview.editor.toPlainText())
        preview.next_hunk.click()
        self.assertEqual(preview.editor.textCursor().blockNumber(), preview.diff_view.hunks[1][0])
        preview.previous_hunk.click()
        self.assertEqual(preview.editor.textCursor().blockNumber(), preview.diff_view.hunks[0][0])
        preview.raw.setChecked(True)
        self.assertIn('diff --git', preview.editor.toPlainText())
        preview.raw.setChecked(False)
        preview.wrap.setChecked(True)
        self.assertEqual(preview.editor.lineWrapMode(), qt.QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.repo.commit('Changes')
        (self.repo.path / 'file.txt').write_text(''.join(line.rstrip('\n') + '  \n' for line in lines))
        self.repo.stage(['file.txt']); self.page.refresh(); self.wait()
        tree.setCurrentItem(tree.topLevelItem(0)); self.wait()
        preview.ignore_whitespace.setChecked(True); self.wait()
        self.assertIn('No differences with whitespace ignored.', preview.editor.toPlainText())
        self.assertTrue(self.repo.status().changes[0].staged)
        preview.ignore_whitespace.setChecked(False); self.wait()
        self.assertIn('Hunk 1', preview.editor.toPlainText())

    def test_diff_and_staged_unstaged_selection(self):
        self.commit_fixture(); self.open()
        (self.repo.path / 'file.txt').write_text('second\n')
        self.page.refresh(); self.wait()
        self.page.changes.unstaged_files.setCurrentItem(self.page.changes.unstaged_files.topLevelItem(0)); self.wait()
        self.assertIn('+second', self.page.preview.editor.toPlainText())
        self.page.changes.stage_selected(); self.wait()
        staged = self.page.changes.staged_files.topLevelItem(0)
        self.page.changes.staged_files.setCurrentItem(staged); self.wait()
        self.page.changes.unstage_selected(); self.wait()
        self.assertFalse(self.page.snapshot.status.changes[0].staged)

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
        self.assertEqual(rail.sync_destinations.itemAt(0).widget().text(), 'Sync')
        self.assertEqual(rail.workspace_destinations.itemAt(0).widget().text(), 'Git')
        icon_layout = rail.buttons['tools'].parentWidget().layout()
        self.assertLess(icon_layout.indexOf(rail.workspace_destinations), icon_layout.indexOf(rail.buttons['tools']))
        self.assertLess(icon_layout.indexOf(rail.buttons['hub']), icon_layout.indexOf(rail.buttons['actions']))
        self.assertLess(icon_layout.indexOf(rail.sync_destinations), icon_layout.indexOf(rail.buttons['documents']))
        self.assertLess(icon_layout.indexOf(rail.buttons['documents']), icon_layout.indexOf(rail.workspace_destinations))
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
        self.assertEqual(self.page.preview.title.text(), 'file.txt')
        self.assertIn('First', self.page.history.metadata.toPlainText())
        self.assertIn('+first', self.page.preview.editor.toPlainText())
        self.assertNotIn('+second', self.page.preview.editor.toPlainText())

    def test_edit_remote_reads_and_prefills_current_url(self):
        self.repo.remote_add('origin', '/example/remote.git')
        self.open()
        captured = []
        def submitted(dialog):
            captured.extend(edit.text() for edit in dialog.findChildren(qt.QLineEdit))
            return False
        with patch('features.git.ui.repository_view.FormDialog.submitted', submitted):
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
