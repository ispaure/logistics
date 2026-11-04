"""Offscreen Qt tests with real repositories and asynchronous UI lifecycle."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from commonUtils.tests.qt_test_case import QtTestCase
from features.git.repository import Repository
from desktop.sidebar import DestinationRail


from tests.version_control.fixtures import GitUIFixture


class GitUILifecycleTests(GitUIFixture, QtTestCase):
    def test_repository_fixture_keeps_mutations_out_of_template(self):
        template = self.repository_template
        config = (template / '.git/config').read_bytes()
        original_status = Repository(template).status()
        self.repo.run(['config', 'user.name', 'Changed in one case'])
        self.commit_fixture()
        self.assertNotEqual((self.repo.path / '.git/config').read_bytes(), config)
        self.assertTrue((self.repo.path / '.git/index').is_file())
        self.assertNotEqual(self.repo.status().oid, original_status.oid)
        self.assertEqual((template / '.git/config').read_bytes(), config)
        self.assertFalse((template / '.git/index').exists())
        self.assertEqual(Repository(template).status(), original_status)
        self.assertFalse((template / 'file.txt').exists())

    def test_hidden_repository_defers_navigation_selection_until_shown(self):
        self.page.hide()
        self.open()
        self.page.views.setCurrentIndex(1)
        self.page.refresh()
        self.wait()
        self.assertIsNone(self.page.refs.currentItem())
        self.page.show()
        self.app.processEvents()
        self.assertIs(self.page.refs.currentItem(), self.page.workspace_items[1])
        self.assertFalse(self.page.refs.visualItemRect(self.page.workspace_items[1]).isEmpty())
        self.page.hide()
        self.page.views.setCurrentIndex(0)
        self.page.refresh()
        self.wait()
        self.page.show()
        self.app.processEvents()
        self.assertIs(self.page.refs.currentItem(), self.page.workspace_items[0])

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
        from desktop import main_window
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

    def test_carriage_return_progress_cannot_grow_log_without_bound(self):
        for _ in range(20): self.page._append_log('x' * 65536)
        self.assertLessEqual(self.page.log.document().characterCount(), 1024 * 1024)
