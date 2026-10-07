"""Adaptive spreads, adjacent archives, boundary taps and metadata editing."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
import zipfile
from PIL import Image
from commonUtils.ui import pyside as qt
from features.comics.pages import ComicPages, load_preview
from features.comics.reading import comic_siblings, visible_pages
from features.comics.ui.reader import ComicReaderWindow, read_previous


class SpreadTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, name, colors=('red', 'green', 'blue', 'yellow', 'orange'), rtl=False, pages_xml=''):
        path = self.root / name
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('ComicInfo.xml', f'<ComicInfo><Manga>{"YesAndRightToLeft" if rtl else "No"}</Manga>{pages_xml}</ComicInfo>')
            for i, color in enumerate(colors):
                image = Image.new('RGB', (800, 1200), color)
                stream = BytesIO()
                image.save(stream, format='PNG')
                archive.writestr(f'{i + 1}.png', stream.getvalue())
        return path

    def wait(self, reader):
        deadline = time.monotonic() + 8
        quiet_since = None
        while time.monotonic() < deadline:
            self.app.processEvents()
            if reader.busy or any(window.busy for window in reader.metadata_windows):
                quiet_since = None
            elif quiet_since is None:
                quiet_since = time.monotonic()
            elif time.monotonic() - quiet_since >= .1:
                return
            time.sleep(.01)
        self.fail('Reader did not finish its background work')

    def reader(self, path, wide=True):
        reader = ComicReaderWindow(ComicPages(path))
        reader.resize(1500 if wide else 750, 900)
        reader.show()
        reader.activateWindow()
        self.wait(reader)
        from shiboken6 import isValid
        def cleanup():
            if isValid(reader):
                reader.close()
                self.wait(reader)
                self.app.processEvents()
        self.addCleanup(cleanup)
        return reader

    def test_auto_spreads_resize_order_progress_and_sequential_navigation(self):
        for rtl in (False, True):
            reader = self.reader(self.archive(f'{rtl}.cbz', rtl=rtl))
            self.assertEqual(reader.displayed_pages, (0, 1))
            self.assertEqual(reader.canvas.visual_pages, (1, 0) if rtl else (0, 1))
            self.assertIn('1 & 2 / 5', reader.progress_label.text())
            self.assertEqual(reader.progress.value(), 0)
            reader.step(1); self.wait(reader)
            self.assertEqual(reader.displayed_pages, (2, 3))
            reader.step(1); self.wait(reader)
            self.assertEqual(reader.displayed_pages, (4,))
            self.assertEqual(reader.progress.value(), 4)
            self.assertIn('100%', reader.progress_label.text())
            reader.step(-1); self.wait(reader)
            self.assertEqual(reader.displayed_pages, (2, 3))
            reader.resize(750, 900)
            self.app.processEvents()
            self.assertEqual(reader.displayed_pages, (2,))
            reader.step(-1); self.wait(reader)
            self.assertEqual(reader.page, 1)
            reader.resize(1500, 900)
            self.app.processEvents()
            self.assertEqual(reader.displayed_pages, (1, 2))
            self.assertEqual(reader.canvas.visual_pages, (2, 1) if rtl else (1, 2))
            reader.close(); self.app.processEvents()

    def test_navigation_keys_work_without_slider_focus(self):
        from PySide6.QtTest import QTest
        reader = self.reader(self.archive('keys.cbz'), wide=False)
        for widget in (reader, reader.canvas, reader.previous_button, reader.next_button, reader.progress):
            reader.go(0)
            self.wait(reader)
            widget.setFocus()
            QTest.keyClick(widget, qt.Qt.Key.Key_Right)
            self.wait(reader)
            self.assertEqual(reader.shown_page, 1)
        editor = reader.edit_metadata()
        self.wait(reader)
        before = reader.shown_page
        field = editor.editors['Series']
        field.setFocus()
        QTest.keyClick(field, qt.Qt.Key.Key_Right)
        self.wait(reader)
        self.assertEqual(reader.shown_page, before)
        editor.reject()

    def test_current_spread_stays_visible_during_load_resize_and_failure(self):
        from threading import Event
        from features.comics.ui import reader as reader_module
        reader = self.reader(self.archive('loading.cbz'))
        before = reader.canvas.visual_pages
        old_image = reader.canvas.pixmap.cacheKey()
        old_label = reader.progress_label.text()
        released = Event()
        original = reader_module.read_candidates
        def delayed(pages, index):
            released.wait(5)
            return original(pages, index)
        with patch.object(reader_module, 'read_candidates', delayed):
            reader.step(1)
            self.app.processEvents()
            self.assertTrue(reader.busy)
            self.assertEqual(reader.canvas.visual_pages, before)
            self.assertEqual(reader.canvas.pixmap.cacheKey(), old_image)
            self.assertEqual(reader.progress_label.text(), old_label)
            reader.resize(750, 900)
            self.app.processEvents()
            self.assertEqual(reader.canvas.visual_pages, (0,))
            released.set()
            self.wait(reader)
        self.assertEqual(reader.shown_page, 2)
        before = reader.canvas.visual_pages
        with patch.object(reader_module, 'read_candidates', side_effect=ValueError('bad image')):
            reader.go(3)
            self.wait(reader)
        self.assertEqual(reader.canvas.visual_pages, before)
        self.assertEqual(reader.page, reader.shown_page)
        self.assertIn('bad image', reader.statusBar().currentMessage())
        self.assertIn('bad image', reader.canvas.toolTip())
        reader.go(3)
        self.wait(reader)
        self.assertEqual(reader.shown_page, 3)
        self.assertEqual(reader.statusBar().currentMessage(), '')
        self.assertEqual(reader.canvas.toolTip(), '')

    def test_landscape_and_metadata_double_pages_remain_single(self):
        self.assertEqual(visible_pages(0, {0: (1600, 1000), 1: (800, 1200)}, (2000, 800)), (0,))
        self.assertEqual(visible_pages(0, {0: (800, 1200), 1: (1600, 1000)}, (2000, 800)), (0,))
        path = self.archive('marked.cbz', pages_xml='<Pages><Page Image="0" DoublePage="true" /></Pages>')
        self.assertEqual(ComicPages(path).double_pages, {0})
        reader = self.reader(path)
        reader.set_mode('single')
        self.assertTrue(reader.menus.mode_actions['single'].isChecked())
        reader.set_mode('auto')
        self.assertTrue(reader.menus.mode_actions['auto'].isChecked())
        self.assertEqual(reader.displayed_pages, (0,))
        reader.step(1); self.wait(reader)
        self.assertEqual(reader.displayed_pages, (1, 2))
        reader.step(-1); self.wait(reader)
        self.assertEqual(reader.displayed_pages, (0,))

    def test_natural_file_order_boundary_double_press_and_dedicated_controls(self):
        first = self.archive('comic 1.cbz', colors=('red', 'green'))
        second = self.archive('comic 2.cbz', colors=('blue',), rtl=True)
        last = self.archive('comic 10.cbz', colors=('orange',))
        self.assertEqual(comic_siblings(first), [first, second, last])
        reader = self.reader(first)
        self.assertFalse(reader.previous_file_button.isEnabled())
        self.assertTrue(reader.next_file_button.isEnabled())
        with patch('features.comics.ui.reader.time.monotonic', side_effect=[10.0, 10.5, 10.7]):
            reader.step(1)
            self.assertEqual(reader.pages.path, first)
            reader.step(1)
            self.assertEqual(reader.pages.path, first)
            reader.step(1)
        self.wait(reader)
        self.assertEqual(reader.pages.path, second)
        self.assertEqual(reader.page, 0)
        self.assertTrue(reader.progress.invertedAppearance())
        reader.next_file_button.click(); self.wait(reader)
        self.assertEqual(reader.pages.path, last)
        self.assertFalse(reader.next_file_button.isEnabled())
        reader.previous_file_button.click(); self.wait(reader)
        self.assertEqual(reader.pages.path, second)
        reader.previous_file_button.click(); self.wait(reader)
        self.assertEqual(reader.pages.path, first)
        self.assertEqual(reader.page, 1)

    def test_previous_after_seek_uses_actual_page_shapes(self):
        from types import SimpleNamespace
        pages = SimpleNamespace(double_pages=set(), pages=range(5))
        portrait = qt.QImage(800, 1200, qt.QImage.Format.Format_RGB32)
        landscape = qt.QImage(1600, 1000, qt.QImage.Format.Format_RGB32)
        images = {0: portrait, 1: portrait, 2: landscape, 3: portrait, 4: portrait}
        with patch('features.comics.ui.reader_pages.read_image', side_effect=lambda pages, index: images[index]):
            start, _ = read_previous(pages, 3, (1500, 900), 'auto')
            self.assertEqual(start, 3)
            start, _ = read_previous(pages, 2, (1500, 900), 'auto')
            self.assertEqual(start, 2)
            start, _ = read_previous(pages, 1, (1500, 900), 'auto')
            self.assertEqual(start, 0)

    def test_corrupt_adjacent_file_leaves_current_comic_open(self):
        first = self.archive('1.cbz')
        (self.root / '2.cbz').write_bytes(b'bad archive')
        reader = self.reader(first)
        reader.next_file_button.click(); self.wait(reader)
        self.assertEqual(reader.pages.path, first)
        self.assertIn('Cannot open comic', reader.statusBar().currentMessage())
        self.assertFalse(reader.file_loading)

    def test_reader_edit_metadata_saves_and_refreshes_reading_direction(self):
        path = self.archive('1.cbz')
        reader = self.reader(path)
        saved = []
        reader.metadata_saved.connect(saved.append)
        editor = reader.edit_metadata()
        self.wait(reader)
        self.assertEqual(editor.targets, (path,))
        self.assertIs(reader.edit_metadata(), editor)
        manga = editor.editors['Manga']
        manga.setCurrentIndex(manga.findData('YesAndRightToLeft'))
        editor._save()
        self.wait(reader)
        self.assertEqual(saved, [path])
        self.assertTrue(reader.pages.right_to_left)
        self.assertTrue(reader.progress.invertedAppearance())
        self.assertEqual(reader.canvas.visual_pages, (1, 0))
        editor.reject()

    def test_preview_preserves_enough_pixels_for_retina_display(self):
        path = self.archive('retina.cbz')
        _, cover, _ = load_preview(path)
        with Image.open(BytesIO(cover)) as image:
            self.assertEqual(image.size, (800, 1200))
