"""Folder diagnostics and cleanup report results without blocking the GUI."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
from commonUtils.operations import OperationCancelled
from commonUtils.ui import pyside as qt
from features.file_tools import filesystem
from features.file_tools.ui.dialogs import WeirdCharactersDialog, DeletePycDialog
from features import registry
from ui_new.file_browser import FileBrowserWindow


class _FileToolsFixture(QtTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def file(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture')
        return path


class FileToolsTests(_FileToolsFixture):
    def test_scan_matches_composed_combining_and_parent_paths_without_printing(self):
        composed = self.file('composed-é.txt')
        combining = self.file('combining-e\u0301.txt')
        child = self.file('À/normal.txt')
        self.file('plain.txt')
        with patch('builtins.print') as printed:
            matches = filesystem.scan_weird_characters([self.root, child.parent])
        printed.assert_not_called()
        self.assertEqual({path for path, characters in matches}, {composed, combining, child})
        self.assertEqual(len(matches), 3)
        self.assertEqual(len(filesystem.scan_weird_characters(self.root, recursive=False)), 2)
        with self.assertRaises(OperationCancelled):
            filesystem.scan_weird_characters(self.root, cancelled=lambda: True)

    def test_cleanup_preserves_sources_links_and_outside_folders(self):
        top = self.file('module.PYC')
        child = self.file('nested/module.pyc')
        source = self.file('module.py')
        external = self.file('outside/module.pyc')
        linked = self.root / 'nested/link.pyc'
        linked.symlink_to(external)
        (self.root / 'nested/external').symlink_to(external.parent, target_is_directory=True)
        result = filesystem.cleanup_pyc_files([self.root / 'nested', self.root / 'nested'])
        self.assertEqual(result.completed, [child])
        self.assertTrue(linked.is_symlink())
        self.assertTrue(external.exists())
        self.assertTrue(source.exists())
        self.assertTrue(top.exists())
        self.assertEqual(filesystem.cleanup_pyc_files(self.root, recursive=False).completed, [top])

    def test_cleanup_reports_failure_and_stops_between_files(self):
        first, second, third = [self.file(f'{name}.pyc') for name in ('a', 'b', 'c')]
        original = Path.unlink
        def fail(path, *args, **kwargs):
            if path == second:
                raise PermissionError('locked')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail):
            result = filesystem.cleanup_pyc_files(self.root)
        self.assertEqual(result.completed, [first, third])
        self.assertIn('locked', str(result.failed[second]))
        first = self.file('a.pyc')
        stop = Event()
        result = filesystem.cleanup_pyc_files(self.root, cancelled=stop.is_set,
            report=lambda done, total, message: stop.set() if done else None)
        self.assertEqual(result.completed, [first])
        self.assertEqual(result.remaining, [second])
        self.assertTrue(result.cancelled)
        self.assertTrue(second.exists())


class FileToolsWindowTests(_FileToolsFixture):
    def setUp(self):
        super().setUp()
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def wait(self, dialog):
        deadline = time.monotonic() + 5
        while dialog.busy:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()

    def dialog(self, kind, roots=None):
        dialog = kind(initial_path=roots or self.root)
        dialog.show()
        def close():
            dialog.task.request_cancel()
            self.wait(dialog)
            dialog.close()
            dialog.deleteLater()
            self.app.processEvents()
        self.addCleanup(close)
        return dialog

    def test_scan_window_keeps_results_and_unicode_visible(self):
        path = self.file('é.txt')
        dialog = self.dialog(WeirdCharactersDialog)
        with patch('builtins.print') as printed:
            dialog.action_button.click()
            self.wait(dialog)
        printed.assert_not_called()
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.results.topLevelItemCount(), 1)
        row = dialog.results.topLevelItem(0)
        self.assertEqual(row.text(0), str(path))
        self.assertIn('U+00E9', row.text(2))
        self.assertIn('Found 1', dialog.summary.text())
        self.assertTrue(path.exists())

    def test_cleanup_preview_excludes_new_and_changed_files(self):
        original = self.file('a.pyc')
        candidates = filesystem.scan_pyc_files(self.root)
        new = self.file('new.pyc')
        original.write_bytes(b'changed since preview')
        result = filesystem.cleanup_pyc_files(self.root, candidates=candidates)
        self.assertEqual(result.completed, [])
        self.assertIn(original, result.failed)
        self.assertTrue(original.exists())
        self.assertTrue(new.exists())

    def test_scan_without_pyc_files_finishes_progress_and_can_scan_again(self):
        source = self.file('source.py')
        dialog = self.dialog(DeletePycDialog)
        for _ in range(2):
            dialog.action_button.click()
            self.wait(dialog)
            self.assertEqual(dialog.task.bar.maximum(), 1000)
            self.assertEqual(dialog.task.bar.value(), 1000)
            self.assertIn('No PYC files found', dialog.task.message.text())
            self.assertIn('Scan complete', dialog.summary.text())
            self.assertEqual(dialog.action_button.text(), 'Scan PYC files')
            self.assertIsNone(dialog._pending)
        self.assertTrue(source.exists())

    def test_cleanup_confirmation_and_results_for_multiple_folders(self):
        first, second = self.file('one/a.pyc'), self.file('two/b.pyc')
        dialog = self.dialog(DeletePycDialog, [first.parent, second.parent])
        dialog.action_button.click()
        self.wait(dialog)
        self.assertEqual(dialog.results.topLevelItemCount(), 2)
        self.assertIn('No files deleted', dialog.summary.text())
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.No):
            dialog.action_button.click()
        self.assertFalse(dialog.busy)
        self.assertTrue(first.exists())
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes):
            dialog.action_button.click()
            self.wait(dialog)
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.results.topLevelItemCount(), 2)
        self.assertEqual(dialog.results.topLevelItem(0).text(1), 'Deleted')
        self.assertIn('2 deleted', dialog.summary.text())
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())

    def test_close_during_scan_requests_cancel_and_keeps_worker_alive(self):
        entered, release = Event(), Event()
        dialog = self.dialog(WeirdCharactersDialog)
        def slow(*args, cancelled, **kwargs):
            entered.set()
            release.wait(5)
            if cancelled():
                raise OperationCancelled('Scan cancelled')
            return []
        with patch.object(filesystem, 'scan_weird_characters', side_effect=slow):
            try:
                dialog.action_button.click()
                self.assertTrue(entered.wait(2))
                dialog.close()
                self.assertTrue(dialog.isVisible())
                self.assertTrue(dialog.busy)
                self.assertTrue(dialog.task.cancelled.is_set())
            finally:
                release.set()
                self.wait(dialog)
        self.assertIn('cancelled', dialog.summary.text())
        self.assertTrue(dialog.action_button.isEnabled())

    def test_folder_context_actions_and_feature_toggle_replace_debug_entries(self):
        folder = self.root / 'folder'
        folder.mkdir()
        file = self.file('plain.txt')
        window = FileBrowserWindow(self.root)
        window.show()
        def close():
            window.close()
            self.app.processEvents()
        self.addCleanup(close)
        deadline = time.monotonic() + 5
        while (window.file_browser.busy or not window.file_browser.model.index(str(folder)).isValid()):
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.005)
        def actions(path):
            menu = window.file_browser.context_menu_for(window.file_browser.model.index(str(path)))
            result = [action for action in menu.actions() if action.property('source') == 'File Tools']
            return menu, result
        menu, tools = actions(folder)
        self.assertEqual([action.text() for action in tools], ['List Weird Characters…', 'Bulk Delete PYC…'])
        with patch('features.file_tools.ui.dialogs.WeirdCharactersDialog') as opened:
            tools[0].trigger()
            self.assertEqual(opened.call_args.kwargs['initial_path'], (folder,))
            opened.return_value.exec.assert_called_once()
            opened.return_value.deleteLater.assert_called_once()
        menu.deleteLater()
        menu, tools = actions(file)
        self.assertEqual(tools, [])
        menu.deleteLater()
        self.assertFalse([action for action in registry.get_debug_actions() if action.feature_name == 'file_tools'])
        registry.set_feature_enabled('file_tools', False)
        self.addCleanup(registry.set_feature_enabled, 'file_tools', True)
        menu, tools = actions(folder)
        self.assertEqual(tools, [])
        menu.deleteLater()
