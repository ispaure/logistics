from pathlib import Path
from threading import Event
from unittest.mock import patch
import tempfile
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.ide.ui.project_search import search_files


class SearchFilesTests(unittest.TestCase):
    def test_masks_case_words_regex_exclusions_unicode_and_live_buffers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            py, txt = root / 'code.py', root / 'notes.txt'
            py.write_text('😀 target target_other\nTARGET\n')
            txt.write_text('target\n')
            (root / 'ignored').mkdir()
            (root / 'ignored' / 'skip.py').write_text('target\n')
            result = search_files([root], ['ignored'], 'target', '*.py', whole=True)
            self.assertEqual(len(result.hits), 2)
            self.assertEqual(result.files, 1)
            self.assertEqual((result.hits[0].line, result.hits[0].column, result.hits[0].start), (1, 2, 3))
            self.assertEqual(len(search_files([root], ['ignored'], 'target', '*.py', case=True, whole=True).hits), 1)
            self.assertEqual(len(search_files([root], ['ignored'], r'targ\w+', '*.py', regex=True).hits), 3)
            result = search_files([root], [], 'live', '*.txt', buffers={txt: 'unsaved live\n'})
            self.assertEqual(result.hits[0].path, txt)
            self.assertEqual(result.hits[0].column, 8)
            self.assertEqual(txt.read_text(), 'target\n')
            with self.assertRaises(ValueError):
                search_files([root], [], '(', regex=True)
            self.assertFalse(search_files([root], [], 'target', cancelled=lambda: True).hits)
            self.assertTrue(search_files([root], [], 'target', limit=1).limited)

    def test_excluded_directory_prefix_also_excludes_unsaved_buffers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / 'src' / 'generated' / 'nested' / 'new.py'
            result = search_files([root], ['src/generated'], 'target',
                                  buffers={path: 'target'})
            self.assertFalse(result.hits)


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

    def test_stale_job_is_discarded_and_close_cancels_search(self):
        from features.ide.ui.project_search import SearchResult
        started, release = Event(), Event()
        def delayed(*args, **kwargs):
            started.set()
            if not release.wait(5):
                raise RuntimeError('Search fixture timed out')
            return SearchResult((), 0, False)
        self.workspace.find_project()
        dialog = self.workspace.project_find
        with patch('features.ide.ui.find_files.search_files', side_effect=delayed):
            dialog.query.setText('old')
            dialog.debounce.stop(); dialog.start_search()
            self.wait_until(started.is_set)
            dialog.query.setText('new')
            self.assertFalse(dialog.prepare_close())
            self.assertTrue(dialog.search_cancel.is_set())
            release.set()
            self.wait_until(lambda: dialog.search_future is None)
        self.assertEqual(dialog.results.topLevelItemCount(), 0)
        self.assertTrue(dialog.prepare_close())
