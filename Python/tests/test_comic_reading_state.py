"""Comic resume state survives reader lifetime and failed navigation."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import time
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import zipfile

from PIL import Image
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.comics.pages import ComicPages
from features.comics.reading_state import ReadingState
from features.comics.ui.reader import ComicReaderWindow


class ComicResumeTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'state'
        self.path = self.root / 'a.cbz'
        image = BytesIO()
        Image.new('RGB', (100, 150), 'orange').save(image, format='PNG')
        for name in ('a.cbz', 'b.cbz'):
            with zipfile.ZipFile(self.root / name, 'w') as archive:
                for number in range(4):
                    archive.writestr(f'{number}.png', image.getvalue())

    def wait(self, reader):
        deadline = time.monotonic() + 5
        while (reader.busy or reader.page_cache.busy) and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.app.processEvents()
        self.assertFalse(reader.busy or reader.page_cache.busy)

    def reader(self):
        reader = ComicReaderWindow(ComicPages(self.path), state_folder=self.folder)
        self.wait(reader)
        return reader

    def test_close_and_reopen_and_file_menu_restore_independent_positions(self):
        reader = self.reader()
        reader.go(2)
        self.wait(reader)
        reader._request_file(self.path)
        self.wait(reader)
        self.assertEqual(reader.shown_page, 2)
        reader.close()
        self.app.processEvents()
        reader = self.reader()
        self.assertEqual(reader.shown_page, 2)
        reader._request_file(self.root / 'b.cbz')
        self.wait(reader)
        self.assertEqual(reader.shown_page, 0)
        reader.go(1)
        self.wait(reader)
        reader._request_file(self.path)
        self.wait(reader)
        self.assertEqual(reader.shown_page, 2)
        reader._request_file(self.root / 'b.cbz')
        self.wait(reader)
        self.assertEqual(reader.shown_page, 1)
        reader.open_adjacent(-1)
        self.wait(reader)
        self.assertEqual(reader.shown_page, 3)
        reader.open_adjacent(1)
        self.wait(reader)
        self.assertEqual(reader.shown_page, 0)
        reader.close()

    def test_failed_page_and_failed_file_do_not_replace_successful_position(self):
        reader = self.reader()
        reader.go(1)
        self.wait(reader)
        reader.page = 3
        reader._loaded(reader.pages, 3, {}, 'decode failed')
        reader._request_file(self.root / 'missing.cbz')
        self.wait(reader)
        reader.close()
        state = ReadingState(self.path, folder=self.folder)
        self.assertEqual(state.position(ComicPages(self.path).pages), 1)

    def test_shutdown_flushes_and_disabled_setting_preserves_history(self):
        reader = self.reader()
        reader.go(2)
        self.wait(reader)
        reader.shutdown()
        reader.close()
        state = ReadingState(self.path, folder=self.folder)
        before = state.path.read_bytes()
        with patch('features.comics.ui.reader.remember_position', return_value=False):
            reader = self.reader()
        self.assertEqual(reader.shown_page, 0)
        reader.go(1)
        self.wait(reader)
        reader.close()
        self.assertEqual(state.path.read_bytes(), before)

    def test_invalid_state_identity_and_changed_page_lists(self):
        pages = ComicPages(self.path).pages
        state = ReadingState(self.path, folder=self.folder)
        self.assertEqual(state.position(pages), 0)
        state.save(2, pages)
        link = self.root / 'alias.cbz'
        link.symlink_to(self.path)
        self.assertEqual(ReadingState(link, folder=self.folder).path, state.path)
        self.assertEqual(state.position(['new.png', *pages]), 3)
        self.assertEqual(state.position(['only.png']), 0)
        for data in ('{', '[]', '{"page": true}', '{"page": "2"}', '{"page": -7}',
                     json.dumps({'page': 0, 'name': []})):
            state.path.write_text(data)
            self.assertEqual(state.position(pages), 0)
        state.path.write_text('{"page": 99}')
        self.assertEqual(state.position(pages), 3)

    def test_thumbnail_progress_tracks_resume_page_and_legacy_state(self):
        from features.comics.cbz import CBZFile
        with patch('features.comics.reading_state.cache_directory', return_value=self.root / 'cache'):
            state = ReadingState(self.path)
            item = CBZFile(self.path)
            self.assertEqual(item.browser_thumbnail_badge(), '')
            state.path.parent.mkdir(parents=True)
            state.path.write_text('{"page":2,"name":"2.png"}')
            item.browser_thumbnail((100, 140))
            self.assertEqual(item.browser_thumbnail_badge(), '3/4')
            state.save(1, ComicPages(self.path).pages)
            self.assertEqual(item.browser_thumbnail_badge(), '2/4')
            self.assertEqual(state.badge(), '2/4')
            state.path.write_text('{"page":true,"total":4}')
            self.assertEqual(state.badge(), '')
            state.path.write_text('broken')
            self.assertEqual(item.browser_thumbnail_badge(), '')
