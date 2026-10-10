"""Repository tabs retain their controls, draft, worker and state while docking."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.git.ui.page import GitPage
from features.git.repository import initialize


class GitRepositoryTabsTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.first_path = initialize(self.root / 'first').resolve()
        self.second_path = initialize(self.root / 'second').resolve()
        self.page = GitPage(preferences_path=self.root / 'git.json')
        self.page.resize(1250, 800); self.page.show()
        self.addCleanup(self.cleanup_page)

    def cleanup_page(self):
        for dock in self.page.workspace.docks:
            dock.widget().changes.message.clear()
        self.page.prepare_close(); self.wait()
        self.page.close(); self.page.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)

    def wait(self, timeout=10):
        deadline = monotonic() + timeout
        while any(dock.widget().busy for dock in self.page.workspace.docks):
            self.assertLess(monotonic(), deadline)
            self.app.processEvents(); sleep(.005)
        for _ in range(5): self.app.processEvents()

    def test_repository_panes_keep_drafts_controls_and_reordered_identity(self):
        first = self.page.open_repository(self.first_path); self.wait()
        first.changes.message.setPlainText('first draft')
        second = self.page.open_repository(self.second_path); self.wait()
        second.changes.message.setPlainText('second draft')
        self.assertEqual(len(self.page.workspace.docks), 2)
        self.assertIs(self.page.open_repository(self.first_path), first)
        second._repositories()
        next(action for action in second.bookmark_menu.actions()
             if action.text() == str(self.first_path)).trigger()
        self.assertEqual(second.path, self.second_path)
        self.assertEqual(len(self.page.workspace.docks), 2)
        self.assertEqual(first.changes.message.toPlainText(), 'first draft')
        dock = next(d for d in self.page.workspace.docks if d.widget() is first)
        dock.setFloating(True); self.wait()
        self.assertIs(dock.widget(), first)
        for title in ('Commit', 'Pull…', 'Push…', 'Fetch', 'Branch…', 'View Remote', 'Terminal'):
            self.assertTrue(first.isAncestorOf(first.action_buttons[title]))
        self.assertTrue(first.isAncestorOf(first.action_buttons[
            'Show in Finder' if os.sys.platform == 'darwin' else 'Open Folder']))
        with patch.object(first, '_operation') as first_action, patch.object(second, '_operation') as second_action:
            first.action_buttons['Fetch'].click()
            first_action.assert_called_once(); second_action.assert_not_called()
        self.page.workspace.adopt(dock); self.wait()
        bar = next(bar for bar in self.page.workspace.findChildren(qt.QTabBar)
                   if bar.parent() is self.page.workspace and bar.count() == 2)
        original = [self.page.workspace._tab_dock(bar, i) for i in range(2)]
        self.assertEqual(self.page.workspace.docks, original)
        bar.moveTab(0, 1); self.wait()
        self.assertEqual(self.page.workspace.docks, [original[1], original[0]])
        second_dock = next(d for d in self.page.workspace.docks if d.widget() is second)
        with patch.object(second, '_confirm', return_value=False):
            self.assertFalse(second_dock.close())
        self.assertEqual(second.changes.message.toPlainText(), 'second draft')
        self.assertEqual(first.changes.message.toPlainText(), 'first draft')

    def test_new_tab_shows_repository_menu_without_toolbar_dropdown(self):
        self.wait()
        view = self.page.workspace.active_view
        self.page.workspace.request_new_view()
        self.assertTrue(view.repository_menu.isVisible())
        view.repository_menu.close()
        self.assertEqual([action.text() for action in view.repository_menu.actions()],
                         ['Open…', 'Clone…', 'Init…', 'Manage bookmarks…', 'Bookmarks', '', 'Git preferences…'])
        self.assertFalse(any(button.text() == '+ Repositories' for button in view.toolbar.findChildren(qt.QToolButton)))

    def test_narrow_floating_pane_keeps_actions_in_toolbar_overflow(self):
        view = self.page.open_repository(self.first_path); self.wait()
        dock = self.page.workspace.active_dock
        dock.setFloating(True); dock.resize(640, 600); self.wait()
        # Native font metrics can make the pane's content minimum wider than
        # 640px. Constrain the toolbar itself to exercise its overflow on every OS.
        view.toolbar.setMaximumWidth(min(640, view.toolbar.sizeHint().width() - 40))
        self.wait()
        self.assertLess(view.toolbar.width(), view.toolbar.sizeHint().width())
        extension = view.toolbar.findChild(qt.QToolButton, 'qt_toolbar_ext_button')
        self.assertIsNotNone(extension)
        self.assertTrue(extension.isVisible())
        for title, button in view.action_buttons.items():
            action = button.defaultAction()
            self.assertIsNotNone(action, title)
            self.assertIn(action, view.toolbar.actions())
        view._set_busy(True)
        self.assertTrue(all(not button.defaultAction().isEnabled() for button in view.action_buttons.values()))
        view._set_busy(False)

    def test_background_repository_does_not_block_another_tab_and_close_waits(self):
        first = self.page.open_repository(self.first_path); self.wait()
        started, release = Event(), Event()
        self.addCleanup(release.set)
        def work(runner):
            started.set(); release.wait(5)
        first._job('Held operation', work)
        self.assertTrue(started.wait(2))
        second = self.page.open_repository(self.second_path)
        deadline = monotonic() + 5
        while second.busy:
            self.assertLess(monotonic(), deadline)
            self.app.processEvents(); sleep(.005)
        self.assertIsNotNone(second.snapshot)
        self.assertTrue(first.busy)
        dock = next(d for d in self.page.workspace.docks if d.widget() is first)
        self.assertFalse(dock.close())
        self.assertIn(dock, self.page.workspace.docks)
        self.assertTrue(first.worker.cancel_event.is_set())
        release.set(); self.wait()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.assertEqual([d.widget() for d in self.page.workspace.docks], [second])
