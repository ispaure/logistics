"""Offscreen reader controls, browser registration and worker lifetimes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import unittest
from unittest.mock import patch
from books_fixture import make_book
from commonUtils.ui import pyside as qt
from features.books import register
from features.books.epub import EPUBBook
from features.books.reader import BooksPage, BookWindow
from features.books.metadata_editor import MetadataEditor
from features.books.preferences import ReadingState


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = make_book(self.folder / 'book.epub')
        self.page = BooksPage(state_folder=self.folder / 'state')
        self.addCleanup(self.page.deleteLater)
        self.page.resize(1150, 850)
        self.page.show()
        self.page._loaded(EPUBBook(self.path))
        self.app.processEvents()

    def test_arrows_from_chapter_sidebar_and_wheel_turn_pages_without_scrolling(self):
        from PySide6.QtTest import QTest
        from unittest.mock import Mock
        self.page.turn_page = Mock()
        self.page.chapters.setFocus()
        QTest.keyClick(self.page.chapters, qt.Qt.Key.Key_Right)
        self.page.turn_page.assert_called_once_with(1)
        self.page.turn_page.reset_mock()
        QTest.keyClick(self.page.chapters, qt.Qt.Key.Key_Left)
        self.page.turn_page.assert_called_once_with(-1)
        before = self.page.text.verticalScrollBar().value()
        self.page.turn_page.reset_mock()
        for key in (qt.Qt.Key.Key_Up, qt.Qt.Key.Key_Down):
            QTest.keyClick(self.page.text, key)
        self.assertEqual(self.page.text.verticalScrollBar().value(), before)

        self.page.turn_page.assert_not_called()
        turns = Mock()
        self.page.text.pageTurn.connect(turns)
        event = qt.QWheelEvent(qt.QPointF(10,10), qt.QPointF(10,10), qt.QPoint(), qt.QPoint(0,-120),
                              qt.Qt.MouseButton.NoButton, qt.Qt.KeyboardModifier.NoModifier,
                              qt.Qt.ScrollPhase.NoScrollPhase, False)
        self.app.sendEvent(self.page.text.viewport(), event)
        turns.assert_called_once_with(1)
        self.assertEqual(self.page.text.verticalScrollBar().value(), before)
        # Find inputs keep their normal caret arrows.
        self.page.query.setText('abc')
        self.page.query.setCursorPosition(1)
        QTest.keyClick(self.page.query, qt.Qt.Key.Key_Right)
        self.assertEqual(self.page.query.cursorPosition(), 2)


    def test_book_track_has_nested_markers_and_click_seeks_to_another_chapter(self):
        from PySide6.QtTest import QTest
        track = self.page.book_progress
        self.assertEqual([marker[1] for marker in track.markers], [0, 1, 0])
        self.assertGreater(track.markers[1][0], track.markers[0][0])
        QTest.mouseClick(track, qt.Qt.MouseButton.LeftButton,
                         pos=qt.QPoint(track.width() - 6, 12))
        self.app.processEvents()
        self.assertEqual(self.page._current, 1)
        self.assertGreater(track.fraction, track.boundaries[1])

    def test_wide_spread_turns_two_pages_and_resize_retains_the_text_anchor(self):
        from PySide6.QtTest import QTest
        self.page.text.setHtml(''.join(f'<p>Paragraph {i}: ' + 'Readable text. ' * 30 + '</p>'
                                       for i in range(100)))
        self.page.resize(1600, 650); QTest.qWait(200)
        self.assertTrue(self.page.spread.enabled)
        self.assertTrue(self.page.spread.second.isVisible())
        self.page.text.show_page(2)
        self.page.turn_page(1)
        self.assertEqual(self.page.text.page_index, 4)
        self.assertEqual(self.page.spread.second.page_index, 5)
        anchor = self.page.text.location()
        self.page.resize(950, 650); QTest.qWait(200)
        self.assertFalse(self.page.spread.enabled)
        cursor = qt.QTextCursor(self.page.text.document()); cursor.setPosition(anchor)
        self.assertTrue(self.page.text.viewport().rect().contains(self.page.text.cursorRect(cursor).center()))

    def test_read_aloud_follows_the_word_and_resize_centers_its_pointer(self):
        from PySide6.QtTest import QTest
        from commonUtils.tests.test_read_aloud import SilentEngine
        from PySide6.QtTextToSpeech import QTextToSpeech
        self.page.text.setHtml('<p>' + 'A paragraph to read. ' * 600 + '</p>')
        QTest.qWait(200)
        speech = self.page.speech
        speech.engine_factory = SilentEngine
        speech.show()
        speech.engine.engineCapabilities = lambda: QTextToSpeech.Capability.WordByWordProgress
        speech.start()
        speech.engine.sayingWord.emit('paragraph', 0, 1200, 9)
        self.assertEqual(self.page.text.read_pointer, speech._utterance_offset + 1200)
        self.page.resize(920, 600); QTest.qWait(200)
        cursor = qt.QTextCursor(self.page.text.document()); cursor.setPosition(self.page.text.read_pointer)
        midpoint = self.page.text.cursorRect(cursor).center().y()
        self.assertLess(abs(midpoint - self.page.text.viewport().height() / 2), 50)
        speech.stop()
        self.assertIsNone(self.page.text.read_pointer)
        self.assertEqual(self.page.text.extraSelections(), [])
        self.assertEqual(self.page.spread.second.extraSelections(), [])
    def wait_idle(self, page):
        loop = qt.QEventLoop()
        page.idle.connect(loop.quit)
        timeout = qt.QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timeout.start(3000)
        if page.worker:
            loop.exec()
        page.idle.disconnect(loop.quit)
        self.assertIsNone(page.worker, 'Book worker did not finish')
        self.app.processEvents()

    def test_chapters_nested_navigation_internal_links_and_boundaries(self):
        self.assertEqual(self.page.chapters.topLevelItemCount(), 2)
        self.assertEqual(self.page.chapters.topLevelItem(0).childCount(), 1)
        self.page.go_chapter(1)
        self.assertIn('Another chapter', self.page.text.toPlainText())
        self.assertFalse(self.page.next.isEnabled())
        self.page.go_chapter(-1)
        self.assertEqual(self.page._current, 1)
        self.page._link_clicked(qt.QUrl('one.xhtml#nested'))
        self.assertEqual(self.page._current, 0)
        self.page._link_clicked(qt.QUrl('https://example.com'))
        self.assertIn('inside the EPUB', self.page.status.text())

    def test_font_themes_search_and_resource_blocking(self):
        from commonUtils.ui.theme import apply_theme
        apply_theme(mode='dark')
        self.page.font_size.setValue(27)
        self.page.spacing.setValue(140)
        self.app.processEvents()
        self.assertEqual(self.page.text.document().defaultFont().pointSize(), 27)
        self.assertEqual(self.page.text.document().begin().next().blockFormat().lineHeight(), 140)
        self.page.theme.setCurrentIndex(self.page.theme.findData('dark'))
        self.assertIn('#111111', self.page.text.styleSheet())
        self.page.query.setText('hello')
        self.page.find_next()
        self.assertEqual(self.page.text.textCursor().selectedText(), 'HELLO')
        self.assertIsNone(self.page.text.loadResource(qt.QTextDocument.ResourceType.ImageResource, qt.QUrl('file:///etc/passwd')))
        self.assertIsNone(self.page.text.loadResource(qt.QTextDocument.ResourceType.ImageResource, qt.QUrl('https://example.com/image.png')))

    def test_reader_menus_sidebar_appearance_and_search_are_discoverable(self):
        from PySide6.QtTest import QTest
        self.assertEqual([action.text().replace('&', '') for action in self.page.menus.bar.actions()],
                         ['File', 'Edit', 'View', 'Navigate'])
        self.assertFalse(self.page.find_panel.isVisible())
        self.page.activateWindow()
        self.page.text.setFocus()
        self.app.processEvents()
        QTest.keyClick(self.page.text, qt.Qt.Key.Key_F, qt.Qt.KeyboardModifier.ControlModifier)
        self.app.processEvents()
        self.assertTrue(self.page.find_panel.isVisible())
        self.page.sidebar_action.trigger()
        self.assertFalse(self.page.sidebar.isVisible())
        self.page.show_bookmarks()
        self.assertTrue(self.page.sidebar.isVisible())
        self.assertEqual(self.page.sidebar.currentIndex(), 1)
        self.page.reading_width.setValue(600)
        self.assertEqual(self.page.text.maximumWidth(), 600)
        QTest.qWait(20)
        self.assertEqual(self.page.text.width(), 600)
        self.assertGreaterEqual(self.page.progress_label.width(),
                                self.page.progress_label.fontMetrics().horizontalAdvance(self.page.progress_label.text()))
        self.page.show_appearance()
        self.assertTrue(self.page.appearance.isVisible())
        self.page.appearance.hide()

    def test_embedded_close_keeps_the_logistics_page_available(self):
        self.page.menus.close_action.trigger()
        self.assertIsNone(self.page.book)
        self.assertTrue(self.page.isVisible())
        self.assertFalse(self.page.menus.metadata_action.isEnabled())

    def test_embedded_image_loading_preserves_aspect_ratio(self):
        image = qt.QImage(20, 40, qt.QImage.Format.Format_RGB32)
        image.fill(qt.QColor('green'))
        buffer = qt.QBuffer()
        buffer.open(qt.QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, 'PNG')
        with ZipFile(self.path, 'a') as archive:
            archive.writestr('OPS/picture.png', bytes(buffer.data()))
        self.page._loaded(EPUBBook(self.path))
        loaded = self.page.text.loadResource(qt.QTextDocument.ResourceType.ImageResource, qt.QUrl('epub:/OPS/picture.png'))
        self.assertEqual((loaded.width(), loaded.height()), (20, 40))

    def test_malformed_saved_state_does_not_break_opening(self):
        state = ReadingState(self.path, folder=self.folder / 'state')
        state.path.parent.mkdir(parents=True, exist_ok=True)
        state.path.write_text('{"theme": [], "font_size": "huge", "position": NaN, "bookmarks": "invalid"}')
        self.page._loaded(EPUBBook(self.path))
        self.app.processEvents()
        self.assertIn('First chapter', self.page.text.toPlainText())

    def test_page_close_retries_parent_after_worker_completion(self):
        closed = []
        with patch.object(self.page, 'close', side_effect=lambda: closed.append(True)):
            self.page.open_book(self.path)
            self.assertFalse(self.page.prepare_close())
            self.wait_idle(self.page)
        self.assertTrue(closed)

    def test_bookmarks_and_saved_chapter_preferences(self):
        self.page.go_chapter(1)
        self.page.font_size.setValue(25)
        with patch.object(qt.QInputDialog, 'getText', return_value=('My place', True)):
            self.page.add_bookmark()
        self.page._save_state()
        state = ReadingState(self.path, folder=self.folder / 'state').load()
        self.assertEqual(state['font_size'], 25)
        self.assertEqual(state['path'], 'OPS/Text/two.xhtml')
        self.assertEqual(state['bookmarks'][0]['label'], 'My place')
        self.page.go_chapter(0)
        self.page.open_bookmark(0)
        self.assertEqual(self.page._current, 1)
        self.page.delete_bookmark()
        self.assertEqual(self.page.bookmarks.count(), 0)

    def test_open_task_and_failed_open_keep_current_book(self):
        self.page.open_book(self.path)
        self.wait_idle(self.page)
        self.assertEqual(self.page.book.title, 'Sample Book')
        self.page.open_book(self.folder / 'missing.epub')
        self.wait_idle(self.page)
        self.assertEqual(self.page.book.title, 'Sample Book')
        self.assertIn('missing.epub', self.page.status.text())

    def test_metadata_dialog_updates_direct_book_and_reader_title(self):
        def accept(dialog):
            dialog.fields['title'].setText('Edited from reader')
            return qt.QDialog.DialogCode.Accepted
        with patch.object(MetadataEditor, 'exec', accept):
            self.page.edit_metadata()
        self.wait_idle(self.page)
        self.assertEqual(EPUBBook(self.path).title, 'Edited from reader')
        self.assertEqual(self.page.title.text(), 'Edited from reader')
        self.assertTrue((self.folder / 'book.epub.bak').is_file())

    def test_metadata_form_keeps_additional_titles_and_languages(self):
        from features.books.metadata import save_metadata
        book, _ = save_metadata(self.page.book, {'title': ['Main title', 'Titre français'], 'language': ['en', 'fr']})
        dialog = MetadataEditor(book)
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.changes(), {})
        dialog.fields['publisher'].setText('Publisher')
        self.assertEqual(dialog.changes(), {'publisher': ['Publisher']})
        dialog.fields['title'].setText('Revised title')
        self.assertEqual(dialog.changes()['title'], ['Revised title', 'Titre français'])

    def test_lazy_feature_registration_and_browser_controller(self):
        from commonUtils.fileTypes.registry import FileTypeRegistry
        from features.books.file_type import EPUBFile
        definition = register()
        self.assertEqual(definition.id, 'books')
        self.assertEqual(definition.requires, ())
        self.assertEqual(definition.pages, [])
        registry = FileTypeRegistry()
        registry.register(EPUBFile, extensions='epub')
        self.assertIsInstance(registry.create(self.path), EPUBFile)
        controller = definition.browser.create_controller(self.page)
        window = controller.open(self.path)
        # Reading state is not touched by this fixture's initial open until idle.
        window.reader._state_folder = self.folder / 'state'
        self.wait_idle(window.reader)
        self.assertEqual(window.reader.book.title, 'Sample Book')
        self.assertTrue(controller.prepare_close())
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.assertEqual(controller.windows, [])

    def test_browser_metadata_action_opens_only_editor_and_saves(self):
        from features.books.metadata_window import MetadataWindow
        controller = register().browser.create_controller(self.page)
        with patch('features.books.controller.BookWindow', side_effect=AssertionError('Reader should not open')):
            window = controller.open(self.path, edit=True)
            self.wait_idle(window)
        self.assertIsInstance(window, MetadataWindow)
        self.assertIsNone(window.findChild(qt.QTextBrowser))
        self.assertEqual(window.editor.fields['title'].text(), 'Sample Book')
        window.editor.fields['title'].setText('Edited without reader')
        window.editor._accept()
        self.wait_idle(window)
        self.assertEqual(EPUBBook(self.path).title, 'Edited without reader')
        self.assertTrue((self.folder / 'book.epub.bak').is_file())
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.assertEqual(controller.windows, [])

    def test_standalone_metadata_save_failure_keeps_editor_open_for_retry(self):
        controller = register().browser.create_controller(self.page)
        window = controller.open(self.path, edit=True)
        self.wait_idle(window)
        window.editor.fields['title'].setText('Keep my edit')
        with patch('features.books.metadata_window.save_metadata', side_effect=OSError('Cannot save here')):
            window.editor._accept()
            self.wait_idle(window)
        self.assertTrue(window.isVisible())
        self.assertTrue(window.editor.isEnabled())
        self.assertEqual(window.editor.fields['title'].text(), 'Keep my edit')
        self.assertIn('Cannot save here', window.status.text())
        self.assertEqual(EPUBBook(self.path).title, 'Sample Book')
        window.close()

    def test_standalone_metadata_close_waits_for_loading(self):
        controller = register().browser.create_controller(self.page)
        window = controller.open(self.path, edit=True)
        self.assertFalse(controller.prepare_close())
        self.wait_idle(window)
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.assertEqual(controller.windows, [])

    def test_window_close_waits_for_its_worker(self):
        window = BookWindow(self.path)
        window.reader._state_folder = self.folder / 'state'
        window.show()
        destroyed = []
        window.destroyed.connect(lambda: destroyed.append(True))
        self.assertIsNotNone(window.reader.worker)
        window.close()
        self.assertTrue(window._close_pending)
        self.wait_idle(window.reader)
        self.assertTrue(destroyed or not window.isVisible())
