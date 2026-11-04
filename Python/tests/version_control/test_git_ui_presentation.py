"""Offscreen Qt tests with real repositories and asynchronous UI lifecycle."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from commonUtils.tests.qt_test_case import QtTestCase


from tests.version_control.fixtures import GitUIFixture


class GitUIPresentationTests(GitUIFixture, QtTestCase):
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

    def test_toolbar_icons_have_native_retina_resolution(self):
        from features.git.ui.chrome import action_icon
        for name in ('commit', 'branch', 'merge', 'stash', 'terminal', 'settings'):
            image = action_icon(name).pixmap(qt.QSize(28, 28), 2.0)
            self.assertEqual(image.width(), 56)
            self.assertEqual(image.devicePixelRatio(), 2.0)

    def test_git_actions_badges_and_file_status_follow_live_accent(self):
        from commonUtils.ui.appearance.theme import apply_theme
        from commonUtils.ui.appearance.styling import style_values
        self.open()
        button = self.page.action_buttons['Commit']
        button.setProperty('badge_count', 7)
        original = button.defaultAction().icon().cacheKey()
        values = dict(style_values(), accent_color_str='#00cc88')
        with patch('commonUtils.ui.appearance.styling.style_values', return_value=values):
            apply_theme(self.app, mode='dark')
            self.app.processEvents()
        self.assertNotEqual(button.defaultAction().icon().cacheKey(), original)
        self.assertEqual(button.property('badge_count'), 7)
        image = button.defaultAction().icon().pixmap(28, 28).toImage()
        self.assertTrue(any(image.pixelColor(x, y).name() == '#00cc88'
                            and image.pixelColor(x, y).alpha() == 255
                            for x in range(image.width()) for y in range(image.height())))
        item = self.page.workspace_items[0]
        self.page.refs.setCurrentItem(item)
        self.app.processEvents()
        rect = self.page.refs.visualItemRect(item)
        image = self.page.refs.viewport().grab().toImage()
        ratio = image.devicePixelRatio()
        color = image.pixelColor(int((rect.right() - 4) * ratio), int(rect.center().y() * ratio))
        self.assertEqual(color.name(), '#00cc88')

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
