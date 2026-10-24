"""Qt rename widget previews asynchronously and applies only selected files."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from dataclasses import replace
from threading import Event
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import time
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from desktop.bulk_rename import BulkRenameWidget, open_bulk_rename
from commonUtils.filesystem.rename import RenameRules


class BulkRenameWidgetTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.first = self.root / 'page2.txt';self.first.write_text('two')
        self.second = self.root / 'page10.txt';self.second.write_text('ten')
        self.widget = BulkRenameWidget(self.root)
        self.widget.resize(1280, 900)
        self.widget.show()
        self.addCleanup(self._close)
        self.wait_idle()

    def _close(self):
        self.widget.preview_timer.stop()
        self.widget.progress.request_cancel()
        self.wait_idle()
        self.widget.close()
        self.widget.deleteLater()
        self.app.processEvents()

    def wait_idle(self):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            self.app.processEvents()
            if not self.widget.progress.busy and not self.widget.preview_timer.isActive():
                # Flush queued initial singleShots and finished signals once more.
                self.app.processEvents()
                if not self.widget.progress.busy and not self.widget.preview_timer.isActive():
                    return
            time.sleep(.005)
        self.fail('Rename UI worker did not finish')

    def test_rules_resize_hide_and_reflow_without_resetting(self):
        self.widget.controls.fields['prefix'].setText('keep_')
        self.wait_idle()
        self.widget.resize(680, 550)
        for _ in range(12):
            self.app.processEvents()
        self.assertLessEqual(self.widget.width(), 680)
        self.assertLess(self.widget.controls._columns, 4)
        self.assertGreaterEqual(self.widget.table.header().sectionSize(0), 100)
        self.assertGreaterEqual(self.widget.table.header().sectionSize(1), 100)
        before = self.widget.table.height()
        self.widget.rules_toggle.setChecked(False)
        self.app.processEvents()
        self.assertGreater(self.widget.table.height(), before)
        self.assertEqual(self.widget.controls.fields['prefix'].text(), 'keep_')
        self.widget.rules_toggle.setChecked(True)
        self.app.processEvents()
        self.assertEqual(self.widget.controls.fields['prefix'].text(), 'keep_')

    def test_wide_window_shows_all_rule_groups_without_scrolling(self):
        self.widget.resize(1600, 1000)
        for _ in range(12):
            self.app.processEvents()
        scroll = self.widget.controls.parentWidget().parentWidget()
        self.assertEqual(scroll.verticalScrollBar().maximum(), 0)
        self.assertGreaterEqual(self.widget.controls._columns, 5)
        for section in self.widget.controls._sections:
            self.assertTrue(section.isVisible())
            self.assertLessEqual(section.mapTo(self.widget.controls, qt.QPoint()).y() + section.height(),
                                 scroll.viewport().height())

    def test_footer_groups_secondary_actions_beside_rename_at_narrow_width(self):
        widget = self.widget
        widget.resize(680, 650)
        for _ in range(12):
            self.app.processEvents()
        for button in (widget.preview_button, widget.reset_button, widget.undo_button, widget.rename_button):
            self.assertTrue(widget.action_area.isAncestorOf(button))
            self.assertTrue(button.isVisible())
            rectangle = qt.QRect(button.mapTo(widget.action_area, qt.QPoint()), button.size())
            self.assertTrue(widget.action_area.rect().contains(rectangle))
        self.assertLess(widget.preview_button.y(), widget.reset_button.y())
        self.assertLess(widget.reset_button.y(), widget.undo_button.y())
        self.assertGreater(widget.rename_button.height(), widget.undo_button.height())
        self.assertGreater(widget.rename_button.x(), widget.undo_button.mapTo(widget.action_area, qt.QPoint()).x()
                           + widget.undo_button.width())

    def test_menu_actions_follow_preview_readiness_and_reuse_rule_controls(self):
        from desktop.bulk_rename.menus import build_menus
        host = qt.QMainWindow()
        menus = build_menus(host, self.widget)
        self.addCleanup(host.deleteLater)
        menus['Rename'].aboutToShow.emit()
        rename = menus['Rename'].actions()[-1]
        self.assertFalse(rename.isEnabled())
        self.widget.controls.fields['prefix'].setText('new_')
        self.wait_idle()
        menus['Rename'].aboutToShow.emit()
        self.assertTrue(rename.isEnabled())
        self.assertFalse(menus['Rename'].actions()[2].isEnabled())
        menus['Rename'].actions()[1].trigger()
        self.wait_idle()
        self.assertEqual(self.widget.controls.fields['prefix'].text(), '')
        menus['Rename'].aboutToShow.emit()
        self.assertFalse(rename.isEnabled())

    def wait_folder_visible(self, path):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            self.app.processEvents()
            index = self.widget.folder_model.index(str(path))
            rectangle = self.widget.folder_tree.visualRect(index)
            if (index.isValid() and not rectangle.isEmpty() and self.widget.folder_tree.viewport().rect().intersects(rectangle)
                    and self.widget._folder_reveal_pending is None):
                return index
            time.sleep(.005)
        self.fail(f'Folder did not become visible in tree: {path}; '
                  f'pending={self.widget._folder_reveal_pending}; index_valid={index.isValid()}; '
                  f'row={rectangle.getRect()}; viewport={self.widget.folder_tree.viewport().rect().getRect()}; '
                  f'current={self.widget.folder_model.filePath(self.widget.folder_tree.currentIndex())}')

    def test_preview_bolds_changed_spans_and_prioritizes_filename_columns(self):
        from desktop.bulk_rename.preview import changed_spans, change_formats, preview_tooltip, RenamePreviewDelegate
        self.assertEqual(changed_spans('page2.txt','page3.txt'),((4,5),))
        self.assertEqual(changed_spans('old-page.txt','page.txt'),())
        self.assertEqual(preview_tooltip('old-page.txt','page.txt'),'page.txt\nRemoved: old-')
        self.assertEqual(changed_spans('page.txt','page.txt'),())
        self.assertEqual(changed_spans('page.txt','<b>page.txt'),((0,3),))
        formats = change_formats('😀page2.txt','😀page3.txt')
        self.assertEqual([(span.start,span.length) for span in formats],[(6,1)])
        self.assertEqual(formats[0].format.fontWeight(),qt.QFont.Weight.Bold)
        self.assertIsInstance(self.widget.table.itemDelegateForColumn(1),RenamePreviewDelegate)
        header = self.widget.table.header()
        for column in (0,1):
            self.assertEqual(header.sectionResizeMode(column),qt.QHeaderView.ResizeMode.Stretch)
            self.assertGreater(self.widget.table.columnWidth(column), self.widget.table.columnWidth(2))
        self.widget.controls.set_rules(RenameRules(prefix='New_'))
        self.wait_idle()
        row = self.widget.table.topLevelItem(0)
        self.assertEqual(row.text(1),'New_'+row.text(0))
        self.assertEqual(row.toolTip(1),row.text(1))
        self.assertTrue(self.first.exists())

    def test_root_load_is_observed_even_when_model_finishes_immediately(self):
        original = qt.QFileSystemModel.setRootPath

        def immediate_load(model, path):
            index = original(model, path)
            model.directoryLoaded.emit(path)
            return index

        with patch.object(qt.QFileSystemModel, 'setRootPath', immediate_load):
            widget = BulkRenameWidget(self.root)
        # No event processing: an early root notification must already be saved.
        self.assertIn(Path(widget._tree_anchor), widget._loaded_tree_directories)
        widget.preview_timer.stop()
        widget.close()
        widget.deleteLater()
        self.app.processEvents()

    def test_navigation_keeps_parent_siblings_and_existing_expanded_branches(self):
        parent = self.root / 'Parent'
        child = parent / 'Child'
        sibling = parent / 'Sibling'
        unrelated = self.root / 'Unrelated'
        for path in (child, sibling, unrelated / 'Leaf'):
            path.mkdir(parents=True)
        self.widget.load_directory(self.root)
        self.wait_idle()
        self.wait_folder_visible(self.root)
        original_root = self.widget.folder_tree.rootIndex()
        original_model_root = self.widget.folder_model.rootPath()
        unrelated_index = self.widget.folder_model.index(str(unrelated))
        self.widget.folder_tree.expand(unrelated_index)
        self.widget.load_directory(child)
        self.wait_idle()
        child_index = self.wait_folder_visible(child)
        self.assertEqual(self.widget.folder_tree.rootIndex(), original_root)
        self.assertEqual(self.widget.folder_model.rootPath(), original_model_root)
        self.assertEqual(self.widget.folder_tree.currentIndex(), child_index)
        self.assertEqual(Path(self.widget.folder_model.filePath(child_index.parent())), parent)
        self.assertTrue(self.widget.folder_tree.isExpanded(child_index.parent()))
        sibling_index = self.widget.folder_model.index(str(sibling))
        self.assertTrue(sibling_index.isValid())
        self.assertFalse(self.widget.folder_tree.visualRect(sibling_index).isEmpty())
        self.assertTrue(self.widget.folder_tree.isExpanded(self.widget.folder_model.index(str(unrelated))))
        # Clicking a sibling still opens its file list, without moving the tree root.
        self.widget.folder_tree.clicked.emit(sibling_index)
        self.wait_idle()
        self.wait_folder_visible(sibling)
        self.assertEqual(self.widget.directory, sibling)
        self.assertEqual(self.widget.folder_tree.rootIndex(), original_root)
        self.widget.up_button.click()
        self.wait_idle()
        self.wait_folder_visible(parent)
        self.assertEqual(self.widget.directory, parent)
        self.assertTrue(self.widget.folder_tree.isExpanded(self.widget.folder_model.index(str(unrelated))))

    def test_folder_reveal_retries_before_the_model_creates_its_index(self):
        self.wait_folder_visible(self.root)
        self.widget._folder_reveal_pending = self.root
        self.widget._folder_reveal_timer.stop()
        with patch.object(self.widget.folder_model, 'index', return_value=qt.QModelIndex()):
            self.widget._reveal_current_folder()
        self.assertTrue(self.widget._folder_reveal_timer.isActive())
        self.wait_folder_visible(self.root)
        self.assertIsNone(self.widget._folder_reveal_pending)

    def test_folder_reveal_loads_ancestors_before_requesting_a_missing_child(self):
        self.wait_folder_visible(self.root)
        child = self.root / 'Deferred child'
        child.mkdir()
        model = self.widget.folder_model
        original_index = model.index
        original_can_fetch = model.canFetchMore
        original_fetch = model.fetchMore
        requested = set()

        def index(path, *args):
            if path == str(child) and self.root not in requested:
                return qt.QModelIndex()
            return original_index(path, *args)

        def can_fetch(index):
            path = Path(model.filePath(index))
            return (path == self.root and path not in requested) or original_can_fetch(index)

        def fetch(index):
            requested.add(Path(model.filePath(index)))
            original_fetch(index)

        # QFileSystemModel may have an ancestor index before it has loaded the
        # children. Retrying only the missing leaf never starts that load.
        with patch.object(model, 'index', side_effect=index), \
                patch.object(model, 'canFetchMore', side_effect=can_fetch), \
                patch.object(model, 'fetchMore', side_effect=fetch):
            self.widget._folder_reveal_pending = child
            self.widget._reveal_current_folder()
            self.assertIn(self.root, requested)
            self.wait_folder_visible(child)

    def test_empty_folder_stays_visible_and_async_loads_do_not_reopen_collapsed_branches(self):
        empty = self.root / 'Empty'
        empty.mkdir()
        self.widget.load_directory(empty)
        self.wait_idle()
        index = self.wait_folder_visible(empty)
        self.assertEqual(self.widget.table.topLevelItemCount(), 0)
        self.assertEqual(self.widget.folder_tree.currentIndex(), index)
        self.assertIsNone(self.widget._folder_reveal_pending)
        self.widget.folder_tree.collapse(index.parent())
        self.widget._folder_directory_loaded(str(empty))
        self.widget._folder_directory_loaded(str(self.root))
        self.assertFalse(self.widget.folder_tree.isExpanded(index.parent()))

    def test_late_model_layout_preserves_visible_selection_but_respects_manual_scroll(self):
        from desktop.bulk_rename.widget import _FolderTree
        model = qt.QStandardItemModel()
        parent = qt.QStandardItem('Parent')
        model.appendRow(parent)
        for number in range(80):
            parent.appendRow(qt.QStandardItem(f'Folder {number}'))
        tree = _FolderTree(model)
        self.addCleanup(tree.deleteLater)
        self.addCleanup(tree.close)
        tree.resize(300, 200)
        tree.show()
        parent_index = model.index(0, 0)
        tree.expand(parent_index)
        index = model.index(60, 0, parent_index)
        tree.setCurrentIndex(index)
        tree.scrollTo(index)
        self.app.processEvents()
        def visible():
            rectangle = tree.visualRect(tree.currentIndex())
            return not rectangle.isEmpty() and tree.viewport().rect().intersects(rectangle)
        self.assertTrue(visible())
        # Model sorting can adjust scrolling after the reveal request finishes.
        model.layoutAboutToBeChanged.emit()
        tree.verticalScrollBar().setValue(0)
        model.layoutChanged.emit()
        self.wait_until(visible, message='Late model layout hid the selected folder')
        # A user who already scrolled away should keep their chosen position.
        tree.verticalScrollBar().setValue(0)
        self.assertFalse(tree.viewport().rect().intersects(tree.visualRect(index)))
        model.layoutAboutToBeChanged.emit()
        model.layoutChanged.emit()
        self.app.processEvents()
        self.assertEqual(tree.verticalScrollBar().value(), 0)
        tree.scrollTo(index)
        self.assertTrue(visible())
        model.layoutAboutToBeChanged.emit()
        tree.collapse(parent_index)
        model.layoutChanged.emit()
        self.app.processEvents()
        self.assertFalse(tree.isExpanded(parent_index))

    def test_late_model_layout_keeps_a_deep_folder_horizontally_visible(self):
        from desktop.bulk_rename.widget import _FolderTree
        model = qt.QStandardItemModel()
        parent = model.invisibleRootItem()
        for number in range(13):
            folder = qt.QStandardItem(f'Folder {number}')
            parent.appendRow(folder)
            parent = folder
        index = parent.index()
        tree = _FolderTree(model)
        self.addCleanup(tree.deleteLater)
        self.addCleanup(tree.close)
        tree.setHeaderHidden(True)
        tree.setHorizontalScrollMode(qt.QAbstractItemView.ScrollMode.ScrollPerPixel)
        tree.resize(200, 300)
        tree.show()
        tree.expandAll()
        tree.setColumnWidth(0, 400)
        tree.setCurrentIndex(index)
        self.app.processEvents()
        tree.horizontalScrollBar().setValue(200)
        self.app.processEvents()

        def visible():
            rectangle = tree.visualRect(index)
            return not rectangle.isEmpty() and tree.viewport().rect().intersects(rectangle)

        self.assertTrue(visible())
        # Qt's scrollTo can align the column's left edge, leaving the indented
        # folder entirely to the right of a narrow viewport after layout.
        model.layoutAboutToBeChanged.emit()
        model.layoutChanged.emit()
        self.app.processEvents()
        self.assertTrue(visible(), f'Layout hid the folder: {tree.visualRect(index).getRect()}')

    def test_preview_apply_and_undo_use_background_work_and_preserve_data(self):
        self.assertEqual(len(self.widget.selected_paths()), 2)
        self.widget.controls.fields['prefix'].setText('new_')
        self.assertFalse(self.widget.rename_button.isEnabled())
        self.wait_idle()
        self.assertTrue(self.widget.rename_button.isEnabled())
        self.assertTrue(self.first.exists())
        self.assertFalse((self.root / 'new_page2.txt').exists())
        self.assertTrue(self.widget.apply())
        self.assertFalse(self.widget.controls.isEnabled())
        self.wait_idle()
        self.assertEqual((self.root / 'new_page2.txt').read_text(), 'two')
        self.assertEqual((self.root / 'new_page10.txt').read_text(), 'ten')
        self.assertTrue(self.widget.undo_button.isEnabled())
        self.assertFalse(self.widget.rename_button.isEnabled())
        self.assertTrue(self.widget.undo())
        self.wait_idle()
        self.assertEqual(self.first.read_text(), 'two')
        self.assertEqual(self.second.read_text(), 'ten')
        self.assertFalse(self.widget.undo_button.isEnabled())

    def test_selection_conflicts_and_invalid_regex_block_rename(self):
        self.widget.controls.set_rules(RenameRules(name_mode='fixed', fixed_name='same'))
        self.wait_idle()
        self.assertFalse(self.widget.rename_button.isEnabled())
        self.assertIn('errors', self.widget.status.text())
        self.widget.table.clearSelection()
        self.widget.table.topLevelItem(0).setSelected(True)
        self.wait_idle()
        self.assertTrue(self.widget.rename_button.isEnabled())
        self.assertEqual(len(self.widget.plan.entries), 1)
        self.widget.controls.fields['regex_pattern'].setText('[')
        self.wait_idle()
        self.assertFalse(self.widget.rename_button.isEnabled())
        self.assertIn('unterminated', self.widget.status.text())
        self.assertTrue(self.first.exists())

    def test_superseded_preview_does_not_enable_outdated_rename(self):
        self.widget.controls.fields['prefix'].setText('old_')
        self.widget._preview()
        self.widget.controls.fields['prefix'].setText('latest_')
        self.wait_idle()
        self.assertTrue(all(entry.target.name.startswith('latest_') for entry in self.widget.plan.entries))
        self.assertTrue(self.widget.rename_button.isEnabled())

    def test_selection_and_rule_previews_keep_layout_scroll_and_selection_stable(self):
        from desktop.bulk_rename import widget as module
        for index in range(100):
            (self.root / f'sample{index}.txt').write_text('sample')
        self.widget.resize(1000, 800)
        self.widget.load_directory(self.root)
        self.wait_idle()
        self.widget.table.clearSelection()
        item = self.widget.table.topLevelItem(50)
        self.widget.table.setCurrentItem(item)
        item.setSelected(True)
        self.wait_idle()
        self.widget.table.verticalScrollBar().setValue(200)
        self.widget.table.horizontalScrollBar().setValue(100)
        self.app.processEvents()
        table_rect = self.widget.table.geometry()
        controls_rect = self.widget.controls.parentWidget().parentWidget().geometry()
        button_rect = self.widget.preview_button.geometry()
        selection = self.widget.selected_paths()
        vertical = self.widget.table.verticalScrollBar().value()
        horizontal = self.widget.table.horizontalScrollBar().value()
        entered, release = Event(), Event()
        original = module.plan_renames
        def delayed(*args, **kwargs):
            entered.set()
            release.wait(5)
            return original(*args, **kwargs)
        with patch.object(module, 'plan_renames', side_effect=delayed):
            try:
                self.widget.controls.fields['remove_digits'].setChecked(True)
                self.widget._preview()
                self.assertTrue(entered.wait(2))
                self.app.processEvents()
                self.assertTrue(self.widget.progress.busy)
                self.assertTrue(self.widget.progress.isHidden())
                self.assertEqual(self.widget.table.geometry(), table_rect)
                self.assertEqual(self.widget.controls.parentWidget().parentWidget().geometry(), controls_rect)
                self.assertEqual(self.widget.preview_button.geometry(), button_rect)
                self.assertEqual(self.widget.selected_paths(), selection)
            finally:
                release.set()
                self.wait_idle()
        self.assertEqual(self.widget.table.geometry(), table_rect)
        self.assertEqual(self.widget.controls.parentWidget().parentWidget().geometry(), controls_rect)
        self.assertEqual(self.widget.preview_button.geometry(), button_rect)
        self.assertEqual(self.widget.table.verticalScrollBar().value(), vertical)
        self.assertEqual(self.widget.table.horizontalScrollBar().value(), horizontal)
        self.assertEqual(self.widget.selected_paths(), selection)
        self.assertIs(self.widget.table.currentItem(), item)

    def test_quiet_preview_can_be_cancelled_from_existing_preview_button(self):
        from desktop.bulk_rename import widget as module
        entered, release = Event(), Event()
        original = module.plan_renames
        def delayed(*args, **kwargs):
            entered.set()
            release.wait(5)
            return original(*args, **kwargs)
        with patch.object(module, 'plan_renames', side_effect=delayed):
            try:
                self.widget.request_preview()
                self.widget._preview()
                self.assertTrue(entered.wait(2))
                self.assertEqual(self.widget.preview_button.text(), 'Cancel preview')
                self.assertTrue(self.widget.preview_button.isEnabled())
                self.widget.preview_button.click()
                self.assertTrue(self.widget.progress.cancelled.is_set())
                self.assertTrue(self.widget.progress.busy)
            finally:
                release.set()
                self.wait_idle()
        self.assertEqual(self.widget.preview_button.text(), 'Preview')
        self.assertIn('cancelled', self.widget.status.text())
        self.assertFalse(self.widget.rename_button.isEnabled())

    def test_json_presets_round_trip_and_bad_preset_is_atomic(self):
        preset = self.root / 'rules.json'
        expected = RenameRules(prefix='Photo_', number_mode='suffix', number_padding=3)
        self.widget.controls.set_rules(expected)
        self.wait_idle()
        with patch.object(qt.QFileDialog, 'getSaveFileName', return_value=(str(preset), '')):
            self.assertTrue(self.widget.save_preset())
        self.widget.controls.set_rules(RenameRules())
        self.wait_idle()
        with patch.object(qt.QFileDialog, 'getOpenFileName', return_value=(str(preset), '')):
            self.assertTrue(self.widget.load_preset())
        self.assertEqual(self.widget.controls.rules(), expected)
        self.wait_idle()
        preset.write_text(json.dumps({'prefix': 'wrong_', 'remove_first': 'bad'}))
        with patch.object(qt.QFileDialog, 'getOpenFileName', return_value=(str(preset), '')):
            self.assertFalse(self.widget.load_preset())
        self.assertEqual(self.widget.controls.rules(), expected)

    def test_explicit_paths_limit_initial_scope(self):
        window = open_bulk_rename(paths=[self.first])
        original = self.widget
        self.widget = window.renamer
        self.wait_idle()
        self.assertEqual(self.widget.selected_paths(), (self.first,))
        window.close()
        self.widget = original
        self.app.processEvents()

    def test_closing_busy_widget_requests_cancel_and_waits_for_rollback(self):
        from commonUtils.filesystem import rename as renameUtils
        self.widget.controls.fields['prefix'].setText('new_')
        self.wait_idle()
        entered, release = Event(), Event()
        original = renameUtils._rename_exclusive
        def delayed(source, target):
            if source == self.first:
                entered.set()
                release.wait(3)
            return original(source, target)
        with patch.object(renameUtils, '_rename_exclusive', side_effect=delayed):
            self.widget.apply()
            deadline = time.monotonic() + 3
            while not entered.is_set() and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.005)
            self.assertTrue(entered.is_set())
            self.assertFalse(self.widget.can_close())
            self.assertTrue(self.widget.progress.busy)
            release.set()
            self.wait_idle()
        self.assertTrue(self.widget.can_close())
        self.assertEqual(self.first.read_text(), 'two')
        self.assertEqual(self.second.read_text(), 'ten')
        self.assertFalse(list(self.root.glob('.bulk-rename-*')))

    def test_parent_window_close_waits_for_child_rename_to_cancel(self):
        from commonUtils.filesystem import rename as renameUtils
        host = qt.QMainWindow()
        host.show()
        window = open_bulk_rename(paths=[self.first, self.second], parent=host)
        original_widget = self.widget
        self.widget = window.renamer
        self.wait_idle()
        self.widget.controls.fields['prefix'].setText('new_')
        self.wait_idle()
        entered, release = Event(), Event()
        original = renameUtils._rename_exclusive
        def delayed(source, target):
            if source == self.first:
                entered.set()
                release.wait(3)
            return original(source, target)
        try:
            with patch.object(renameUtils, '_rename_exclusive', side_effect=delayed):
                self.widget.apply()
                deadline = time.monotonic() + 3
                while not entered.is_set() and time.monotonic() < deadline:
                    self.app.processEvents()
                    time.sleep(.005)
                self.assertTrue(entered.is_set())
                self.assertFalse(host.close())
                self.assertTrue(host.isVisible())
                self.assertTrue(self.widget.progress.busy)
                release.set()
                self.widget = original_widget
                deadline = time.monotonic() + 5
                while host.isVisible() and time.monotonic() < deadline:
                    self.app.processEvents()
                    time.sleep(.005)
                self.assertFalse(host.isVisible())
                self.assertEqual(self.first.read_text(), 'two')
                self.assertEqual(self.second.read_text(), 'ten')
        finally:
            release.set()
            self.widget = original_widget
            host.close()
            host.deleteLater()
            self.app.processEvents()

    def test_opt_in_browser_provider_uses_selection_and_refreshes_after_rename(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from desktop.bulk_rename import bulk_rename_actions
        browser = MagicMock()
        context = SimpleNamespace(selection=(SimpleNamespace(path=self.first),), widget=browser, browser=browser)
        actions = bulk_rename_actions(None, context)
        self.assertEqual(actions[0].title, 'Bulk Rename…')
        self.assertEqual(actions[0].category, 'rename')
        with patch('desktop.bulk_rename.open_bulk_rename') as opened:
            actions[0].run(context)
            opened.assert_called_once_with(paths=[self.first], parent=browser.window())
            callback = opened.return_value.renamer.renamed.connect.call_args.args[0]
            callback(None)
            browser.refresh.assert_called_once_with()
        self.assertEqual(bulk_rename_actions(None, SimpleNamespace(selection=())), ())

    def test_stale_source_error_keeps_ui_and_files_available(self):
        self.widget.controls.fields['prefix'].setText('new_')
        self.wait_idle()
        self.first.write_text('edited after preview')
        self.widget.apply()
        self.wait_idle()
        self.assertIn('changed since preview', self.widget.status.text())
        self.assertEqual(self.first.read_text(), 'edited after preview')
        self.assertFalse(self.widget.rename_button.isEnabled())
