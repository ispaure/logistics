"""Offscreen Qt tests with real repositories and asynchronous UI lifecycle."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from commonUtils.ui import pyside as qt
from commonUtils.tests.qt_test_case import QtTestCase


from tests.version_control.fixtures import GitUIFixture


class GitUIHistoryTests(GitUIFixture, QtTestCase):
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
        self.wait_until(lambda: history.tree.topLevelItem(0).isHidden())
        self.assertFalse(history.tree.topLevelItem(1).isHidden())
        self.assertEqual(history.selected_commit().oid, selected)
        self.assertFalse(self.page.busy)
        history.tree.setCurrentItem(history.tree.topLevelItem(1)); self.wait()
        self.assertIn('+preview', self.page.preview.editor.toPlainText())
        history.file_search.clear()
        self.wait_until(lambda: not history.tree.topLevelItem(0).isHidden())
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

    def test_history_search_hides_graph_to_avoid_false_edges(self):
        self.commit_fixture(); self.open()
        self.page.history.search.setText('First')
        self.wait_until(lambda: self.page.history.table.isColumnHidden(0))
        self.page.history.search.clear()
        self.wait_until(lambda: not self.page.history.table.isColumnHidden(0))

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
