"""Comic resume state survives reader lifetime and failed navigation."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import zipfile

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.comics.pages import ComicPages
from features.comics.reading_state import ReadingState, open_comic_progress
from features.comics.ui.reader import ComicReaderWindow
from tests.comics.fixtures import encoded_page


class ComicResumeTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = self.temporary_directory()
        self.root = Path(self.temp.name)
        self.folder = self.root / 'state'
        self.path = self.root / 'a.cbz'
        for name in ('a.cbz', 'b.cbz'):
            with zipfile.ZipFile(self.root / name, 'w') as archive:
                for number in range(4):
                    archive.writestr(f'{number}.png', encoded_page(size=(100, 150)))

    def wait(self, reader):
        self.wait_until(lambda: not (reader.busy or reader.page_cache.busy))

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
        progress, index = open_comic_progress(ComicPages(self.path), self.folder)
        self.addCleanup(progress.retire)
        self.assertEqual(index, 1)

    def test_shutdown_flushes_and_disabled_setting_preserves_history(self):
        reader = self.reader()
        reader.go(2)
        self.wait(reader)
        reader.shutdown()
        reader.close()
        progress, index = open_comic_progress(ComicPages(self.path), self.folder)
        self.assertEqual(index, 2)
        before = progress.load()
        progress.retire()
        with patch('features.comics.ui.reader.remember_position', return_value=False):
            reader = self.reader()
        self.assertEqual(reader.shown_page, 0)
        reader.go(1)
        self.wait(reader)
        reader.close()
        progress, index = open_comic_progress(ComicPages(self.path), self.folder)
        self.addCleanup(progress.retire)
        self.assertEqual(index, 2)
        self.assertEqual(progress.load(), before)

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

    def test_oversized_page_identity_preserves_the_last_readable_state(self):
        state = ReadingState(self.path, folder=self.folder)
        pages = ['0.png', '1.png']
        state.save(1, pages)
        before = state.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            state.save(0, ['😀' * (32 * 1024)])
        self.assertEqual(state.path.read_bytes(), before)
        self.assertEqual(state.position(pages), 1)

    def test_resume_and_badge_enforce_limit_with_stale_size_metadata(self):
        from types import SimpleNamespace
        state = ReadingState(self.path, folder=self.folder)
        state.path.parent.mkdir()
        pages = ['0.png', '1.png', '2.png']
        state.path.write_text(json.dumps({'page': 2, 'name': '2.png', 'total': 3,
                                         'padding': 'x' * (128 * 1024)}))
        before = state.path.read_bytes()
        original_stat = Path.stat

        def stale_stat(path, *args, **kwargs):
            if path == state.path:
                return SimpleNamespace(st_size=0)
            return original_stat(path, *args, **kwargs)

        with patch.object(Path, 'stat', stale_stat):
            self.assertEqual(state.position(pages), 0)
            self.assertEqual(state.badge(pages), '')
            self.assertEqual(state.badge(), '')
        self.assertEqual(state.path.read_bytes(), before)

    def test_badge_uses_one_snapshot_when_another_reader_saves(self):
        state = ReadingState(self.path, folder=self.folder)
        pages = ['0.png', '1.png', '2.png', '3.png']
        state.save(1, pages)
        original_open = Path.open
        reads = []
        @contextmanager
        def open_and_update(path, *args, **kwargs):
            with original_open(path, *args, **kwargs) as stream:
                yield stream
            if path == state.path:
                reads.append(path)
                if len(reads) == 1:
                    state.save(3, pages)
        with patch.object(Path, 'open', open_and_update):
            self.assertEqual(state.badge(pages), '2/4')
        self.assertEqual(len(reads), 1)
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
