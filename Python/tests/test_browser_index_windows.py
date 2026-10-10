"""Real browser tabs, separate workspaces and detached docks share indexing safely."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
from commonUtils.filesystem.index import DirectoryCache
from commonUtils.ui import pyside as qt
from commonUtils.ui.workspace import Workspace
from commonUtils.ui.file_browser.status import WorkspaceIndexStatus
from ui_new.file_browser import BrowserView
from commonUtils.ui.file_browser.index_policy import IndexPolicy


class BrowserWindowIndexTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory(); base = Path(self.temp.name)
        self.root = base / 'files'; self.root.mkdir()
        self.first = self.root / 'view-a'; self.first.mkdir()
        self.second = self.root / 'view-b'; self.second.mkdir()
        (self.first / 'file.txt').write_bytes(b'aaa')
        (self.second / 'file.txt').write_bytes(b'bbbbb')
        self.background = self.root / 'a-background'; self.background.mkdir()
        (self.background / 'file.txt').write_bytes(b'x')
        self.cache = DirectoryCache(database=base / 'cache' / 'index.sqlite3')
        self.addCleanup(self.cache.close)
        self.patches = [patch(name,self.cache) for name in (
            'commonUtils.directory_index.directory_cache',
            'commonUtils.ui.file_browser.index_worker.directory_cache',
            'commonUtils.ui.file_browser.index_search.directory_cache')]
        self.patches.append(patch('ui_new.file_browser.registry.get_browser_extensions', return_value=[]))
        # These cases exercise the optional recursive background mode. The
        # cache-first/visited default has separate policy and navigation tests.
        self.patches.append(patch('commonUtils.ui.file_browser.index_policy.index_policy', return_value=IndexPolicy()))
        for item in self.patches: item.start()
        self.hosts = []; self.workspaces = []; self.views = []; self.releases = []

    def tearDown(self):
        for release in self.releases: release.set()
        for workspace in self.workspaces: workspace.prepare_close()
        from shiboken6 import isValid
        for view in self.views:
            if isValid(view): view.file_browser.shutdown()
        self.app.processEvents()
        for host in self.hosts: host.close(); host.deleteLater()
        self.app.sendPostedEvents(None,qt.QEvent.Type.DeferredDelete)
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def wait(self, condition):
        deadline = monotonic() + 8
        while not condition():
            self.assertLess(monotonic(),deadline)
            self.app.processEvents(); sleep(.005)
        self.app.processEvents()

    def window(self):
        host = qt.QWidget(); layout = qt.QVBoxLayout(host)
        def factory(path):
            view = BrowserView(root_path=path); self.views.append(view); return view
        workspace = Workspace(factory,host); layout.addWidget(workspace)
        workspace.index_status = WorkspaceIndexStatus(workspace)
        host.resize(1100,700); host.show()
        self.hosts.append(host); self.workspaces.append(workspace)
        return workspace

    def test_tabs_windows_and_detached_view_get_priority_and_closing_one_keeps_scan_alive(self):
        entered, release_root, tail, release_tail = Event(), Event(), Event(), Event()
        self.releases.extend((release_root,release_tail))
        original = self.cache._scan_folder
        scanned = []
        def scan(*args,**kwargs):
            result = original(*args,**kwargs); folder = args[4]; scanned.append(folder)
            if folder in (self.root,self.background):
                ready,release = (entered,release_root) if folder == self.root else (tail,release_tail)
                ready.set()
                while not release.wait(.01):
                    if args[5](): break
            return result
        with patch.object(self.cache,'_scan_folder',side_effect=scan):
            first_window = self.window(); root_view = first_window.add_view(self.root)
            self.wait(entered.is_set)
            floating = first_window.add_view(self.first); dock = first_window.active_dock
            first_window.detach_active(); self.app.processEvents()
            second_window = self.window(); other = second_window.add_view(self.second)
            job = root_view.file_browser.folder_operation._job
            self.assertIs(floating.file_browser.folder_operation._job,job)
            self.assertIs(other.file_browser.folder_operation._job,job)
            self.assertTrue(dock.isFloating())
            self.assertFalse(floating.file_browser.index_status.isHidden())
            self.assertTrue(root_view.file_browser.index_status.isHidden())
            self.assertTrue(first_window.index_status.refresh_button.isHidden())
            release_root.set(); self.wait(tail.is_set)
            self.wait(lambda: self.first in floating.file_browser.model.folder_totals and
                      self.second in other.file_browser.model.folder_totals)
            self.assertEqual(floating.file_browser.model.folder_totals[self.first].size,3)
            self.assertEqual(other.file_browser.model.folder_totals[self.second].size,5)
            self.assertLess(scanned.index(self.first),scanned.index(self.background))
            self.assertLess(scanned.index(self.second),scanned.index(self.background))
            owner = floating.file_browser._index_priority_owner
            dock.close(); self.wait(lambda: dock not in first_window.docks)
            self.assertNotIn(owner,self.cache._priority_folders)
            self.assertFalse(job.isInterruptionRequested())
            release_tail.set()
            self.wait(lambda: not root_view.file_browser.folder_busy and not other.file_browser.folder_busy)
        saved = self.cache.peek(self.root)
        self.assertTrue(saved.complete)
        self.assertEqual(saved.folder_stats()[self.root].size,9)
        self.assertFalse(second_window.index_status.refresh_button.isHidden())
        with self.cache._writer(lambda: False) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM roots').fetchone()[0],1)
            self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())

    def test_closing_window_waiting_on_different_root_does_not_interrupt_other_writer(self):
        entered, release = Event(), Event(); self.releases.append(release)
        original = self.cache._scan_folder
        def scan(*args,**kwargs):
            result = original(*args,**kwargs)
            if args[4] == self.root:
                entered.set()
                while not release.wait(.01):
                    if args[5](): break
            return result
        outside = self.root.parent / 'outside'; outside.mkdir(); (outside / 'item').write_bytes(b'xx')
        with patch.object(self.cache,'_scan_folder',side_effect=scan):
            first = self.window(); active = first.add_view(self.root); self.wait(entered.is_set)
            other_window = self.window(); waiting = other_window.add_view(outside)
            job = active.file_browser.folder_operation._job
            self.assertIsNot(waiting.file_browser.folder_operation._job,job)
            self.assertEqual(len(self.cache._priority_folders),2)
            waiting_owner = waiting.file_browser._index_priority_owner
            other_window.active_dock.close(); self.wait(lambda: not other_window.docks)
            self.assertNotIn(waiting_owner,self.cache._priority_folders)
            self.assertFalse(job.isInterruptionRequested())
            release.set(); self.wait(lambda: not active.file_browser.folder_busy)
        self.assertTrue(self.cache.peek(self.root).complete)

    def test_idle_refresh_controls_follow_active_folder_and_detaching(self):
        self.cache.get(self.root)
        workspace = self.window(); first = workspace.add_view(self.first)
        self.wait(lambda: not first.file_browser.folder_busy)
        second = workspace.add_view(self.second)
        self.wait(lambda: not second.file_browser.folder_busy)
        status = workspace.index_status
        self.assertFalse(status.refresh_button.isHidden())
        self.assertTrue(first.file_browser.refresh_button.isHidden())
        dock = workspace.active_dock
        workspace.detach_active(); self.app.processEvents()
        self.assertFalse(second.file_browser.index_status.isHidden())
        self.assertFalse(second.file_browser.refresh_button.isHidden())
        self.assertGreater(second.file_browser.refresh_button.y(),second.file_browser.splitter.y())
        for view in (first,second):
            watcher = view.file_browser.index_watcher
            paths = watcher.directories()+watcher.files()
            if paths: watcher.removePaths(paths)
        added_first = self.first / 'new.txt'; added_first.write_bytes(b'zz')
        added_second = self.second / 'new.txt'; added_second.write_bytes(b'xxxx')
        entered, release = Event(), Event(); self.releases.append(release)
        original = self.cache.reconcile_folder; requests = []
        def reconcile(path,**kwargs):
            requests.append((path,kwargs['full'])); entered.set()
            while not release.wait(.01):
                if kwargs['cancelled'](): return None
            return original(path,**kwargs)
        with patch.object(self.cache,'reconcile_folder',side_effect=reconcile):
            status.refresh_button.click(); self.wait(entered.is_set)
            self.assertTrue(status.refresh_button.isHidden())
            self.assertTrue(second.file_browser.refresh_button.isHidden())
            release.set(); self.wait(lambda: not second.file_browser.folder_busy)
        self.assertEqual(requests,[(self.second,True)])
        self.assertIsNone(self.cache.peek(self.root).entry(added_first))
        self.assertIsNotNone(self.cache.peek(self.root).entry(added_second))
        self.assertEqual(self.cache.peek(self.root).folder_stats()[self.root].size,13)
        self.assertFalse(second.file_browser.refresh_button.isHidden())
        workspace.reattach_active(); self.app.processEvents()
        self.assertFalse(dock.isFloating())
        self.assertTrue(second.file_browser.index_status.isHidden())
        self.assertTrue(second.file_browser.refresh_button.isHidden())
        self.assertFalse(status.refresh_button.isHidden())

    def test_first_open_shallow_scan_displays_independently_cached_sizes(self):
        self.cache.get(self.first)
        self.cache.get(self.second)
        scanned = []
        original = self.cache._scan_folder
        def scan(*args, **kwargs):
            scanned.append(args[4])
            return original(*args, **kwargs)
        policy = IndexPolicy(recursive_on_open=False, refresh_cached_on_startup=True, watch_changes=False)
        with patch('commonUtils.ui.file_browser.index_policy.index_policy', return_value=policy), \
             patch.object(self.cache, '_scan_folder', side_effect=scan):
            workspace = self.window(); view = workspace.add_view(self.root)
            browser = view.file_browser
            self.wait(lambda: not browser.folder_busy)
            self.assertEqual(browser.model.folder_totals[self.first].size, 3)
            self.assertEqual(browser.model.folder_totals[self.second].size, 5)
            self.assertEqual(browser.model.data(browser.model.index(str(self.first), 1)), '3 B')
            self.assertEqual(scanned, [self.root])
