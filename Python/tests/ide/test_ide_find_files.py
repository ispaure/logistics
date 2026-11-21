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
        self.workspace.current.document().setModified(True)
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

    def test_first_hit_can_be_opened_while_the_worker_is_still_searching(self):
        from commonUtils.search.files import SearchResult

        hit = search_files([self.root], [], 'old').hits[0]
        published, release = Event(), Event()

        def search(*args, on_first_hit, **kwargs):
            on_first_hit(hit)
            published.set()
            if not release.wait(5):
                raise RuntimeError('Search fixture timed out')
            return SearchResult((hit,), 1, False)

        self.workspace.find_project()
        dialog = self.workspace.project_find
        with patch('features.ide.ui.find_files.search_files', side_effect=search):
            try:
                dialog.query.setText('old')
                self.wait_until(lambda: published.is_set() and dialog.open_button.isEnabled())
                self.assertFalse(dialog.search_future.done())
                self.assertEqual(dialog.summary.text(), 'Searching…')
                doc = self.workspace.current
                doc.moveCursor(qt.QTextCursor.MoveOperation.End)
                dialog.open_button.click()
                self.assertFalse(dialog.isVisible())
                self.assertEqual(doc.textCursor().position(), 0)
                self.assertTrue(dialog.search_cancel.is_set())
            finally:
                release.set()
                self.wait_until(lambda: dialog.search_future is None and dialog.preview_future is None)

    def test_project_patterns_prune_files_and_subtrees_in_nested_scopes(self):
        bundle = self.root / 'Example.dSYM' / 'Contents'
        bundle.mkdir(parents=True)
        (bundle / 'inside.py').write_text('old\n')
        (self.root / 'result.xcarchive').write_text('old\n')
        self.workspace.project.excluded_patterns = ['*.xcarchive', '*.dSYM']
        self.workspace.project.source_paths = ['.', 'Example.dSYM/Contents']
        self.workspace.find_project()
        dialog = self.workspace.project_find
        dialog.scope.setCurrentIndex(1)
        dialog.query.setText('old')
        self.wait_until(lambda: dialog.summary.text() == '1 matches in 1 files')
        self.assertEqual(dialog.results.topLevelItem(0).text(1), 'file.py')
        dialog.scope.setCurrentIndex(2)
        dialog.directory.setText(str(bundle))
        self.wait_until(lambda: dialog.summary.text() == '0 matches in 0 files')

    def test_project_worker_borrows_shared_index_without_a_new_scan(self):
        from commonUtils.filesystem.index import DirectoryCache
        from features.ide.search import search_files as project_search
        database = Path(self.temporary_directory().name) / 'index.sqlite3'
        with DirectoryCache(database=database) as cache:
            cache.get(self.root).close()
        with patch('features.ide.search.cache_for', side_effect=lambda: DirectoryCache(database=database)) as factory, \
                patch('os.scandir', side_effect=AssertionError('Warm project was scanned')):
            result = project_search([self.root], [], 'draft', buffers={self.path: 'unsaved draft'})
        factory.assert_called_once_with()
        self.assertEqual([hit.path for hit in result.hits], [self.path])
        self.assertEqual(self.path.read_text(), 'old\n')

    def test_warm_search_reads_external_changes_renames_and_read_only_files(self):
        from commonUtils.filesystem.index import DirectoryCache
        from features.ide.search import search_files as project_search

        source = self.root / 'src'
        source.mkdir()
        original = source / 'original.py'
        original.write_text('original\n')
        database = Path(self.temporary_directory().name) / 'index.sqlite3'
        with DirectoryCache(database=database) as cache:
            cache.get(source).close()
        with patch('features.ide.search.cache_for', side_effect=lambda: DirectoryCache(database=database)):
            def hits(excluded=()):
                result = project_search([source], excluded, 'target', project_root=self.root)
                return [hit.path for hit in result.hits]

            self.assertEqual(hits(), [])
            original.write_text('target\n')
            self.assertEqual(hits(), [original])
            renamed = original.with_name('renamed.py')
            original.rename(renamed)
            renamed.chmod(0o444)
            source.chmod(0o555)
            try:
                self.assertEqual(hits(), [renamed])
                self.assertEqual(hits(['src/renamed.py']), [])
                self.assertEqual(hits(['src']), [])
                self.assertEqual(list(source.iterdir()), [renamed])
            finally:
                source.chmod(0o755)
                renamed.chmod(0o644)

    def test_exact_exclusion_stays_project_relative_in_nested_scopes(self):
        from features.ide.search import search_files as project_search

        source = self.root / 'src'
        excluded = source / 'generated'
        included = source / 'src' / 'generated'
        for directory in (excluded, included):
            directory.mkdir(parents=True)
            (directory / 'example.py').write_text('SearchTag')
        rules = ['src/generated']
        result = project_search([source], rules, 'SearchTag', project_root=self.root)
        self.assertEqual([hit.path for hit in result.hits], [included / 'example.py'])
        result = project_search([excluded], rules, 'SearchTag', project_root=self.root)
        self.assertEqual(result.hits, ())

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
            report_first = submit.call_args.kwargs['on_first_hit']
            dialog.query.setText('missing')
            dialog.debounce.stop()
            report_first(hit)
            dialog.completed()
            self.assertFalse(dialog.open_button.isEnabled())
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
