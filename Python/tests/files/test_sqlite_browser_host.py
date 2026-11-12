"""Logistics hosts the shared SQLite editor without bypassing storage or close policy."""
from contextlib import closing
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock, patch

from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from desktop.file_browser import FileBrowserWindow, _sqlite_readonly_paths, _sqlite_write_allowed

TEST_STAGE = TestStage.REGRESSION


class SQLiteHostTests(QtTestCase):
    def setUp(self):
        temporary = self.temporary_directory()
        self.root = Path(temporary.name).resolve()
        self.path = self.root / 'data.db'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE records(id INTEGER PRIMARY KEY, name TEXT)')
            db.executemany('INSERT INTO records VALUES (?,?)', ((1, 'alpha'), (2, 'beta')))
        self.crypt = patch('desktop.file_browser._crypt_location', return_value=(None, False)).start()
        patch('features.application.registry.get_browser_extensions', return_value=[]).start()
        self.addCleanup(patch.stopall)
        self.window = FileBrowserWindow(self.root)
        self.window.show()
        self.wait_until(lambda: self.window.file_browser.model.index(str(self.path)).isValid())

    def editor(self, view=None):
        view = view or self.window.workspace.active_view
        browser = view.file_browser
        menu = browser.context_menu_for(browser.model.index(str(self.path)))
        self.addCleanup(menu.deleteLater)
        next(action for action in menu.actions() if action.text() == 'Inspect SQLite…').trigger()
        editor = browser.sqlite_browser.windows[-1]
        from shiboken6 import isValid
        def cleanup_editor():
            if isValid(editor):
                self.wait_until(lambda: not isValid(editor) or not editor.busy)
                if isValid(editor):
                    editor.discard()
        self.addCleanup(cleanup_editor)
        self.wait_until(lambda: not editor.busy)
        self.assertIsNotNone(editor.page, editor.status.text())
        return editor

    def test_normal_host_action_filter_save_and_reopen(self):
        editor = self.editor()
        self.assertFalse(editor.editing)
        editor.filter_column.setCurrentIndex(editor.filter_column.findData('name'))
        editor.filter_value.setText('beta')
        editor.apply_query()
        self.wait_until(lambda: not editor.busy)
        self.assertEqual([row['id'] for row in editor.page.rows], [2])
        editor.enable_editing()
        self.wait_until(lambda: not editor.busy)
        self.assertTrue(editor.stage_update(0, {'name': 'saved'}))
        editor.save()
        self.wait_until(lambda: not editor.busy)
        self.assertFalse(editor.dirty, editor.status.text())
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT * FROM records ORDER BY id').fetchall(),
                             [(1, 'alpha'), (2, 'saved')])

    def test_dirty_workspace_tab_veto_precedes_feature_shutdown(self):
        dock = self.window.workspace.active_dock
        view = dock.widget()
        self.window.workspace.add_view(self.root)
        editor = self.editor(view)
        editor.enable_editing()
        self.wait_until(lambda: not editor.busy)
        self.assertTrue(editor.stage_update(0, {'name': 'unsaved'}))
        extension = Mock()
        extension.prepare_close.return_value = True
        view.extensions.append(extension)
        self.assertFalse(view.close_in_background)
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
            self.assertFalse(dock.close())
        self.assertIn(dock, self.window.workspace.docks)
        self.assertNotIn(dock, self.window.workspace._retiring)
        self.assertFalse(view.can_retire)
        self.assertFalse(view.closing)
        extension.prepare_close.assert_not_called()
        self.assertTrue(editor.dirty)

    def test_host_private_and_managed_database_policy(self):
        self.crypt.return_value = (None, True)
        with self.assertRaisesRegex(PermissionError, 'private provider'):
            _sqlite_write_allowed(self.path)
        editor = self.editor()
        editor.enable_editing()
        self.wait_until(lambda: not editor.busy)
        self.assertFalse(editor.editing)
        self.crypt.return_value = (None, False)
        with patch('commonUtils.filesystem.index.directory_cache', SimpleNamespace(database=self.path)):
            self.assertEqual(_sqlite_readonly_paths(), (self.path, self.path.with_suffix('.jobs.sqlite3')))
            editor.refresh()
            self.wait_until(lambda: not editor.busy)
            editor.enable_editing()
            self.wait_until(lambda: not editor.busy)
            self.assertFalse(editor.editing)
