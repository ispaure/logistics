"""Real desktop Notes Library documents: lazy providers, navigation and revocation."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.ui.notes_library import NotesLibraryWindow
from features.text_editor.notes_actions import actions
from models.folder_entry import FolderEntry
from models.local_folder import LocalFolder


class RemoteFiles(LocalFiles):
    private = remote_storage = True
    def __init__(self, root):
        super().__init__(root);self.calls=[];self.closed=False
    def list(self, path='', **kw):
        self.calls.append(path);return super().list(path, **kw)
    def _check_active(self):
        if self.closed:raise ValueError('Credentials revoked')
    def acquire(self):return self.close
    def close(self):self.closed=True


class PrivateFiles(RemoteFiles):
    remote_storage = False


class NotesLibraryDesktopTests(QtTestCase):
    def test_miscellaneous_files_are_visible_and_use_the_document_router(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            for name in ('clip.mp4', 'archive.bin', 'LICENSE', '.secret'):
                (root / name).write_bytes(b'content')
            window = self.open_library(root)
            self.assertTrue({'clip.mp4', 'archive.bin', 'LICENSE'} <= window.items.keys())
            self.assertNotIn('.secret', window.items)
            with patch('desktop.document_catalog.open_resource') as opened:
                window.open_note('clip.mp4')
                opened.assert_called_once_with(window.provider, 'clip.mp4', window)
            window.close()

    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def open_library(self, root):
        (root / '.obsidian').mkdir(exist_ok=True)
        window = NotesLibraryWindow(lambda: LocalFiles(root), 'Parity')
        window.show()
        self.wait_until(lambda: not window.progress.busy)
        self.addCleanup(lambda: window.close() if __import__('shiboken6').isValid(window) else None)
        return window

    def test_favourite_keeps_library_root_and_reopens_the_note(self):
        from desktop.document_catalog import reference, reopen
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Home.md').write_text('# Home')
            window = self.open_library(root)
            window.open_note('Home.md')
            self.wait_until(lambda: not window.progress.busy)
            source, title, opener, cipher = reference(window)
            self.assertIsNone(cipher)
            self.assertEqual(opener, dict(editor='notes', root=str(root.resolve())))
            with patch.object(qt.QMessageBox, 'warning', side_effect=AssertionError('Favourite could not reopen')):
                restored = reopen(dict(source=source, title=title, opener=opener))
            self.addCleanup(lambda: restored.close() if __import__('shiboken6').isValid(restored) else None)
            self.wait_until(lambda: not restored.progress.busy and restored.index >= 0)
            self.assertEqual(restored.history[restored.index], 'Home.md')
            restored.close()
            window.close()

    def test_search_activation_opens_nested_document_from_its_provider_path(self):
        from PySide6.QtTest import QTest
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Nested').mkdir()
            (root / 'Nested/Target.md').write_text('# Target note')
            window = self.open_library(root)
            window.search.setText('Target')
            window.filter()
            self.wait_until(lambda: not window.aux.busy and bool(window.search_rows))
            item = window.search_results.topLevelItem(0)
            self.assertEqual(item.text(0), 'Target.md')
            window.search_results.setCurrentItem(item)
            window.search_results.setFocus()
            QTest.keyClick(window.search_results, qt.Qt.Key.Key_Return)
            self.wait_until(lambda: not window.progress.busy and window.index >= 0)
            self.assertEqual(window.history[window.index], 'Nested/Target.md')
            self.assertIn('Target note', window.viewer.browser.toPlainText())
            window.close()

    def test_tree_drop_moves_nested_file_to_visible_library_root(self):
        from types import SimpleNamespace
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Nested').mkdir()
            (root / 'Nested/Move.md').write_text('# Preserve me')
            window = self.open_library(root)
            window.items['Nested'].setExpanded(True)
            self.wait_until(lambda: not window.progress.busy)
            window.tree.setCurrentItem(window.items['Nested/Move.md'])
            root_item = window.items[window.library.root]
            self.assertEqual(root_item.text(0), 'Library root')
            event = SimpleNamespace(ignore=lambda: None, source=lambda: window.tree,
                position=lambda: qt.QPointF(window.tree.visualItemRect(root_item).center()))
            window.tree.dropEvent(event)
            self.wait_until(lambda: not window.progress.busy)
            self.assertEqual((root / 'Move.md').read_text(), '# Preserve me')
            self.assertFalse((root / 'Nested/Move.md').exists())
            window.close()

    def test_save_before_navigation_continues_once_and_failure_keeps_current_note(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Home.md').write_text('# Home')
            (root / 'Other.md').write_text('# Other')
            window = self.open_library(root)
            window.open_note('Home.md')
            self.wait_until(lambda: not window.progress.busy)
            window.viewer.set_editing(True)
            window.viewer.set_edit_mode('source')
            window.viewer.editor.insertPlainText('Saved draft ')
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Save) as prompt:
                window.open_note('Other.md')
                self.wait_until(lambda: not window.progress.busy)
                self.assertEqual(prompt.call_count, 1)
            self.assertEqual(window.history, ['Home.md', 'Other.md'])
            self.assertIn('Saved draft', (root / 'Home.md').read_text())
            window.viewer.editor.insertPlainText('Unpublished ')
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Save), \
                    patch('services.documents.storage.DocumentResource.save', side_effect=OSError('Disk full')):
                window.open_note('Home.md')
                self.wait_until(lambda: not window.progress.busy)
            self.assertEqual(window.history[window.index], 'Other.md')
            self.assertTrue(window.viewer.is_modified)
            self.assertIsNone(window._after_document_save)
            window.viewer.save_document()
            self.wait_until(lambda: not window.progress.busy)
            self.assertEqual(window.history[window.index], 'Other.md')
            window.close()

    def test_save_before_move_continues_for_markdown_and_drawing(self):
        from features.notebooks.notebook import Notebook
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Home.md').write_text('# Home')
            (root / 'Drawing.rmdoc').write_bytes(Notebook.new('Drawing').to_bytes())
            window = self.open_library(root)
            window.open_note('Home.md')
            self.wait_until(lambda: not window.progress.busy)
            window.viewer.set_editing(True)
            window.viewer.set_edit_mode('source')
            window.viewer.editor.insertPlainText('Preserved ')
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Save) as prompt:
                window.move_entry('Home.md', 'Moved.md')
                self.wait_until(lambda: not window.progress.busy)
                self.assertEqual(prompt.call_count, 1)
            self.assertFalse((root / 'Home.md').exists())
            self.assertIn('Preserved', (root / 'Moved.md').read_text())
            window.open_note('Drawing.rmdoc')
            self.wait_until(lambda: not window.progress.busy)
            window.canvas.perform({'op': 'add-page'})
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Save) as prompt:
                window.move_entry('Drawing.rmdoc', 'Moved.rmdoc')
                self.wait_until(lambda: not window.canvas.busy and not window.progress.busy)
                self.assertEqual(prompt.call_count, 1)
            self.assertFalse((root / 'Drawing.rmdoc').exists())
            self.assertEqual(len(Notebook.read((root / 'Moved.rmdoc').read_bytes()).pages), 2)
            self.assertEqual(window.history[window.index], 'Moved.rmdoc')
            window.close()

    def test_close_during_save_supersedes_deferred_navigation(self):
        from threading import Event
        from shiboken6 import isValid
        from services.documents.storage import DocumentResource
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Home.md').write_text('# Home')
            (root / 'Other.md').write_text('# Other')
            window = self.open_library(root)
            window.open_note('Home.md')
            self.wait_until(lambda: not window.progress.busy)
            window.viewer.set_editing(True)
            window.viewer.set_edit_mode('source')
            window.viewer.editor.insertPlainText('Keep saved ')
            entered, release = Event(), Event()
            original = DocumentResource.save
            def slow(resource, *args, **kwargs):
                entered.set()
                release.wait(5)
                return original(resource, *args, **kwargs)
            try:
                with patch.object(DocumentResource, 'save', new=slow), \
                        patch.object(window.library, 'read', wraps=window.library.read) as read:
                    with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Save):
                        window.open_note('Other.md')
                    self.wait_until(entered.is_set)
                    with patch.object(qt.QMessageBox, 'warning', side_effect=AssertionError('Save already authorized')):
                        window.close()
                    self.assertTrue(window.pending_close)
                    self.assertIsNone(window._after_document_save)
                    release.set()
                    self.wait_until(lambda: not isValid(window))
                    read.assert_not_called()
                self.assertIn('Keep saved', (root / 'Home.md').read_text())
            finally:
                release.set()

    def test_failed_drawing_close_does_not_close_after_later_manual_save(self):
        from shiboken6 import isValid
        from features.notebooks.notebook import Notebook
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Drawing.rmdoc').write_bytes(Notebook.new('Drawing').to_bytes())
            window = self.open_library(root)
            window.open_note('Drawing.rmdoc')
            self.wait_until(lambda: not window.progress.busy)
            window.canvas.perform({'op': 'add-page'})
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Save), \
                    patch('services.documents.storage.DocumentResource.save', side_effect=OSError('Disk full')):
                window.close()
                self.wait_until(lambda: not window.canvas.busy)
            self.assertTrue(isValid(window))
            self.assertFalse(window.pending_close)
            self.assertTrue(window.canvas.document.dirty)
            window.canvas.save_document()
            self.wait_until(lambda: not window.canvas.busy)
            self.assertTrue(isValid(window))
            self.assertFalse(window.canvas.document.dirty)
            self.assertEqual(len(Notebook.read((root / 'Drawing.rmdoc').read_bytes()).pages), 2)
            window.close()

    def test_deleting_other_note_preserves_current_duplicate_history_entry(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            for name in ('A.md', 'B.md', 'C.md'):
                (root / name).write_text('# ' + name)
            window = self.open_library(root)
            for path in ('A.md', 'B.md', 'A.md', 'C.md'):
                window.open_note(path)
                self.wait_until(lambda: not window.progress.busy)
            window.navigate(-1)
            self.wait_until(lambda: not window.progress.busy)
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes):
                window.delete_entry('B.md')
            self.wait_until(lambda: not window.progress.busy)
            self.assertEqual(window.history, ['A.md', 'A.md', 'C.md'])
            self.assertEqual(window.index, 1)
            window.navigate(1)
            self.wait_until(lambda: not window.progress.busy)
            self.assertEqual(window.history[window.index], 'C.md')
            window.close()

    def test_delayed_files_search_cannot_cancel_calendar_or_restart_hidden_scan(self):
        from threading import Event
        from features.text_editor.library_files import daily_notes
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '2026-11-02.md').write_text('# Today')
            window = self.open_library(root)
            entered, release = Event(), Event()
            def slow(*args, **kwargs):
                entered.set()
                release.wait(5)
                return daily_notes(*args, **kwargs)
            try:
                with patch('features.text_editor.library_files.daily_notes', side_effect=slow) as scan:
                    window.panel_tabs.setCurrentIndex(1)
                    self.wait_until(entered.is_set)
                    generation = window.aux_generation
                    window.search.setText('query')
                    window.filter()  # Delayed callback from Files.
                    self.assertEqual(window.aux_generation, generation)
                    self.assertFalse(window.aux.cancelled.is_set())
                    release.set()
                    self.wait_until(lambda: not window.aux.busy)
                    self.assertIn('2026-11-02', window.calendar_entries)
                    window.search.clear()
                    window.panel_tabs.setCurrentIndex(0)
                    window.refresh_calendar()  # A retained button callback.
                    self.assertEqual(scan.call_count, 1)
                    self.assertFalse(window.aux.busy)
            finally:
                release.set()
            window.close()

    def test_close_releases_a_notebook_that_finishes_opening_after_cancellation(self):
        from threading import Event
        from shiboken6 import isValid
        from features.notebooks.notebook import Notebook
        from features.notebooks.storage import NotebookDocument
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Drawing.rmdoc').write_bytes(Notebook.new('Drawing').to_bytes())
            window = self.open_library(root)
            entered, release = Event(), Event()
            documents = []
            def construct(*args, **kwargs):
                document = NotebookDocument(*args, **kwargs)
                documents.append(document)
                entered.set()
                release.wait(5)
                return document
            try:
                with patch('features.notebooks.storage.NotebookDocument', side_effect=construct):
                    window.open_note('Drawing.rmdoc')
                    self.wait_until(entered.is_set)
                    window.close()
                    self.assertTrue(isValid(window))
                    release.set()
                    self.wait_until(lambda: not isValid(window))
                    self.assertTrue(documents[0].resource.closed)
            finally:
                release.set()

    def test_saved_note_refreshes_content_matches_and_visible_connections(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Home.md').write_text('# Needle\n\n[[Missing]]')
            (root / 'Other.md').write_text('# Other')
            window = self.open_library(root)
            window.search.setText('needle')
            window.filter()
            self.wait_until(lambda: not window.aux.busy)
            self.assertEqual([row['path'] for row in window.search_rows], ['Home.md'])
            window.open_note('Home.md')
            self.wait_until(lambda: not window.progress.busy)
            window.toggle_links()
            self.wait_until(lambda: not window.connections_progress.busy)
            self.assertEqual(window.links_tree.topLevelItem(3).text(0), 'Unresolved links (1)')
            window.viewer.set_editing(True)
            window.viewer.set_edit_mode('source')
            window.viewer.editor.selectAll()
            window.viewer.editor.insertPlainText('# Changed\n\n[[Other]]')
            window.viewer.save_document()
            self.wait_until(lambda: not window.progress.busy and not window.aux.busy and not window.connections_progress.busy)
            self.assertEqual(window.search_rows, [])
            self.assertEqual(window.links_tree.topLevelItem(2).text(0), 'Outgoing links (1)')
            self.assertEqual(window.links_tree.topLevelItem(3).text(0), 'Unresolved links (0)')
            window.close()

    def test_failed_mutation_resumes_search_and_connections(self):
        from commonUtils.search.providers import search_resources
        from features.text_editor.notes_links import connections
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Home.md').write_text('# Needle\n\n[[Other]]')
            (root / 'Other.md').write_text('# Other')
            window = self.open_library(root)
            window.open_note('Home.md')
            self.wait_until(lambda: not window.progress.busy)
            window.search.setText('needle')
            window.filter()
            window.toggle_links()
            self.wait_until(lambda: not window.aux.busy and not window.connections_progress.busy)
            with patch.object(qt.QInputDialog, 'getText', return_value=('Other.md', True)), \
                    patch('features.text_editor.ui.library_panels.search_resources', wraps=search_resources) as search, \
                    patch('features.text_editor.notes_links.connections', wraps=connections) as links:
                window.copy_entry('Home.md')
                self.wait_until(lambda: not window.progress.busy and not window.aux.busy and not window.connections_progress.busy)
                self.assertGreaterEqual(search.call_count, 1)
                self.assertGreaterEqual(links.call_count, 1)
            self.assertEqual([row['path'] for row in window.search_rows], ['Home.md'])
            self.assertEqual(window.links_tree.topLevelItem(2).text(0), 'Outgoing links (1)')
            self.assertEqual((root / 'Other.md').read_text(), '# Other')
            window.close()

    def test_recursive_search_modes_prioritize_names_and_exclude_hidden_configuration(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Nested').mkdir()
            (root / 'Nested/turtle red.md').write_text('Name match')
            (root / 'Body.md').write_text('A turtle followed by red.')
            window = self.open_library(root)
            (root / '.obsidian/turtle red.md').write_text('Private configuration')
            window.search.setText('turtle red')
            window.filter()
            self.wait_until(lambda: not window.aux.busy)
            self.assertEqual([row['path'] for row in window.search_rows], ['Nested/turtle red.md', 'Body.md'])
            self.assertNotIn('Nested', window.loaded)
            window.search_mode.setCurrentIndex(1)
            self.wait_until(lambda: not window.aux.busy)
            self.assertEqual([row['path'] for row in window.search_rows], ['Nested/turtle red.md'])
            window.search.clear()
            window.filter()
            self.assertIs(window.files_stack.currentWidget(), window.tree)
            window.close()

    def test_calendar_handles_nested_duplicates_and_confirmed_creation(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Nested').mkdir()
            for path in ['2026-10-15.md', 'Nested/2026-10-15.md']:
                (root / path).write_text('# Daily')
            window = self.open_library(root)
            window.panel_tabs.setCurrentIndex(1)
            self.wait_until(lambda: not window.aux.busy)
            self.assertEqual(len(window.calendar_entries['2026-10-15']), 2)
            with patch.object(qt.QInputDialog, 'getItem', return_value=('Nested/2026-10-15.md', True)):
                window.open_daily_note(qt.QDate(2026, 10, 15))
            self.wait_until(lambda: not window.progress.busy)
            self.assertEqual(window.history[window.index], 'Nested/2026-10-15.md')
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.No):
                window.open_daily_note(qt.QDate(2026, 10, 16))
            self.assertFalse((root / '2026-10-16.md').exists())
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes):
                window.open_daily_note(qt.QDate(2026, 10, 16))
            self.wait_until(lambda: not window.progress.busy and not window.aux.busy)
            self.assertTrue((root / '2026-10-16.md').exists())
            self.assertEqual(window.history[window.index], '2026-10-16.md')
            self.assertTrue(window.viewer.edit_button.isChecked())
            window.close()

    def test_connections_open_targets_and_report_unresolved_links(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Home.md').write_text('# Home\n\n[[Other]] [[Missing]]')
            (root / 'Other.md').write_text('[[Home]]')
            window = self.open_library(root)
            window.open_note('Home.md')
            self.wait_until(lambda: not window.progress.busy)
            window.toggle_links()
            self.wait_until(lambda: not window.connections_progress.busy)
            self.assertGreater(window.links_tree.width(), 100)
            self.assertEqual(window.links_tree.topLevelItem(1).text(0), 'Backlinks (1)')
            self.assertEqual(window.links_tree.topLevelItem(2).text(0), 'Outgoing links (1)')
            self.assertEqual(window.links_tree.topLevelItem(3).child(0).text(0), 'Missing')
            window.choose_connection(window.links_tree.topLevelItem(2).child(0))
            self.wait_until(lambda: not window.progress.busy and not window.connections_progress.busy)
            self.assertEqual(window.history[window.index], 'Other.md')
            window.close()

    def test_copy_collision_and_delete_resolve_unsaved_changes(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Home.md').write_text('Original')
            window = self.open_library(root)
            with patch.object(qt.QInputDialog, 'getText', return_value=('Copy.md', True)):
                window.copy_entry('Home.md')
            self.wait_until(lambda: not window.progress.busy)
            self.assertEqual((root / 'Copy.md').read_text(), 'Original')
            (root / 'Copy.md').write_text('Keep destination')
            with patch.object(qt.QInputDialog, 'getText', return_value=('Copy.md', True)):
                window.copy_entry('Home.md')
            self.wait_until(lambda: not window.progress.busy)
            self.assertEqual((root / 'Copy.md').read_text(), 'Keep destination')
            window.open_note('Home.md')
            self.wait_until(lambda: not window.progress.busy)
            window.viewer.set_editing(True)
            window.viewer.set_edit_mode('source')
            window.viewer.editor.insertPlainText('Draft ')
            draft = window.viewer.markdown_text()
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes), \
                    patch.object(qt.QMessageBox, 'warning', side_effect=AssertionError('Unrelated delete must keep draft')):
                window.delete_entry('Copy.md')
                self.wait_until(lambda: not window.progress.busy)
            self.assertEqual(window.viewer.markdown_text(), draft)
            self.assertTrue(window.viewer.is_modified)
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes):
                with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Cancel):
                    window.delete_entry('Home.md')
                self.assertTrue((root / 'Home.md').exists())
                with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Discard):
                    window.delete_entry('Home.md')
            self.wait_until(lambda: not window.progress.busy)
            self.assertFalse((root / 'Home.md').exists())
            self.assertEqual(window.history, [])
            self.assertIs(window.document_stack.currentWidget(), window.welcome)
            self.assertFalse(window.up.isEnabled())
            window.close()

    def test_connections_do_not_cancel_file_search_and_close_waits_for_both(self):
        from threading import Event
        from shiboken6 import isValid
        from features.text_editor.notes_links import connections
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Home.md').write_text('# Searchable home')
            window = self.open_library(root)
            window.open_note('Home.md')
            self.wait_until(lambda: not window.progress.busy)
            entered, release = Event(), Event()
            def slow(*args, **kwargs):
                entered.set()
                release.wait(5)
                return connections(*args, **kwargs)
            try:
                with patch('features.text_editor.notes_links.connections', side_effect=slow):
                    window.toggle_links()
                    self.wait_until(entered.is_set)
                    window.search.setText('Searchable')
                    window.filter()
                    self.wait_until(lambda: not window.aux.busy)
                    self.assertEqual([row['path'] for row in window.search_rows], ['Home.md'])
                    self.assertTrue(window.connections_progress.busy)
                    window.close()
                    self.assertTrue(isValid(window))
                    release.set()
                    self.wait_until(lambda: not isValid(window))
            finally:
                release.set()

    def test_folder_landing_notes_and_reading_positions(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Topics').mkdir()
            (root / 'Topics/Topics.md').write_text('# Topics\n\n' + '\n\n'.join(f'Paragraph {i}' for i in range(200)))
            (root / 'Other.md').write_text('# Other')
            window = self.open_library(root)
            self.assertFalse(window.items['Topics'].icon(0).isNull())
            self.assertIn('same-named note', window.items['Topics'].toolTip(0))
            self.assertFalse(window.items['Other.md'].icon(0).isNull())
            self.assertIn('File', window.items['Other.md'].toolTip(0))
            window.choose(window.items['Topics'])
            self.wait_until(lambda: not window.progress.busy)
            self.assertEqual(window.history[window.index], 'Topics/Topics.md')
            bar = window.viewer.browser.verticalScrollBar()
            self.wait_until(lambda: bar.maximum() > 500)
            bar.setValue(400)
            window.open_note('Other.md')
            self.wait_until(lambda: not window.progress.busy)
            window.navigate(-1)
            self.wait_until(lambda: not window.progress.busy)
            self.assertEqual(bar.value(), 400)
            window.parent_folder()
            self.wait_until(lambda: not window.progress.busy)
            self.assertIn('Topics', window.loaded)
            window.close()

    def test_close_waits_for_cancelled_background_scan(self):
        from threading import Event
        from shiboken6 import isValid
        with self.temporary_directory() as directory:
            root = Path(directory)
            window = self.open_library(root)
            entered, release = Event(), Event()
            original = window.library.folders
            def slow(*args, **kwargs):
                entered.set()
                release.wait(5)
                return original(*args, **kwargs)
            try:
                with patch.object(window.library, 'folders', side_effect=slow):
                    window.search.setText('query')
                    window.filter()
                    self.wait_until(entered.is_set)
                    window.close()
                    self.assertTrue(isValid(window))
                    self.assertTrue(window.closing)
                    release.set()
                    self.wait_until(lambda: not isValid(window))
            finally:
                release.set()

    def test_remarkable_document_uses_the_same_library_window(self):
        from features.text_editor.notes import NotesLibrary
        from features.notebooks.notebook import Notebook
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '.obsidian').mkdir()
            (root / 'Home.md').write_text('# [[Tech]]\n')
            provider = LocalFiles(root)
            NotesLibrary(provider).create('Drawing', extension='rmdoc')
            window = NotesLibraryWindow(lambda: provider, 'Mixed documents')
            window.show()
            self.wait_until(lambda: not window.progress.busy)
            self.assertIs(window.document_stack.currentWidget(), window.welcome)
            window.open_note('Drawing.rmdoc')
            self.wait_until(lambda: not window.progress.busy)
            self.assertIsNotNone(window.canvas)
            self.assertIs(window.document_stack.currentWidget(), window.canvas)
            from desktop.location_context import document_location
            self.assertEqual(document_location(window), (root / 'Drawing.rmdoc', provider))
            window.canvas.perform({'op': 'add-page'})
            self.assertTrue(window.canvas.document.dirty)
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
                window.open_note('Home.md')
            self.assertEqual(window.history, ['Drawing.rmdoc'])
            self.assertTrue(window.save_drawing.isVisible())
            window.save_drawing.click()
            self.wait_until(lambda: not window.canvas.busy)
            self.assertEqual(len(Notebook.read((root / 'Drawing.rmdoc').read_bytes()).pages), 2)
            window.canvas.perform({'op': 'add-page'})
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Save):
                window.open_note('Home.md')
            self.wait_until(lambda: not window.canvas.busy and not window.progress.busy)
            self.assertEqual(len(Notebook.read((root / 'Drawing.rmdoc').read_bytes()).pages), 3)
            self.assertIs(window.document_stack.currentWidget(), window.viewer)
            window.close()

    def test_formatted_wiki_heading_can_be_edited_and_saved(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '.obsidian').mkdir()
            (root / 'Home.md').write_text('# [[Tech]]\n')
            window = NotesLibraryWindow(lambda: LocalFiles(root), 'Wiki')
            window.show()
            self.wait_until(lambda: not window.progress.busy)
            window.open_note('Home.md')
            self.wait_until(lambda: not window.progress.busy)
            window.viewer.set_editing(True)
            window.viewer.set_edit_mode('formatted')
            editor = window.viewer.formatted_editor
            cursor = editor.textCursor()
            cursor.movePosition(qt.QTextCursor.MoveOperation.End)
            cursor.insertText(' updated')
            window.viewer.save_document()
            self.wait_until(lambda: not window.progress.busy)
            self.assertIn('[[Tech]]', (root / 'Home.md').read_text())
            self.assertIn('updated', (root / 'Home.md').read_text())
            window.close()

    def test_real_localcrypt_and_crypt_remote_open_and_read_notes(self):
        from io import BytesIO
        from features.rclone import executable, session
        from features.rclone.remote_resources import RemoteResources
        from features.rclone.localcrypt.backend import CryptResources
        from tests.local_crypt_fixture import crypt_fixture
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone executable not installed')
        with self.temporary_directory() as directory, crypt_fixture(directory, binary) as fixture:
            fixture.provider.mkdir('.obsidian')
            fixture.provider.mkdir('Nested')
            fixture.provider.create_file('Nested/Next.md', BytesIO(b'# Nested note'))
            fixture.provider.create_file('Nested/Tech.md', BytesIO(b'# Tech'))
            from features.rclone.localcrypt.ui.views import CryptBrowserView
            with patch('features.rclone.executable.get_rclone_path', return_value=binary):
                view = CryptBrowserView(fixture.item)
            view.show()
            self.assertIsNone(view.notes_offer)
            self.wait_until(lambda: view.file_browser.views.root is not None)
            view.close()
            # Seed the synthetic cloud crypt with the same vault marker and nested note.
            environment, source, destination = session.launch(
                fixture.context, str(fixture.item.data), str(fixture.cloud))
            from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
            run_bytes([str(binary), '--config', session.NULL_CONFIG,
                       'copy', '--create-empty-src-dirs', source, destination], environment=environment, max_output=0)
            for remote in (False, True):
                with self.subTest(remote=remote):
                    factory = (lambda: RemoteResources(fixture.context, 'Secret', binary=binary)) if remote else (
                        lambda: CryptResources(fixture.item, binary=binary))
                    window = NotesLibraryWindow(factory, 'Encrypted fixture', remote=remote)
                    window.show()
                    self.wait_until(lambda: not window.progress.busy)
                    if remote:
                        self.assertIsNone(window.library)
                        self.assertIn('local copy', window.progress.message.text())
                        window.close()
                        continue
                    self.assertIsNotNone(window.library, window.progress.message.text())
                    self.assertEqual(window.viewer.allow_edit, not remote)
                    self.assertFalse(window.viewer.edit_button.isChecked())
                    self.assertIn('note.md', window.items)
                    window.open_note('note.md')
                    self.wait_until(lambda: not window.progress.busy)
                    self.assertIn('Original note', window.viewer.browser.toPlainText(), window.viewer.status.text())
                    window.viewer.set_editing(True)
                    self.assertEqual(len(window.storage.resources), 1)
                    url = window.viewer.browser.document().baseUrl().resolved(qt.QUrl('page.png'))
                    image = window.viewer.browser.document().resource(qt.QTextDocument.ResourceType.ImageResource, url)
                    self.assertFalse(image.isNull())
                    window.items['Nested'].setExpanded(True)
                    self.wait_until(lambda: not window.progress.busy)
                    window.open_note('Nested/Next.md')
                    self.wait_until(lambda: not window.progress.busy)
                    self.assertIn('Nested note', window.viewer.browser.toPlainText(), window.viewer.status.text())
                    window.viewer.follow_link(qt.QUrl('note.md'))
                    self.wait_until(lambda: not window.progress.busy)
                    self.assertEqual(window.storage.path, (window.provider.root / 'note.md').resolve(), window.viewer.status.text())
                    window.viewer.follow_link(qt.QUrl('Tech.md'))
                    self.wait_until(lambda: not window.progress.busy)
                    self.assertEqual(window.storage.path, (window.provider.root / 'Nested/Tech.md').resolve(), window.viewer.status.text())
                    window.back.click()
                    self.wait_until(lambda: not window.progress.busy)
                    self.assertEqual(window.history[window.index], 'note.md')
                    window.forward.click()
                    self.wait_until(lambda: not window.progress.busy)
                    self.assertEqual(window.history[window.index], 'Nested/Tech.md')
                    window.open_note('Nested/Next.md')
                    self.wait_until(lambda: not window.progress.busy)
                    if not remote:
                        for mode in ('formatted', 'source'):
                            window.viewer.set_edit_mode(mode)
                            window.viewer.active_editor().insertPlainText('Edited ' + mode + '. ')
                            window.viewer.save_document()
                            self.wait_until(lambda: not window.progress.busy)
                            self.assertFalse(window.viewer.is_modified, window.viewer.status.text())
                            self.assertIn(('Edited ' + mode).encode(), fixture.provider.read_bytes('Nested/Next.md'))
                    from shiboken6 import isValid
                    provider = window.provider
                    session.forget(provider.context)
                    self.wait_until(lambda: not isValid(window) or window.locked)
                    self.assertEqual(window.storage.data, b'')
                    self.assertTrue(provider.closed)
                    if isValid(window):
                        window.close()

    def test_action_uses_only_selected_storage_context(self):
        from dataclasses import replace
        from features.text_editor.notes_actions import sources
        from features.rclone.desktop_service import service
        with self.temporary_directory() as directory:
            root = Path(directory)
            self.fixture(root)
            entry = FolderEntry('Notes', local=LocalFolder(root), remote_name='Notes',
                                remote_source='rclone', remote_context=root / 'keys.conf')
            with patch.object(service.remotes, 'open', side_effect=lambda location: LocalFiles(root)) as remote:
                local_actions = actions(replace(entry, storage_scope='local'))
                remote.assert_not_called()
                self.assertEqual([action.name for action in local_actions], ['Open as Notes Library'])
                cloud_actions = actions(replace(entry, storage_scope='remote'))
                remote.assert_not_called()
                self.assertEqual(cloud_actions, [])
                with patch('features.text_editor.ui.notes_library.open_notes') as opened:
                    local_actions[0].callback()
                    self.assertFalse(opened.call_args.kwargs['remote'])
            self.assertEqual([item[0] for item in sources(replace(entry, local=None, storage_scope='local'))], [])

    def test_workspace_library_starts_reading_and_saves_in_local_context(self):
        with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Discard):
            with self.temporary_directory() as directory:
                root = Path(directory)
                self.fixture(root)
                window = NotesLibraryWindow(lambda: LocalFiles(root), 'Notes')
                window.show()
                self.wait_until(lambda: not window.progress.busy)
                window.open_note('Home.md')
                self.wait_until(lambda: not window.progress.busy)
                self.assertTrue(window.viewer.allow_edit)
                self.assertFalse(window.viewer.edit_button.isChecked())
                window.viewer.set_editing(True)
                window.viewer.set_edit_mode('source')
                window.viewer.editor.insertPlainText('Edited locally. ')
                window.viewer.save_document()
                self.wait_until(lambda: not window.progress.busy)
                self.assertIn('Edited locally.', (root / 'Home.md').read_text(), window.viewer.status.text())
                self.assertFalse(window.viewer.is_modified)
                window.viewer.editor.insertPlainText('Unsaved ')
                with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Cancel):
                    window.open_note('Nested/Next.md')
                    self.assertFalse(window.progress.busy)
                    self.assertFalse(window.prepare_close())
                    self.assertEqual(window.history[window.index], 'Home.md')
                with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Discard) as prompt:
                    window.open_note('Nested/Next.md')
                    self.wait_until(lambda: not window.progress.busy)
                    prompt.assert_called_once()
                self.assertTrue(window.viewer.edit_button.isChecked())
                window.viewer.editor.insertPlainText('Saved on close. ')
                with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Save):
                    self.assertFalse(window.prepare_close())
                from shiboken6 import isValid
                self.wait_until(lambda: not isValid(window) or not window.progress.busy)
                self.assertIn('Saved on close.', (root / 'Nested/Next.md').read_text())

    def test_note_reads_complete_short_chunks_and_enforce_the_total_preview_limit(self):
        from contextlib import contextmanager
        from io import BytesIO
        from features.text_editor.notes import NotesLibrary, MAX_NOTE
        class ShortReads(BytesIO):
            def read(self, count):
                return super().read(min(3, count))
        with self.temporary_directory() as directory:
            root = Path(directory)
            data = b'# Complete note\n'
            (root / 'Note.md').write_bytes(data)
            provider = LocalFiles(root)
            library = NotesLibrary(provider)
            @contextmanager
            def opened(path):
                with ShortReads(data) as stream:
                    yield stream
            for limit in (4, MAX_NOTE):
                with self.subTest(limit=limit), patch.object(provider, 'open', side_effect=opened), \
                        patch('features.text_editor.notes.MAX_NOTE', limit):
                    if limit < len(data):
                        with self.assertRaisesRegex(ValueError, 'too large'):
                            library.read('Note.md')
                    else:
                        self.assertEqual(library.read('Note.md'), data)

    def fixture(self, root):
        (root/'.obsidian').mkdir();(root/'Nested').mkdir()
        (root/'Home.md').write_text('# Home\n\n[Next](Nested/Next.md)')
        (root/'Nested/Next.md').write_text('# Next\n\nA nested note.')
        (root/'.obsidian/private.md').write_text('# Hidden')
        (root/'Other.txt').write_text('Not Markdown')

    def test_location_action_and_documents_host_open_library(self):
        from commonUtils.ui.document_host import register_document_host
        from desktop.documents import DocumentsPage
        with self.temporary_directory() as directory:
            root=Path(directory);self.fixture(root)
            commands=actions(FolderEntry('Notes',local=LocalFolder(root)))
            self.assertEqual([item.name for item in commands], ['Open as Notes Library'])
            host=DocumentsPage(lambda: None);host.show();register_document_host(host)
            try:
                window=commands[0].callback()
                self.wait_until(lambda:not window.progress.busy)
                self.assertIn(window,host.records)
                self.assertIsNotNone(window.search)
                self.assertEqual(window.items[window.library.root].childCount(),3)
                child=window.open_note('Home.md');self.wait_until(lambda:not child.progress.busy and child.index >= 0)
                self.assertIn('Home',child.viewer.browser.toPlainText())
                child=window.open_note('Nested/Next.md');self.wait_until(lambda:not child.progress.busy and child.index >= 0)
                self.assertIn('nested note',child.viewer.browser.toPlainText())
                window.navigate(-1);self.wait_until(lambda:not window.progress.busy)
                self.assertEqual(window.history[window.index],'Home.md')
                window.search.setText('Home')
                self.assertFalse(window.items['Home.md'].isHidden())
            finally:
                self.app._commonutils_document_host = lambda: None
                host.close()

    def test_remote_no_search_no_recursive_index_and_revoked_text_clears(self):
        with self.temporary_directory() as directory:
            root=Path(directory);self.fixture(root)
            provider=RemoteFiles(root)
            window=NotesLibraryWindow(lambda:provider,'Remote',remote=True)
            window.show();self.wait_until(lambda:not window.progress.busy)
            self.assertIsNone(window.library)
            self.assertIn('local copy', window.progress.message.text())
            self.assertEqual(provider.calls, [])
            self.assertTrue(provider.closed)
            window.close()

    def test_marker_file_and_escape_never_open(self):
        with self.temporary_directory() as directory:
            root=Path(directory);(root/'.obsidian').write_text('not directory')
            self.assertEqual(actions(FolderEntry('Not a vault',local=LocalFolder(root))),[])
            (root/'.obsidian').unlink();self.fixture(root)
            window=NotesLibraryWindow(lambda:LocalFiles(root),'Notes')
            window.show();self.wait_until(lambda:not window.progress.busy)
            window.open_note('../outside.md')
            self.assertFalse(window.progress.busy)
            self.assertEqual(window.storage.data,b'')
            window.open_note('.obsidian/private.md')
            self.assertEqual(window.storage.data,b'')

    def test_closing_during_listing_waits_for_worker_and_releases_provider(self):
        from threading import Event
        from shiboken6 import isValid
        with self.temporary_directory() as directory:
            root = Path(directory);self.fixture(root)
            provider = PrivateFiles(root)
            entered, released = Event(), Event()
            original = provider.list
            def blocked(path='', **kwargs):
                entered.set()
                if not released.wait(5):raise RuntimeError('Fixture timed out')
                return original(path, **kwargs)
            with patch.object(provider, 'list', side_effect=blocked):
                window = NotesLibraryWindow(lambda: provider, 'Slow private local')
                window.show()
                try:
                    self.wait_until(entered.is_set)
                    window.close()
                    self.assertTrue(window.closing)
                    self.assertTrue(window.progress.busy)
                finally:
                    released.set()
                self.wait_until(lambda: not isValid(window) or not window.progress.busy)
                self.assertTrue(provider.closed)

    def test_late_private_read_does_not_publish_after_provider_revocation(self):
        from contextlib import contextmanager
        with self.temporary_directory() as directory:
            root = Path(directory);self.fixture(root)
            provider = PrivateFiles(root)
            window = NotesLibraryWindow(lambda: provider, 'Private local')
            window.show();self.wait_until(lambda:not window.progress.busy)
            original = provider.open
            @contextmanager
            def revoked_read(path):
                with original(path) as stream:
                    yield stream
                provider.closed = True
            with patch.object(provider, 'open', side_effect=revoked_read):
                window.open_note('Home.md')
                from shiboken6 import isValid
                self.wait_until(lambda:not isValid(window) or not window.progress.busy)
                if isValid(window):
                    self.assertEqual(window.storage.data, b'')
                    self.assertIsNone(window.viewer.document_state.source_bytes)

    def test_provider_library_embeds_load_from_memory_in_both_modes(self):
        from PIL import Image
        from commonUtils.formats.markdown.images import image_targets
        from services.documents.markdown import prepare_markdown
        for remote in (False, True):
            with self.subTest(remote=remote), self.temporary_directory() as directory:
                root = Path(directory)
                self.fixture(root)
                (root / 'Attachments').mkdir()
                embeds = []
                for kind in ('PNG', 'JPEG', 'WEBP', 'GIF'):
                    filename = 'photo #1.' + kind.lower()
                    Image.new('RGB', (800, 400), 'blue').save(root / 'Attachments' / filename, kind)
                    embeds.append('![[Attachments/' + filename + '|900]]')
                source = '\n\n'.join(embeds) + '\n\nFollowing text'
                path = root / 'Nested/Next.md'
                path.write_text(source)
                provider = PrivateFiles(root) if remote else LocalFiles(root)
                window = NotesLibraryWindow(lambda: provider, 'Images')
                window.show()
                self.wait_until(lambda: not window.progress.busy)
                window.open_note('Nested/Next.md')
                self.wait_until(lambda: not window.progress.busy)
                self.assertEqual(len(window.storage.resources), 4)
                for editing in ((False,) if remote else (False, True)):
                    window.viewer.set_editing(editing)
                    window.viewer.set_edit_mode('formatted')
                    surface = window.viewer.formatted_editor if editing else window.viewer.browser
                    for target in image_targets(source):
                        url = surface.document().baseUrl().resolved(qt.QUrl(target))
                        image = surface.document().resource(qt.QTextDocument.ResourceType.ImageResource, url)
                        self.assertIsInstance(image, qt.QImage)
                        self.assertFalse(image.isNull(), target)
                    self.assertFalse(window.viewer.is_modified)
                if remote:
                    self.assertEqual(provider.calls, [''])
                    window.retire()
                    self.assertEqual(window.storage.resources, {})
                window.close()
                # Direct provider Markdown also collects wiki images, references,
                # spaces and literal hashes, ignoring fenced code.
                sibling = root / 'Nested/photo #1.png'
                Image.new('RGB', (800, 400), 'blue').save(sibling)
                direct = b'![[photo #1.png|500]]\n\n![Reference][pic]\n\n[pic]: <photo #1.png>\n\n```\n![[absent.png]]\n```'
                _, resources = prepare_markdown(LocalFiles(root), path, data=direct)
                self.assertEqual(set(resources), {sibling.resolve()})
