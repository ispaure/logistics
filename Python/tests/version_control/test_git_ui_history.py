"""Offscreen Qt tests with real repositories and asynchronous UI lifecycle."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from commonUtils.ui import pyside as qt
from commonUtils.tests.qt_test_case import QtTestCase


from tests.version_control.fixtures import GitUIFixture


class GitUIHistoryTests(GitUIFixture, QtTestCase):
    def test_menu_staging_uses_selected_files_and_history_hides_file_actions(self):
        self.open()
        (self.repo.path / 'menu.txt').write_text('menu staging')
        self.page.refresh(); self.wait()
        actions = {a.text(): a for a in self.page.menu_controls.menus['Actions'].actions()}
        self.assertFalse(actions['Stage Selected Files'].isEnabled())
        self.page.changes.unstaged_files.setCurrentItem(self.page.changes.unstaged_files.topLevelItem(0))
        self.wait()
        self.assertTrue(actions['Stage Selected Files'].isEnabled())
        actions['Stage Selected Files'].trigger(); self.wait()
        self.assertTrue(self.repo.status().changes[0].staged)
        self.page.menu_controls.show_view(1); self.wait()
        self.assertFalse(actions['Unstage Selected Files'].isEnabled())

    def test_history_files_are_one_column_without_header_and_refs_use_icons(self):
        from features.git.ui.history import ref_badge
        self.commit_fixture(); self.open()
        self.assertEqual(self.page.history.tree.columnCount(), 1)
        self.assertTrue(self.page.history.tree.isHeaderHidden())
        item = self.page.history.table.topLevelItem(0)
        self.assertEqual(item.data(1, qt.Qt.ItemDataRole.UserRole).oid, self.page.history.head_oid)
        for column in range(self.page.history.table.columnCount()):
            self.assertTrue(item.font(column).bold())
        self.assertEqual(ref_badge('tag: v1.0'), ('tag', 'v1.0'))
        self.assertEqual(ref_badge('HEAD -> main'), ('branch', 'main'))
        self.assertEqual(ref_badge('origin/main'), ('branch', 'origin/main'))

    def test_uncommitted_history_row_stays_in_history_and_disappears_when_clean(self):
        self.commit_fixture()
        (self.repo.path / 'file.txt').write_text('changed\n')
        self.open(); self.page.views.setCurrentIndex(1); self.wait()
        history = self.page.history
        item = history.table.topLevelItem(0)
        self.assertEqual(item.text(1), 'Uncommitted changes')
        self.assertEqual(item.text(2), '*')
        head_item = history.table.topLevelItem(1)
        self.assertEqual(head_item.data(1, qt.Qt.ItemDataRole.UserRole).oid, history.head_oid)
        for column in range(history.table.columnCount()):
            self.assertTrue(head_item.font(column).bold())
        self.assertEqual(history.selected_commit().subject, 'First')
        row = item.data(0, qt.Qt.ItemDataRole.UserRole)
        self.assertEqual(row.outgoing, ((0, 0),))
        history.table.setCurrentItem(item); self.wait()
        # Filesystem notifications can refresh and replace the table while
        # the preview loads. Inspect the current HEAD row after that wait.
        head_item = history.table.topLevelItem(1)
        self.assertEqual(head_item.data(1, qt.Qt.ItemDataRole.UserRole).oid, history.head_oid)
        self.assertTrue(head_item.font(1).bold())
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

    def test_dirty_detached_head_marks_checked_out_commit_instead_of_branch_tip(self):
        self.commit_fixture()
        older = self.repo.status().oid
        (self.repo.path / 'file.txt').write_text('second\n')
        self.repo.stage(['file.txt']); self.repo.commit('Branch tip')
        latest = self.repo.status().oid
        self.repo.run(['checkout', '--detach', older])
        (self.repo.path / 'file.txt').write_text('local changes on older commit\n')
        self.open()
        history = self.page.history
        self.assertEqual(history.head_oid, older)
        self.assertEqual(history.table.topLevelItem(0).text(1), 'Uncommitted changes')
        items = {item.data(1, qt.Qt.ItemDataRole.UserRole).oid: item
                 for i in range(1, history.table.topLevelItemCount())
                 if (item := history.table.topLevelItem(i)).data(1, qt.Qt.ItemDataRole.UserRole)}
        self.assertIn(latest, items)
        history.table.setCurrentItem(items[latest]); self.wait()
        # Native filesystem notifications can rebuild history while the preview
        # loads. Inspect the current rows rather than deleted C++ item wrappers.
        items = {item.data(1, qt.Qt.ItemDataRole.UserRole).oid: item
                 for i in range(1, history.table.topLevelItemCount())
                 if (item := history.table.topLevelItem(i)).data(1, qt.Qt.ItemDataRole.UserRole)}
        for oid, item in items.items():
            for column in range(history.table.columnCount()):
                self.assertEqual(item.font(column).bold(), oid == older)
        self.assertEqual(self.repo.status().oid, older)
        # A detached commit with no branch pointing at it must remain visible too.
        self.repo.stage(['file.txt']); self.repo.commit('Detached commit')
        detached = self.repo.status().oid
        self.page.refresh(); self.wait()
        current = next(history.table.topLevelItem(i) for i in range(history.table.topLevelItemCount())
                       if history.table.topLevelItem(i).data(1, qt.Qt.ItemDataRole.UserRole).oid == detached)
        self.assertTrue(current.font(1).bold())
        self.assertIn('HEAD', current.data(1, qt.Qt.ItemDataRole.UserRole).decorations)

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
