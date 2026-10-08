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
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from ui_new.bulk_rename import BulkRenameWidget, open_bulk_rename
from commonUtils.renameUtils import RenameRules


class BulkRenameWidgetTests(unittest.TestCase):
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
        self.fail(f'Folder did not become visible in tree: {path}')

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
        self.assertEqual(self.widget.folder_model.filePath(child_index.parent()), str(parent))
        self.assertTrue(self.widget.folder_tree.isExpanded(child_index.parent()))
        sibling_index = self.widget.folder_model.index(str(sibling))
        self.assertTrue(sibling_index.isValid())
        self.assertFalse(self.widget.folder_tree.visualRect(sibling_index).isEmpty())
        self.assertTrue(self.widget.folder_tree.isExpanded(unrelated_index))
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
        self.assertTrue(self.widget.folder_tree.isExpanded(unrelated_index))

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
        from ui_new.bulk_rename import widget as module
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
        from ui_new.bulk_rename import widget as module
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
        from commonUtils import renameUtils
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
        from commonUtils import renameUtils
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
        from ui_new.bulk_rename import bulk_rename_actions
        browser = MagicMock()
        context = SimpleNamespace(selection=(SimpleNamespace(path=self.first),), widget=browser, browser=browser)
        actions = bulk_rename_actions(None, context)
        self.assertEqual(actions[0].title, 'Bulk Rename…')
        self.assertEqual(actions[0].category, 'rename')
        with patch('ui_new.bulk_rename.open_bulk_rename') as opened:
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
