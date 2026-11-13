"""Scoped Notes Library tab groups retain independent drafts and provider leases."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from threading import Event
from time import monotonic
from unittest.mock import patch
from shiboken6 import isValid
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from features.notes_library.ui.library_workspace import TabbedNotesLibrary


def wait_for_cancellation(cancelled):
    deadline = monotonic() + 10
    pause = Event()
    while not cancelled():
        if monotonic() >= deadline:
            raise TimeoutError('Synthetic document worker was not cancelled')
        pause.wait(.01)


class NotesLibraryTabTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.enterContext(patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Discard))
    def opened(self, root):
        (root / '.obsidian').mkdir()
        (root / 'A.md').write_text('# A')
        (root / 'B.md').write_text('# B')
        owner = TabbedNotesLibrary(lambda: LocalFiles(root), 'Tabs')
        owner.show()
        self.addCleanup(lambda: owner.close() if isValid(owner) else None)
        self.wait_until(lambda: not owner.progress.busy)
        return owner

    def note(self, owner, path):
        child = owner.open_note(path, new_tab=True)
        self.wait_until(lambda: not child.progress.busy and child.index >= 0)
        return child

    def test_document_pane_has_no_duplicate_library_navigator(self):
        with self.temporary_directory() as directory:
            owner = self.opened(Path(directory))
            child = self.note(owner, 'A.md')
            self.assertIsInstance(child, qt.QWidget)
            self.assertEqual(child.breadcrumbs.entries, [('A.md', None)])
            self.assertNotIsInstance(child, qt.QMainWindow)
            for name in ('tree', 'panel_tabs', 'calendar', 'search_results', 'aux'):
                self.assertFalse(hasattr(child, name), name)
            self.assertIsNot(child.library, owner.library)
            self.assertIs(child.provider, owner.provider)
            with patch.object(owner, 'reveal_folder') as reveal:
                child.breadcrumbs.linkActivated.emit('0')
                reveal.assert_not_called()
                child.up.click()
                reveal.assert_called_once_with('')
            owner.close()

    def test_direct_video_uses_full_player_without_replacing_library_tab(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'clip.mp4').write_bytes(b'fixture')
            owner = self.opened(root)
            child = self.note(owner, 'A.md')
            before = len(owner.document_tabs.documents)
            with patch('desktop.document_catalog.open_resource') as opened:
                result = owner.open_note('clip.mp4')
                opened.assert_called_once_with(child.provider, 'clip.mp4', child)
                self.assertIs(result, opened.return_value)
            self.assertEqual(len(owner.document_tabs.documents), before)
            self.assertIs(owner.document_tabs.current, child)
            self.assertEqual(child.history[child.index], 'A.md')
            owner.close()

    def test_native_image_preview_does_not_serialize_html(self):
        from services.documents.file_preview import PreviewContent
        with self.temporary_directory() as directory:
            root = Path(directory)
            image = qt.QImage(2, 2, qt.QImage.Format.Format_RGB32)
            image.fill(qt.QColor('white'))
            self.assertTrue(image.save(str(root / 'image.png')))
            owner = self.opened(root)
            with patch.object(PreviewContent, 'html', side_effect=AssertionError('Native image needs no HTML')):
                child = self.note(owner, 'image.png')
                self.assertFalse(child.file_preview.browser.pixmap.isNull())
            owner.close()

    def test_browsing_reuses_active_tab_and_cancel_keeps_draft(self):
        with self.temporary_directory() as directory:
            owner = self.opened(Path(directory))
            first = self.note(owner, 'A.md')
            self.assertIs(owner.open_note('B.md'), first)
            self.wait_until(lambda: not first.progress.busy)
            self.assertEqual(len(owner.document_tabs.documents), 1)
            self.assertEqual(first.history[first.index], 'B.md')
            self.assertEqual(owner.document_tabs.active_group.tabText(0), 'B.md')
            first.viewer.set_editing(True)
            first.viewer.set_edit_mode('source')
            first.viewer.editor.insertPlainText('Keep this draft ')
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Cancel):
                owner.open_note('A.md')
            self.assertEqual(first.history[first.index], 'B.md')
            self.assertIn('Keep this draft', first.viewer.editor.toPlainText())
            owner.close()

    def test_links_panel_belongs_to_its_tab_and_document_uses_available_space(self):
        from commonUtils.ui.appearance.status_line import StatusLine
        with self.temporary_directory() as directory:
            root = Path(directory)
            owner = self.opened(root)
            (root / 'A.md').write_text('# A\n[B](B.md)')
            first = self.note(owner, 'A.md')
            second = self.note(owner, 'B.md')
            self.assertFalse(second.links_button.isHidden())
            toolbar = second.viewer.navigation_toolbar
            self.assertEqual(toolbar.itemAt(toolbar.count() - 1).widget(), second.links_button)
            self.assertTrue(owner.controls_bar.isHidden())
            self.assertTrue(second.controls_bar.isHidden())
            second.links_button.click()
            self.wait_until(lambda: not second.connections_progress.busy)
            self.assertTrue(second.links_tree.isVisible())
            self.assertTrue(second.isAncestorOf(second.links_tree))
            self.assertEqual(second.backlinks_tree.topLevelItem(0).text(0), 'Backlinks (1)')
            owner.open_note('A.md', new_tab=True)
            self.assertTrue(first.links_panel.isHidden())
            self.assertFalse(first.links_button.isChecked())
            owner.open_note('B.md', new_tab=True)
            self.assertTrue(second.links_tree.isVisible())
            second.links_button.click()
            self.app.processEvents()
            second.viewer.status.setText('Formatted edits normalize Markdown syntax.')
            self.app.processEvents()
            self.assertLessEqual(second.viewer.status.height(), StatusLine().sizeHint().height())
            self.assertEqual(second.viewer.geometry().left(), 0)
            self.assertEqual(second.viewer.geometry().right(), second.document_stack.width() - 1)
            second.viewer.status.clear()
            self.wait_until(lambda: owner.operation_footer.height() <= 1)
            self.assertTrue(second.viewer.status.isHidden())
            self.assertLessEqual(second.operation_footer.height(), 1)
            self.assertLessEqual(owner.operation_footer.height(), 1)
            owner.close()

    def test_links_panel_hides_for_other_formats_and_returns_with_markdown(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            owner = self.opened(root)
            (root / 'plain.txt').write_text('Plain text')
            (root / 'unknown.binary').write_bytes(b'\x00binary')
            child = self.note(owner, 'A.md')
            child.links_button.click()
            self.wait_until(lambda: not child.connections_progress.busy)
            for path in ('plain.txt', 'unknown.binary'):
                owner.open_note(path)
                self.wait_until(lambda: not child.progress.busy)
                self.assertTrue(child.links_panel.isHidden())
                self.assertTrue(child.links_button.isChecked())
                self.assertEqual(child.links_tree.topLevelItemCount(), 0)
                self.assertTrue(child.controls_bar.isVisible())
                owner.open_note('A.md')
                self.wait_until(lambda: not child.progress.busy and not child.connections_progress.busy)
                self.assertTrue(child.links_tree.isVisible())
                self.assertTrue(child.links_button.isVisible())
                self.assertTrue(child.controls_bar.isHidden())
                self.assertEqual(child.links_tree.topLevelItem(0).text(0), '2 words · 3 characters')
            owner.close()

    def test_background_note_and_reactivated_tab_refresh_their_own_links(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            owner = self.opened(root)
            (root / 'C.md').write_text('# C\n[B](B.md)')
            first = self.note(owner, 'A.md')
            first.links_button.click()
            self.wait_until(lambda: not first.connections_progress.busy)
            self.note(owner, 'B.md')
            first.open_note('C.md')
            self.wait_until(lambda: not first.progress.busy and not first.connections_progress.busy)
            self.assertFalse(first.isVisible())
            self.assertEqual(first.links_tree.topLevelItem(1).text(0), 'Outgoing links (1)')
            (root / 'C.md').write_text('# C\n[Missing](Missing.md)')
            owner.open_note('C.md', new_tab=True)
            self.wait_until(lambda: not first.connections_progress.busy)
            self.assertEqual(first.links_tree.topLevelItem(1).text(0), 'Outgoing links (0)')
            self.assertEqual(first.links_tree.topLevelItem(2).child(0).text(0), 'Missing.md')
            owner.close()

    def test_library_mutation_refreshes_connections_in_other_tabs(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            owner = self.opened(root)
            (root / 'A.md').write_text('# A\n[B](B.md)')
            first = self.note(owner, 'A.md')
            first.links_button.click()
            self.wait_until(lambda: not first.connections_progress.busy)
            second = self.note(owner, 'B.md')
            owner.move_entry('B.md', 'Renamed.md')
            self.wait_until(lambda: not owner.progress.busy and not second.progress.busy
                            and not first.connections_progress.busy)
            self.assertEqual(first.links_tree.topLevelItem(1).text(0), 'Outgoing links (0)')
            self.assertEqual(first.links_tree.topLevelItem(2).child(0).text(0), 'B.md')
            owner.close()

    def test_saved_links_refresh_backlinks_in_another_split_group(self):
        with self.temporary_directory() as directory:
            owner = self.opened(Path(directory))
            first = self.note(owner, 'A.md')
            first.links_button.click()
            self.wait_until(lambda: not first.connections_progress.busy)
            second = self.note(owner, 'B.md')
            tabs = owner.document_tabs
            self.assertTrue(tabs.move(second, tabs.active_group, 'right'))
            second.viewer.set_editing(True)
            second.viewer.set_edit_mode('source')
            second.viewer.editor.selectAll()
            second.viewer.editor.insertPlainText('# B\n[A](A.md)')
            second.save_current_document()
            self.wait_until(lambda: not second.progress.busy and not first.connections_progress.busy)
            self.assertTrue(first.links_tree.isVisible())
            self.assertEqual(first.backlinks_tree.topLevelItem(0).text(0), 'Backlinks (1)')
            self.assertEqual(first.backlinks_tree.topLevelItem(0).child(0).text(0), 'B.md')
            owner.close()

    def test_images_pdf_and_unknown_files_remain_in_same_library_tab(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            owner = self.opened(root)
            image = qt.QImage(32, 24, qt.QImage.Format.Format_RGB32)
            image.fill(qt.QColor('red'))
            image.save(str(root / 'Image.png'))
            writer = qt.QPdfWriter(str(root / 'Document.pdf'))
            painter = qt.QPainter(writer)
            painter.drawText(20, 40, 'First page')
            writer.newPage()
            painter.drawText(20, 40, 'Second page')
            painter.end()
            del writer
            (root / 'Unknown.binary').write_bytes(b'\x00binary')
            child = self.note(owner, 'A.md')
            with patch('desktop.document_catalog.open_resource', side_effect=AssertionError('Must remain inside library')):
                for path in ('Image.png', 'Document.pdf', 'Unknown.binary', 'B.md'):
                    self.assertIs(owner.open_note(path), child)
                    self.wait_until(lambda: not child.progress.busy)
                    self.assertEqual(child.history[child.index], path, child.viewer.status.text())
                    self.assertEqual(len(owner.document_tabs.documents), 1)
                    self.assertEqual(child.document_resource_path, root / path)
                    if path != 'B.md':
                        self.assertIs(child.document_stack.currentWidget(), child.file_preview)
                        if path == 'Document.pdf':
                            self.assertEqual(child.file_preview.preview.count, 2)
                            pdf = child.file_preview.pdf
                            bar = pdf.verticalScrollBar()
                            child.file_preview.show_page(1)
                            self.assertEqual(child.file_preview.index, 1)
                            boundary = bar.value()
                            self.assertGreater(boundary, 30)
                            for offset in (25, 50, 20):
                                bar.setValue(boundary - offset)
                                self.assertEqual(bar.value(), boundary - offset)
                            child.file_preview.show_page(0)
                            self.assertEqual(child.file_preview.index, 0)
                        if path == 'Image.png':
                            self.assertIn('data:image/png', child.file_preview.browser.toHtml())
                            self.assertFalse(child.file_preview.browser.pixmap.isNull())
            owner.close()

    def test_extensionless_file_links_keep_exact_filename_priority(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            owner = self.opened(root)
            (root / 'LICENSE').write_text('License text')
            (root / 'LICENSE.md').write_text('# Markdown license')
            self.assertEqual(owner.library.link('A.md', 'LICENSE')[0], 'LICENSE')
            self.assertEqual(owner.library.link('A.md', 'B')[0], 'B.md')
            child = self.note(owner, 'A.md')
            child.open_note('LICENSE', resolve_link=True)
            self.wait_until(lambda: not child.progress.busy)
            self.assertEqual(child.history[child.index], 'LICENSE')
            self.assertIs(child.document_stack.currentWidget(), child.file_preview)
            owner.close()

    def test_history_shortcuts_follow_document_controls_across_markdown_and_text(self):
        from PySide6.QtTest import QTest
        with self.temporary_directory() as directory:
            root = Path(directory)
            owner = self.opened(root)
            (root / 'plain.txt').write_text('Plain text')
            first = self.note(owner, 'A.md')
            child = self.note(owner, 'B.md')
            tabs = owner.document_tabs
            self.assertTrue(tabs.move(first, tabs.active_group, 'right'))
            self.assertIs(owner.open_note('B.md', new_tab=True), child)
            owner.open_note('A.md')
            self.wait_until(lambda: not child.progress.busy)
            owner.activateWindow()

            def press(widget, key, expected):
                widget.setFocus()
                self.app.processEvents()
                self.assertIs(self.app.focusWidget(), widget)
                QTest.keyClick(widget, key, qt.Qt.KeyboardModifier.AltModifier)
                QTest.keyRelease(widget, qt.Qt.Key.Key_Alt)
                self.wait_until(lambda: not child.progress.busy)
                self.assertEqual(child.history[child.index], expected)
                self.assertEqual(first.history, ['A.md'])

            press(child.viewer.browser, qt.Qt.Key.Key_Left, 'B.md')
            press(child.viewer.browser, qt.Qt.Key.Key_Right, 'A.md')
            owner.open_note('plain.txt')
            self.wait_until(lambda: not child.progress.busy)
            press(child.text_document.editor, qt.Qt.Key.Key_Left, 'A.md')
            press(child.viewer.browser, qt.Qt.Key.Key_Right, 'plain.txt')
            self.assertIs(child.document_stack.currentWidget(), child.text_document)
            owner.close()

    def test_loading_tab_restores_cancel_footer_and_clears_previous_projection(self):
        from threading import Event
        from features.notes_library.notes import NotesLibrary
        from commonUtils.runtime.operations import OperationCancelled
        with self.temporary_directory() as directory:
            owner = self.opened(Path(directory))
            first = self.note(owner, 'A.md')
            started, release = Event(), Event()
            original = NotesLibrary.load_note
            def read(library, path, *, cancelled, **kwargs):
                if path == 'B.md':
                    started.set()
                    while not release.wait(.01):
                        if cancelled():
                            raise OperationCancelled()
                return original(library, path, cancelled=cancelled, **kwargs)
            with patch.object(NotesLibrary, 'load_note', read):
                second = owner.open_note('B.md', new_tab=True)
                try:
                    self.wait_until(started.is_set)
                    group = owner.document_tabs.active_group
                    group.setCurrentWidget(first)
                    self.assertTrue(second.operation_footer.isHidden())
                    group.setCurrentWidget(second)
                    self.assertTrue(second.progress.isVisible())
                    self.assertFalse(first.operation_footer.isVisible())
                    self.assertEqual(owner.history, [])
                    self.assertEqual(owner.index, -1)
                    self.assertIsNone(owner.document_resource_path)
                    second.progress.cancel_button.click()
                    self.wait_until(lambda: not second.progress.busy)
                finally:
                    release.set()
                    self.wait_until(lambda: not second.progress.busy)
            self.assertTrue(owner.document_tabs.close_tab(second))
            self.assertEqual(owner.history, ['A.md'])
            self.assertTrue(owner.document_tabs.close_tab(first))
            self.assertEqual(owner.history, [])
            self.assertEqual(owner.index, -1)
            self.assertIsNone(owner.document_resource_path)
            self.assertFalse(owner.save_current_document())
            owner.close()

    def test_navigation_and_loading_footer_follow_active_document(self):
        with self.temporary_directory() as directory:
            owner = self.opened(Path(directory))
            first = self.note(owner, 'A.md')
            second = self.note(owner, 'B.md')
            self.assertTrue(owner.navigation.isHidden())
            self.assertEqual(second.viewer.navigation_toolbar.indexOf(second.navigation), 0)
            self.assertFalse(second.back.isHidden())
            self.assertFalse(first.back.isEnabled())
            self.assertFalse(second.back.isEnabled())
            self.assertIs(second.operation_footer.parentWidget(), owner.operation_footer)
            self.assertTrue(first.operation_footer.isHidden())
            self.assertFalse(second.operation_footer.isHidden())
            self.assertIs(owner.open_note('A.md'), second)
            self.wait_until(lambda: not second.progress.busy)
            self.assertEqual(second.history, ['B.md', 'A.md'])
            second.back.click()
            self.wait_until(lambda: not second.progress.busy)
            self.assertIs(owner.document_tabs.current, second)
            self.assertEqual(second.history[second.index], 'B.md')
            self.assertEqual(first.history, ['A.md'])
            self.assertFalse(first.back.isEnabled())
            self.assertTrue(second.forward.isEnabled())
            second.forward.click()
            self.wait_until(lambda: not second.progress.busy)
            self.assertEqual(second.history[second.index], 'A.md')
            second.back.click()
            self.wait_until(lambda: not second.progress.busy)
            self.assertTrue(owner.document_tabs.close_tab(first))
            self.app.processEvents()
            self.assertFalse(second.operation_footer.isHidden())
            from threading import Event
            from commonUtils.runtime.operations import OperationCancelled
            started = Event()
            def lookup(*args, cancelled, **kwargs):
                started.set()
                wait_for_cancellation(cancelled)
                raise OperationCancelled()
            with patch.object(second.library, 'link', side_effect=lookup):
                second.open_note('Missing', resolve_link=True)
                self.wait_until(started.is_set)
                self.assertTrue(second.progress.isVisible())
                self.assertGreater(second.progress.mapTo(owner, qt.QPoint()).y(),
                                   owner.split.geometry().bottom())
                self.assertGreater(second.progress.width(), owner.split.width() * .9)
                second.progress.cancel_button.click()
                self.wait_until(lambda: not second.progress.busy)
            self.assertEqual(second.history[second.index], 'B.md')
            self.assertTrue(second.progress.isHidden())
            owner.close()

    def test_data_view_loading_uses_bottom_footer_and_follows_active_tab(self):
        from threading import Event
        from features.notes_library.ui.dataview import DesktopViews
        with self.temporary_directory() as directory:
            owner = self.opened(Path(directory))
            first = self.note(owner, 'A.md')
            second = self.note(owner, 'B.md')
            views = second.viewer.data_views = DesktopViews(second.viewer)
            started = Event()
            def read(report, cancelled):
                started.set()
                wait_for_cancellation(cancelled)
            views.progress.start(read, message='Reading data view files…')
            try:
                self.wait_until(started.is_set)
                self.app.processEvents()
                self.assertTrue(views.progress.isVisible())
                self.assertGreater(views.progress.mapTo(owner, qt.QPoint()).y(),
                                   owner.split.geometry().bottom())
                self.assertGreater(views.progress.width(), owner.split.width() * .9)
                group = owner.document_tabs.active_group
                group.setCurrentWidget(first)
                self.app.processEvents()
                self.assertFalse(views.progress.isVisible())
                group.setCurrentWidget(second)
                self.app.processEvents()
                self.assertTrue(views.progress.isVisible())
                views.progress.cancel_button.click()
                self.wait_until(lambda: not views.progress.busy)
                self.assertTrue(views.progress.isHidden())
            finally:
                views.progress.request_cancel()
                self.wait_until(lambda: not views.progress.busy)
            self.assertTrue(owner.document_tabs.close_tab(second))
            self.app.processEvents()
            owner.close()

    def test_concurrent_loading_and_notice_share_one_footer_row(self):
        from threading import Event
        from features.notes_library.ui.dataview import DesktopViews
        with self.temporary_directory() as directory:
            owner = self.opened(Path(directory))
            child = self.note(owner, 'A.md')
            viewer = child.viewer
            viewer.set_editing(True)
            viewer.set_editing(False)
            self.assertEqual(viewer.status.text(), '')
            views = viewer.data_views = DesktopViews(viewer)
            started = Event()
            def read(report, cancelled):
                started.set()
                wait_for_cancellation(cancelled)
            views.progress.start(read, message='Reading data view files…')
            try:
                self.wait_until(started.is_set)
                self.app.processEvents()
                row_height = owner.operation_footer.height()
                notice = 'Cannot save note: storage is read-only. ' * 12
                viewer.status.setText(notice)
                viewer.page_loading.show()
                self.app.processEvents()
                self.assertEqual(owner.operation_footer.height(), row_height)
                self.assertTrue(viewer.status.isVisible())
                self.assertEqual(viewer.status.toolTip(), notice)
                self.assertEqual(viewer.status.accessibleDescription(), notice)
                for widget in (viewer.status, viewer.page_loading, views.progress):
                    self.assertTrue(widget.isVisible())
                    self.assertGreater(widget.width(), 0)
                    self.assertLessEqual(widget.height(), row_height)
                self.assertTrue(views.progress.cancel_button.isVisible())
                self.assertTrue(views.progress.cancel_button.isEnabled())
                views.progress.cancel_button.click()
                self.wait_until(lambda: not views.progress.busy)
                self.assertTrue(views.progress.isHidden())
                self.assertTrue(viewer.status.isVisible())
            finally:
                views.progress.request_cancel()
                self.wait_until(lambda: not views.progress.busy)
                viewer.page_loading.hide()
                viewer.status.clear()
            self.wait_until(lambda: owner.operation_footer.height() <= 1)
            owner.close()

    def test_markdown_render_progress_uses_bottom_footer(self):
        with self.temporary_directory() as directory:
            owner = self.opened(Path(directory))
            child = self.note(owner, 'A.md')
            viewer = child.viewer
            def render(url, scroll=None):
                self.app.processEvents()
                self.assertTrue(viewer.page_loading.isVisible())
                self.assertGreater(viewer.page_loading.mapTo(owner, qt.QPoint()).y(),
                                   owner.split.geometry().bottom())
                self.assertLessEqual(viewer.page_loading.width(), 140)
                return True
            with patch.object(viewer, '_render_page', side_effect=render):
                self.assertTrue(viewer._render(qt.QUrl.fromLocalFile(str(Path(directory) / 'A.md'))))
            self.assertTrue(viewer.page_loading.isHidden())
            owner.close()

    def test_status_messages_follow_split_focus_at_workspace_bottom(self):
        with self.temporary_directory() as directory:
            owner = self.opened(Path(directory))
            first = self.note(owner, 'A.md')
            second = self.note(owner, 'B.md')
            tabs = owner.document_tabs
            self.assertTrue(tabs.move(second, tabs.active_group, 'right'))
            first.viewer.status.setText('First document notice')
            second.viewer.status.setText('Second document notice')
            for child, other in ((first, second), (second, first)):
                tabs.activate(tabs.documents[child]['group'])
                self.app.processEvents()
                self.assertTrue(child.viewer.status.isVisible())
                self.assertFalse(other.viewer.status.isVisible())
                self.assertGreater(child.viewer.status.mapTo(owner, qt.QPoint()).y(),
                                   owner.split.geometry().bottom())
            self.assertTrue(tabs.close_tab(second))
            self.app.processEvents()
            self.assertTrue(first.viewer.status.isVisible())
            self.assertTrue(tabs.close_tab(first))
            self.wait_until(lambda: owner.operation_footer.height() <= 1)
            owner.close()

    def test_source_save_progress_uses_bottom_footer_and_follows_active_tab(self):
        from threading import Event
        with self.temporary_directory() as directory:
            root = Path(directory)
            owner = self.opened(root)
            first = self.note(owner, 'A.md')
            (root / 'source.py').write_text('original = True\n')
            second = self.note(owner, 'source.py')
            editor = second.text_document
            editor.editor.setPlainText('saved = True\n')
            started, release = Event(), Event()
            save = editor.resource.save
            def write(*args, **kwargs):
                started.set()
                release.wait(5)
                return save(*args, **kwargs)
            with patch.object(editor.resource, 'save', side_effect=write):
                try:
                    self.assertTrue(editor.save())
                    self.wait_until(started.is_set)
                    self.app.processEvents()
                    self.assertTrue(editor.operation.isVisible())
                    self.assertGreater(editor.operation.mapTo(owner, qt.QPoint()).y(),
                                       owner.split.geometry().bottom())
                    self.assertGreater(editor.operation.width(), owner.split.width() * .9)
                    group = owner.document_tabs.active_group
                    group.setCurrentWidget(first)
                    self.app.processEvents()
                    self.assertFalse(editor.operation.isVisible())
                    group.setCurrentWidget(second)
                    self.app.processEvents()
                    self.assertTrue(editor.operation.isVisible())
                finally:
                    release.set()
                    self.wait_until(lambda: not editor.busy)
            self.assertTrue(editor.operation.isHidden())
            self.assertEqual((root / 'source.py').read_text(), 'saved = True\n')
            self.assertFalse(editor.dirty)
            self.app.processEvents()
            self.assertEqual(editor.status.text(), 'Saved.')
            self.assertGreater(editor.status.mapTo(owner, qt.QPoint()).y(),
                               owner.split.geometry().bottom())
            owner.open_note('B.md')
            self.wait_until(lambda: not second.progress.busy)
            self.app.processEvents()
            self.assertTrue(editor.status.isHidden())
            owner.close()

    def test_each_split_tab_keeps_history_and_parent_folder(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            owner = self.opened(root)
            (root / 'Folder').mkdir()
            (root / 'Folder/C.md').write_text('# C')
            (root / 'D.md').write_text('# D')
            first = self.note(owner, 'A.md')
            owner.open_note('Folder/C.md')
            self.wait_until(lambda: not first.progress.busy)
            second = self.note(owner, 'B.md')
            owner.open_note('D.md')
            self.wait_until(lambda: not second.progress.busy)
            tabs = owner.document_tabs
            tabs.move(second, tabs.active_group, 'right')
            self.assertEqual(first.history, ['A.md', 'Folder/C.md'])
            self.assertEqual(second.history, ['B.md', 'D.md'])
            first.back.click()
            self.wait_until(lambda: not first.progress.busy)
            self.assertEqual(first.history[first.index], 'A.md')
            self.assertEqual(second.history[second.index], 'D.md')
            self.assertTrue(first.forward.isEnabled())
            self.assertFalse(second.forward.isEnabled())
            first.forward.click()
            self.wait_until(lambda: not first.progress.busy)
            with patch.object(owner, 'reveal_folder') as reveal:
                first.up.click()
                reveal.assert_called_once_with('Folder')
            self.assertIs(tabs.current, first)
            second.back.click()
            self.wait_until(lambda: not second.progress.busy)
            self.assertEqual(second.history[second.index], 'B.md')
            self.assertEqual(first.history[first.index], 'Folder/C.md')
            tabs.activate(tabs.documents[second]['group'])
            self.assertIs(owner.open_note('A.md'), second)
            self.wait_until(lambda: not second.progress.busy)
            self.assertEqual(second.history, ['B.md', 'A.md'])
            self.assertFalse(second.forward.isEnabled())
            self.assertEqual(first.history, ['A.md', 'Folder/C.md'])
            owner.close()

    def test_independent_drafts_scoped_groups_and_cancelled_close(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            owner = self.opened(root)
            from desktop.location_context import document_title
            self.assertEqual(owner.windowTitle(), root.name)
            first = self.note(owner, 'A.md')
            self.assertEqual(document_title(owner), root.name)
            first.viewer.set_editing(True)
            first.viewer.set_edit_mode('source')
            first.viewer.editor.insertPlainText('Unsaved A ')
            with patch.object(qt.QMessageBox, 'warning', side_effect=AssertionError('Switching tabs must retain drafts')):
                second = self.note(owner, 'B.md')
            self.assertIn('Unsaved A', first.viewer.editor.toPlainText())
            tabs = owner.document_tabs
            group = tabs.active_group
            self.assertTrue(tabs.move(second, group, 'right'))
            self.assertEqual(len(tabs.groups), 2)
            self.assertEqual(tabs.groups[0].widget(0), first)
            self.assertEqual(tabs.groups[1].widget(0), second)
            self.assertIs(owner.open_note('A.md', new_tab=True), first)
            self.assertIs(tabs.current, first)
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Cancel):
                self.assertFalse(tabs.close_tab(first))
            self.assertIn(first, tabs.documents)
            from PySide6.QtTest import QTest
            owner.activateWindow()
            first.viewer.editor.setFocus()
            self.app.processEvents()
            self.assertIs(self.app.focusWidget(), first.viewer.editor)
            combination = first.save_action.shortcut()[0]
            QTest.keyClick(first.viewer.editor, combination.key(), combination.keyboardModifiers())
            self.wait_until(lambda: not first.progress.busy)
            self.assertIn('Unsaved A', (root / 'A.md').read_text(),
                          (first.save_action.shortcut().toString(), first.save_action.isEnabled(), self.app.activeWindow()))
            self.assertTrue(tabs.close_tab(first))
            self.assertNotIn(first, tabs.documents)
            owner.close()

    def test_mutations_preserve_each_tabs_history_occurrences_and_identity(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            owner = self.opened(root)
            first = self.note(owner, 'A.md')
            for path in ('B.md', 'A.md'):
                owner.open_note(path)
                self.wait_until(lambda: not first.progress.busy)
            second = self.note(owner, 'B.md')
            for path in ('A.md', 'B.md'):
                owner.open_note(path)
                self.wait_until(lambda: not second.progress.busy)
            tabs = owner.document_tabs
            def settled():
                return not owner.progress.busy and all(not child.progress.busy for child in tabs.documents)
            owner.move_entry('A.md', 'Renamed.md')
            self.wait_until(settled)
            self.assertEqual(set(tabs.documents), {first, second})
            self.assertEqual(first.history, ['Renamed.md', 'B.md', 'Renamed.md'])
            self.assertEqual(first.index, 2)
            self.assertEqual(second.history, ['B.md', 'Renamed.md', 'B.md'])
            self.assertEqual(second.index, 2)
            first.back.click()
            self.wait_until(settled)
            self.assertEqual(first.history[first.index], 'B.md')
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes):
                owner.delete_entry('Renamed.md')
                self.wait_until(settled)
            self.assertEqual(first.history, ['B.md'])
            self.assertEqual(first.index, 0)
            self.assertEqual(second.history, ['B.md', 'B.md'])
            self.assertEqual(second.index, 1)
            second.back.click()
            self.wait_until(settled)
            self.assertEqual(second.index, 0)
            self.assertTrue(second.forward.isEnabled())
            owner.move_entry('B.md', 'Moved.md')
            self.wait_until(settled)
            self.assertEqual(set(tabs.documents), {first, second})
            self.assertEqual(first.history, ['Moved.md'])
            self.assertEqual(second.history, ['Moved.md', 'Moved.md'])
            self.assertEqual(second.index, 0)
            self.assertEqual(first.document_resource_path, root / 'Moved.md')
            self.assertEqual(second.document_resource_path, root / 'Moved.md')
            owner.close()

    def test_mutation_does_not_race_pending_document_read(self):
        from threading import Event
        from commonUtils.runtime.operations import OperationCancelled
        with self.temporary_directory() as directory:
            root = Path(directory)
            owner = self.opened(root)
            child = self.note(owner, 'A.md')
            started = Event()
            def read(*args, cancelled, **kwargs):
                started.set()
                wait_for_cancellation(cancelled)
                raise OperationCancelled()
            with patch.object(child.library, 'load_note', side_effect=read):
                owner.open_note('B.md')
                self.wait_until(started.is_set)
                owner.move_entry('A.md', 'Renamed.md')
                self.assertFalse(owner.progress.busy)
                self.assertTrue((root / 'A.md').exists())
                child.progress.cancel_button.click()
                self.wait_until(lambda: not child.progress.busy)
            owner.move_entry('A.md', 'Renamed.md')
            self.wait_until(lambda: not owner.progress.busy and not child.progress.busy)
            self.assertEqual(child.history, ['Renamed.md'])
            self.assertEqual(child.document_resource_path, root / 'Renamed.md')
            owner.close()

    def test_deleting_inactive_dirty_tab_can_be_cancelled(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            owner = self.opened(root)
            first = self.note(owner, 'A.md')
            first.viewer.set_editing(True)
            first.viewer.set_edit_mode('source')
            first.viewer.editor.insertPlainText('Keep this draft ')
            second = self.note(owner, 'B.md')
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes), \
                    patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Cancel):
                owner.delete_entry('A.md')
            self.assertFalse(owner.progress.busy)
            self.assertTrue((root / 'A.md').exists())
            self.assertIn(first, owner.document_tabs.documents)
            self.assertIn('Keep this draft', first.viewer.editor.toPlainText())
            self.assertIs(owner.document_tabs.current, second)
            owner.close()

    def test_failed_history_open_preserves_cursor_and_forward_branch(self):
        with self.temporary_directory() as directory:
            owner = self.opened(Path(directory))
            child = self.note(owner, 'A.md')
            owner.open_note('B.md')
            self.wait_until(lambda: not child.progress.busy)
            with patch.object(child.library, 'load_note', side_effect=ValueError('Read rejected')):
                child.back.click()
                self.wait_until(lambda: not child.progress.busy)
            self.assertEqual(child.history, ['A.md', 'B.md'])
            self.assertEqual(child.index, 1)
            self.assertTrue(child.back.isEnabled())
            self.assertFalse(child.forward.isEnabled())
            child.back.click()
            self.wait_until(lambda: not child.progress.busy)
            self.assertEqual(child.index, 0)
            self.assertTrue(child.forward.isEnabled())
            self.assertEqual(owner.history, child.history)
            self.assertEqual(owner.index, child.index)
            owner.close()

    def test_rename_and_delete_update_all_open_document_tabs(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            owner = self.opened(root)
            first = self.note(owner, 'A.md')
            second = self.note(owner, 'B.md')
            owner.document_tabs.move(second, owner.document_tabs.active_group, 'right')
            first_group = owner.document_tabs.documents[first]['group']
            owner.move_entry('A.md', 'Renamed.md')
            self.wait_until(lambda: not owner.progress.busy and (root / 'Renamed.md').exists())
            self.wait_until(lambda: any(child.index >= 0 and child.history[child.index] == 'Renamed.md'
                                       for child in owner.document_tabs.documents))
            self.assertFalse(any(owner.document_tabs.path(child) == 'A.md' for child in owner.document_tabs.documents))
            moved = next(child for child in owner.document_tabs.documents if owner.document_tabs.path(child) == 'Renamed.md')
            self.assertIs(owner.document_tabs.documents[moved]['group'], first_group)
            self.wait_until(lambda: not moved.progress.busy)
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes):
                owner.delete_entry('B.md')
                self.wait_until(lambda: not owner.progress.busy)
            self.assertFalse(any(owner.document_tabs.path(child) == 'B.md' for child in owner.document_tabs.documents))
            owner.close()

    def test_private_tabs_share_a_lease_until_all_documents_close(self):
        from io import BytesIO
        from features.rclone import executable
        from tests.local_crypt_fixture import crypt_fixture
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is unavailable')
        with self.temporary_directory() as directory, crypt_fixture(directory, binary) as fixture:
            provider = fixture.provider
            provider.mkdir('.obsidian')
            provider.create_file('B.md', BytesIO(b'# B'))
            owner = TabbedNotesLibrary(lambda: provider, 'Private tabs')
            owner.show()
            self.wait_until(lambda: not owner.progress.busy)
            first = self.note(owner, 'note.md')
            self.note(owner, 'B.md')
            self.assertTrue(owner.document_tabs.close_tab(first))
            self.assertFalse(provider.closed)
            owner.close()
            self.wait_until(lambda: provider.closed)
