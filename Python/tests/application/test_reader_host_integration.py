"""Real Markdown, EPUB and comic readers close without exiting the application."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from tests.application._main_window_fixture import MainWindowFixture


class ReaderHostIntegrationTests(MainWindowFixture, QtTestCase):
    def test_document_x_closes_only_its_document_attached_or_floating(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from commonUtils.ui.markdown import open_markdown
        window = self.window(); window.dlg.show()
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'note.md'; path.write_text('# Note')
            for floating in (False, True):
                document = open_markdown(path)
                for _ in range(5): self.app.processEvents()
                dock = window.documents.records[document]['dock']
                if floating:
                    dock.setFloating(True)
                for _ in range(5): self.app.processEvents()
                with patch.object(window, 'can_close', wraps=window.can_close) as close_main:
                    dock.tab_header.close_button.click()
                    for _ in range(10): self.app.processEvents()
                    close_main.assert_not_called()
                self.assertTrue(window.dlg.isVisible())
                self.assertFalse(window._closing)
                self.assertEqual(window.documents.count, 0)
                self.assertEqual(window.documents.workspace.docks, [])

    def test_actual_epub_and_comic_x_never_close_the_application(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from time import monotonic, sleep
        from io import BytesIO
        from zipfile import ZipFile
        from PIL import Image
        from tests.books_fixture import make_book
        from features.books.ui.reader import BookWindow
        from features.comics.pages import ComicPages
        from features.comics.ui.reader import ComicReaderWindow
        from commonUtils.ui.document_host import show_document
        from PySide6.QtTest import QTest, QSignalSpy
        from shiboken6 import isValid
        window = self.window(); window.dlg.show()
        quit_signal = QSignalSpy(self.app.lastWindowClosed)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            epub = root/'sample.epub'; make_book(epub)
            comic = root/'sample.cbz'
            output = BytesIO(); Image.new('RGB', (20, 30), 'red').save(output, 'PNG')
            with ZipFile(comic, 'w') as archive:
                archive.writestr('page.png', output.getvalue())
            for floating in (False, True):
                for create in (lambda: BookWindow(epub), lambda: ComicReaderWindow(ComicPages(comic))):
                    document = create(); show_document(document)
                    deadline = monotonic() + 5
                    while (getattr(getattr(document, 'reader', None), 'worker', None) is not None
                           or getattr(document, 'busy', False) or getattr(getattr(document, 'page_cache', None), 'busy', False)):
                        self.assertLess(monotonic(), deadline)
                        self.app.processEvents(); sleep(.005)
                    dock = window.documents.records[document]['dock']
                    if floating: dock.setFloating(True)
                    for _ in range(5): self.app.processEvents()
                    with patch.object(window, 'can_close', wraps=window.can_close) as close_main, \
                         patch.object(document, 'close', wraps=document.close) as native_close:
                        QTest.mouseClick(dock.tab_header.close_button, qt.Qt.MouseButton.LeftButton)
                        native_close.assert_not_called()
                        while window.documents.count:
                            self.assertLess(monotonic(), deadline)
                            self.app.processEvents(); sleep(.005)
                        for _ in range(10): self.app.processEvents()
                        close_main.assert_not_called()
                    self.assertTrue(window.dlg.isVisible())
                    self.assertFalse(window._closing)
                    self.assertEqual(quit_signal.count(), 0)
                    self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
                    self.assertFalse(isValid(document))
            # Exercise the actual native grouped-tab X too, keeping a second reader open.
            book = BookWindow(epub); show_document(book)
            reader = ComicReaderWindow(ComicPages(comic)); show_document(reader)
            deadline = monotonic() + 5
            while book.reader.worker is not None or reader.busy or reader.page_cache.busy:
                self.assertLess(monotonic(), deadline); self.app.processEvents(); sleep(.005)
            for _ in range(5): self.app.processEvents()
            workspace = window.documents.workspace
            bar = next(bar for bar in workspace.findChildren(qt.QTabBar)
                       if bar.parent() is workspace and bar.count())
            dock = window.documents.records[reader]['dock']
            index = next(i for i in range(bar.count()) if workspace._tab_dock(bar, i) is dock)
            with patch.object(window, 'can_close', wraps=window.can_close) as close_main:
                QTest.mouseClick(bar.tabButton(index, qt.QTabBar.ButtonPosition.RightSide), qt.Qt.MouseButton.LeftButton)
                for _ in range(10): self.app.processEvents()
                self.assertEqual(window.documents.count, 1)
                self.assertTrue(isValid(book))
                window.documents.records[book]['dock'].tab_header.close_button.click()
                for _ in range(10): self.app.processEvents()
                close_main.assert_not_called()
            self.assertTrue(window.dlg.isVisible())
            self.assertEqual(quit_signal.count(), 0)
