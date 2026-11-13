"""Check Find Files results, exact navigation and stale search or preview rejection."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from concurrent.futures import Future
from pathlib import Path
from threading import Event
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.search.files import search_files


class FindFilesTests(QtTestCase):
    def setUp(self):
        super().setUp()
        self.app = qt.QApplication.instance() or qt.QApplication([])
        from features.ide.projects import Project
        from features.ide.ui.workspace import ProjectWorkspace
        self.directory = self.temporary_directory()
        self.root = Path(self.directory.name).resolve()
        self.path = self.root / 'file.py'
        self.path.write_text('old\n')
        self.workspace = ProjectWorkspace(Project('test', str(self.root), autosave='off'))
        self.workspace.resize(1200, 850)
        self.workspace.show()
        self.workspace.activateWindow()
        self.app.processEvents()
        self.workspace.open_path(self.path)
        self.wait_until(lambda: not self.workspace.worker and not self.workspace.queue)

    def test_live_results_preview_and_exact_navigation_from_unsaved_buffer(self):
        self.workspace.current.setPlainText('😀 LiveTag\n')
        excluded = self.root / '.git'
        excluded.mkdir()
        (excluded / 'hidden.py').write_text('LiveTag\n')
        self.workspace.find_project()
        dialog = self.workspace.project_find
        self.assertEqual(dialog.windowType(), qt.Qt.WindowType.Popup)
        dialog.query.setText('LiveTag')
        self.wait_until(lambda: dialog.results.topLevelItemCount() == 1 and dialog.preview_future is None)
        self.assertEqual(dialog.summary.text(), '1 matches in 1 files')
        self.assertEqual(dialog.preview.toPlainText(), '😀 LiveTag\n')
        self.assertEqual(dialog.preview.search_selections[0].cursor.selectedText(), 'LiveTag')
        dialog.open_button.click()
        self.wait_until(lambda: not self.workspace.worker and not self.workspace.queue)
        self.assertEqual(self.workspace.current.textCursor().position(), 3)
        self.assertEqual(self.path.read_text(), 'old\n')
        self.assertFalse(dialog.isVisible())
        self.workspace.find_project()
        dialog.query.setText('missing')
        self.wait_until(lambda: dialog.search_future is None and dialog.summary.text().startswith('0 matches'))
        self.assertFalse(dialog.open_button.isEnabled())
        self.workspace.current.document().setModified(False)

    def test_search_worker_start_failure_is_visible_and_retryable(self):
        from features.ide.ui import find_files
        self.workspace.find_project()
        dialog = self.workspace.project_find
        for error in (OSError('synthetic startup failure'), RuntimeError()):
            with self.subTest(error=type(error).__name__):
                dialog.query.setText('old')
                dialog.changed()
                dialog.debounce.stop()
                with patch.object(find_files._executor, 'submit', side_effect=error):
                    dialog.start_search()
                self.assertIn(str(error) or type(error).__name__, dialog.summary.text())
                self.assertIsNone(dialog.search_future)
                self.assertEqual(dialog.jobs, [])
                self.assertTrue(dialog.search_cancel.is_set())
                dialog.changed()
                dialog.debounce.stop()
                dialog.start_search()
                self.wait_until(lambda: dialog.results.topLevelItemCount() == 1
                                and dialog.preview_future is None)
                self.assertEqual(dialog.preview.toPlainText(), 'old\n')

    def test_preview_worker_start_failure_is_visible_and_retryable(self):
        from features.ide.ui import find_files
        self.workspace.find_project()
        dialog = self.workspace.project_find
        dialog.debounce.stop()
        hit = search_files([self.root], [], 'old').hits[0]
        item = qt.QTreeWidgetItem(['old', 'file.py', '1'])
        item.setData(0, qt.Qt.ItemDataRole.UserRole, hit)
        for error in (OSError('synthetic startup failure'), RuntimeError()):
            with self.subTest(error=type(error).__name__):
                with patch.object(find_files._executor, 'submit', side_effect=error):
                    dialog.selected(item)
                self.assertIn(str(error) or type(error).__name__, dialog.preview_title.text())
                self.assertIsNone(dialog.preview_future)
                self.assertEqual(dialog.jobs, [])
                self.assertTrue(dialog.preview_cancel.is_set())
                dialog.selected(item)
                self.wait_until(lambda: dialog.preview_future is None)
                self.assertEqual(dialog.preview.toPlainText(), 'old\n')

    def test_superseded_preview_cannot_replace_the_selected_file(self):
        from features.ide.ui import find_files
        other = self.root / 'other.py'
        other.write_text('new\n')
        hits = [search_files([self.root], [], query).hits[0] for query in ('old', 'new')]
        stale, latest = Future(), Future()
        def finish_requests():
            for future in (stale, latest):
                if not future.done():
                    future.set_result('')
        self.addCleanup(finish_requests)
        self.workspace.find_project()
        dialog = self.workspace.project_find
        dialog.debounce.stop()
        items = []
        for hit in hits:
            item = qt.QTreeWidgetItem([hit.excerpt, hit.path.name, str(hit.line)])
            item.setData(0, qt.Qt.ItemDataRole.UserRole, hit)
            items.append(item)
        with patch.object(find_files._executor, 'submit', side_effect=[stale, latest]):
            dialog.selected(items[0])
            self.assertTrue(stale.set_running_or_notify_cancel())
            dialog.selected(items[1])
            stale.set_result('obsolete preview\n')
            dialog.completed()
            self.assertEqual(dialog.preview.toPlainText(), '')
            self.assertIn(str(other), dialog.preview_title.text())
            self.assertIs(dialog.preview_future, latest)
            latest.set_result('new\n')
            dialog.completed()
        self.assertEqual(dialog.preview.toPlainText(), 'new\n')
        self.assertEqual(dialog.preview.search_selections[0].cursor.selectedText(), 'new')
        self.assertEqual(dialog.jobs, [])

    def test_superseded_search_cannot_publish_hits_before_latest_search_finishes(self):
        from features.ide.ui import find_files
        from commonUtils.search.files import SearchResult
        stale, latest = Future(), Future()
        def finish_requests():
            for future in (stale, latest):
                if not future.done():
                    future.set_result(SearchResult((), 0, False))
        self.addCleanup(finish_requests)
        hit = search_files([self.root], [], 'old').hits[0]
        self.workspace.find_project()
        dialog = self.workspace.project_find
        with patch.object(find_files._executor, 'submit', side_effect=[stale, latest]) as submit:
            dialog.query.setText('old')
            dialog.debounce.stop()
            dialog.start_search()
            # Keep the old request running so cancellation cannot discard it
            # before the generation check gets exercised.
            self.assertTrue(stale.set_running_or_notify_cancel())
            dialog.query.setText('missing')
            dialog.debounce.stop()
            stale.set_result(SearchResult((hit,), 1, False))
            dialog.completed()
            self.assertFalse(dialog.closing)
            self.assertEqual(dialog.results.topLevelItemCount(), 0)
            self.assertEqual(dialog.summary.text(), 'Searching…')
            self.assertIs(dialog.search_future, latest)
            self.assertEqual(submit.call_args.args[3], 'missing')
            latest.set_result(SearchResult((), 0, False))
            dialog.completed()
        self.assertEqual(dialog.summary.text(), '0 matches in 0 files')
        self.assertEqual(dialog.jobs, [])

    def test_stale_job_is_discarded_and_close_cancels_search(self):
        from commonUtils.search.files import SearchResult
        started, release = Event(), Event()
        hit = search_files([self.root], [], 'old').hits[0]
        def delayed(*args, **kwargs):
            started.set()
            if not release.wait(5):
                raise RuntimeError('Search fixture timed out')
            return SearchResult((hit,), 1, False)
        self.workspace.find_project()
        dialog = self.workspace.project_find
        with patch('features.ide.ui.find_files.search_files', side_effect=delayed):
            try:
                dialog.query.setText('old')
                dialog.debounce.stop(); dialog.start_search()
                self.wait_until(started.is_set)
                dialog.query.setText('new')
                self.assertFalse(dialog.prepare_close())
                self.assertTrue(dialog.search_cancel.is_set())
            finally:
                release.set()
                self.wait_until(lambda: dialog.search_future is None)
        self.assertEqual(dialog.results.topLevelItemCount(), 0)
        self.assertTrue(dialog.prepare_close())
