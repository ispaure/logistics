"""Adaptive spreads, adjacent archives, boundary taps and metadata editing."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from io import BytesIO
from pathlib import Path
import time
from unittest import TestCase
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
import zipfile
from PIL import Image
from commonUtils.ui import pyside as qt
from features.comics.pages import ComicPages, load_preview
from features.comics.reading import comic_siblings, visible_pages
from features.comics.ui.reader import ComicReaderWindow, read_previous
from tests.comics.fixtures import encoded_page


class MobileSpreadTests(TestCase):
    def navigation(self, *, right_to_left=False, failed_page=None):
        from features.comics.mobile.navigation import ComicNavigation
        portrait = encoded_page('red', (80, 120))
        wide = encoded_page('blue', (160, 100))
        pages = (portrait, portrait, wide, portrait)

        def read_page(index):
            if index == failed_page:
                raise ValueError('Unreadable previous page')
            return pages[index], 'image/png'

        return ComicNavigation(read_page, len(pages), right_to_left=right_to_left)

    def test_previous_probe_preserves_pending_display_and_committed_progress(self):
        for rtl in (False, True):
            with self.subTest(right_to_left=rtl):
                nav = self.navigation(right_to_left=rtl)
                indices, _ = nav.load(3, viewport=(400, 800))
                nav.commit(indices)
                nav.requested_half = 1
                pending, _ = nav.load(2, viewport=(400, 800))

                self.assertEqual(nav.previous(2, viewport=(800, 400)), 0)
                self.assertEqual(nav.progress_label, '4 / 4')
                self.assertEqual(nav.crop, (0.0, 0.54) if rtl else (0.46, 1.0))
                nav.commit(pending)
                self.assertEqual(nav.progress_label, '3 2/2 / 4')
                self.assertEqual(nav.viewport, (400, 800))
                self.assertEqual(nav.visits.previous, [(3, 0)])

    def test_previous_probe_does_not_consume_half_request_even_on_failure(self):
        for failed_page in (None, 1):
            with self.subTest(failed_page=failed_page):
                nav = self.navigation(failed_page=failed_page)
                indices, _ = nav.load(2, viewport=(400, 800))
                nav.commit(indices)
                nav.requested_half = 1

                if failed_page is None:
                    self.assertEqual(nav.previous(2, viewport=(800, 400)), 0)
                else:
                    with self.assertRaisesRegex(ValueError, 'Unreadable previous page'):
                        nav.previous(2, viewport=(800, 400))
                self.assertEqual(nav.progress_label, '3 1/2 / 4')
                indices, _ = nav.load(2, viewport=(400, 800))
                nav.commit(indices)
                self.assertEqual(nav.progress_label, '3 2/2 / 4')

    def test_previous_target_respects_mobile_layout_and_double_pages(self):
        cases = (
            ('auto', (400, 800), (), 2, 1),
            ('auto', (800, 400), (), 2, 0),
            ('single', (800, 400), (), 2, 1),
            ('double', (400, 800), (), 2, 0),
            ('double', (800, 400), (0,), 2, 1),
            ('double', (800, 400), (1,), 2, 1),
            ('double', (800, 400), (), 3, 2),  # Wide page cannot pair.
        )
        for mode, viewport, double_pages, start, expected in cases:
            with self.subTest(mode=mode, viewport=viewport, double_pages=double_pages, start=start):
                nav = self.navigation()
                nav.double_pages = set(double_pages)
                self.assertEqual(nav.previous(start, viewport=viewport, mode=mode), expected)


class SpreadTests(QtTestCase):
    def test_desktop_pages_touch_at_the_center(self):
        from features.comics.ui.reader_pages import PageCanvas
        canvas = PageCanvas()
        canvas.resize(400, 200)
        left, right = qt.QPixmap(100, 200), qt.QPixmap(100, 200)
        left.fill(qt.QColor('red'))
        right.fill(qt.QColor('blue'))
        canvas.set_pages(((0, left), (1, right)), False)
        pixels = canvas.grab().toImage()
        self.assertEqual(pixels.pixelColor(199, 100), qt.QColor('red'))
        self.assertEqual(pixels.pixelColor(200, 100), qt.QColor('blue'))
        canvas.close()

    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = self.temporary_directory()
        self.root = Path(self.temp.name)

    def archive(self, name, colors=('red', 'green', 'blue', 'yellow', 'orange'), rtl=False,
                pages_xml='', size=(80, 120)):
        path = self.root / name
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('ComicInfo.xml', f'<ComicInfo><Manga>{"YesAndRightToLeft" if rtl else "No"}</Manga>{pages_xml}</ComicInfo>')
            for i, color in enumerate(colors):
                archive.writestr(f'{i + 1}.png', encoded_page(color, size))
        return path

    def wait(self, reader):
        self.wait_until(lambda: not (reader.busy or reader.page_cache.busy
                        or any(window.busy for window in reader.metadata_windows)),
                        timeout=8, message='Reader did not finish its background work')

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
        with patch.object(reader.page_cache, 'lookup', return_value=None), patch.object(reader_module, 'read_candidates', delayed):
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
        with patch.object(reader.page_cache, 'lookup', return_value=None), patch.object(reader_module, 'read_candidates', side_effect=ValueError('bad image')):
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

    @patch('mobile.comic_guidance.present')
    def test_natural_file_order_boundary_double_press_and_dedicated_controls(self, mobile_guidance):
        first = self.archive('comic 1.cbz', colors=('red', 'green'))
        second = self.archive('comic 2.cbz', colors=('blue',), rtl=True)
        last = self.archive('comic 10.cbz', colors=('orange',))
        self.assertEqual(comic_siblings(first), [first, second, last])
        reader = self.reader(first)
        self.assertFalse(reader.previous_file_button.isEnabled())
        self.assertTrue(reader.next_file_button.isEnabled())
        with patch('features.comics.ui.reader.time') as clock:
            clock.monotonic.side_effect = [10.0, 10.5, 10.7]
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
        mobile_guidance.assert_not_called()

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
        self.wait_until(lambda: reader.pages.right_to_left,
                        message='Reader did not reload the saved reading direction')
        self.wait(reader)
        self.assertEqual(saved, [path])
        self.assertTrue(reader.pages.right_to_left)
        self.assertTrue(reader.progress.invertedAppearance())
        self.assertEqual(reader.canvas.visual_pages, (1, 0))
        editor.reject()

    def test_preview_preserves_enough_pixels_for_retina_display(self):
        path = self.archive('retina.cbz', colors=('red',), size=(800, 1200))
        _, cover, _ = load_preview(path)
        with Image.open(BytesIO(cover)) as image:
            self.assertEqual(image.size, (800, 1200))

    def wait_cache(self, reader):
        self.wait_until(lambda: not reader.page_cache.busy)

    def test_holding_arrows_uses_steady_timer_and_stops_on_release_for_both_directions(self):
        from PySide6.QtTest import QTest
        from features.comics.ui.reader_keys import PAGE_TURN_INTERVAL_MS
        for rtl in (False, True):
            reader = self.reader(self.archive(f'held-{rtl}.cbz', colors=('red',) * 12, rtl=rtl), wide=False)
            reader.set_mode('single')
            self.wait_cache(reader)
            self.assertEqual(reader.keys.timer.interval(), PAGE_TURN_INTERVAL_MS)
            self.assertEqual(reader.keys.timer.timerType(), qt.Qt.TimerType.PreciseTimer)
            # Dispatch repeat ticks explicitly while checking OS auto-repeat.
            # Workstation load must not turn another page between assertions.
            reader.keys.timer.setInterval(60_000)
            forward = qt.Qt.Key.Key_Left if rtl else qt.Qt.Key.Key_Right
            backward = qt.Qt.Key.Key_Right if rtl else qt.Qt.Key.Key_Left
            QTest.keyPress(reader.canvas, forward)
            self.assertEqual(reader.shown_page, 1)
            self.wait(reader)
            for _ in range(10):
                self.app.sendEvent(reader.canvas, qt.QKeyEvent(qt.QEvent.Type.KeyPress, forward,
                                  qt.Qt.KeyboardModifier.NoModifier, '', True))
            self.assertEqual(reader.shown_page, 1)
            self.app.sendEvent(reader.canvas, qt.QKeyEvent(qt.QEvent.Type.KeyRelease, forward,
                              qt.Qt.KeyboardModifier.NoModifier, '', True))
            self.assertTrue(reader.keys.timer.isActive())
            reader.keys.timer.timeout.emit()
            QTest.keyRelease(reader.canvas, forward)
            self.wait(reader)
            self.assertEqual(reader.shown_page, 2)
            self.assertFalse(reader.keys.timer.isActive())
            QTest.keyPress(reader.canvas, backward)
            self.assertEqual(reader.shown_page, 1)
            reader.keys.timer.timeout.emit()
            QTest.keyRelease(reader.canvas, backward)
            self.wait(reader)
            self.assertEqual(reader.shown_page, 0)
            reader.close(); self.wait(reader)

    def test_hold_timer_dispatches_and_release_stops_ticks(self):
        from PySide6.QtTest import QTest
        from features.comics.ui.reader_keys import PAGE_TURN_INTERVAL_MS
        reader = self.reader(self.archive('timer.cbz'), wide=False)
        self.wait_cache(reader)
        ticks = []
        def release_on_tick():
            ticks.append(reader.page)
            QTest.keyRelease(reader.canvas, qt.Qt.Key.Key_Right)
        reader.keys.timer.timeout.connect(release_on_tick)
        QTest.keyPress(reader.canvas, qt.Qt.Key.Key_Right)
        try:
            self.wait_until(lambda: bool(ticks), message='Hold timer did not dispatch')
            self.wait(reader)
            self.assertEqual(ticks, [2])
            self.assertEqual(reader.shown_page, 2)
            self.assertFalse(reader.keys.timer.isActive())
            QTest.qWait(PAGE_TURN_INTERVAL_MS + 50)
            self.assertEqual(ticks, [2])
            self.assertEqual(reader.shown_page, 2)
        finally:
            QTest.keyRelease(reader.canvas, qt.Qt.Key.Key_Right)

    def test_holding_page_button_and_boundary_never_automatically_opens_next_comic(self):
        from PySide6.QtTest import QTest
        from features.comics.ui.reader_keys import PAGE_TURN_INTERVAL_MS
        path = self.archive('1-held.cbz')
        self.archive('2-held.cbz')
        reader = self.reader(path, wide=False)
        reader.set_mode('single'); self.wait_cache(reader)
        self.assertEqual(reader.keys.timer.interval(), PAGE_TURN_INTERVAL_MS)
        reader.keys.timer.setInterval(60_000)
        QTest.mousePress(reader.next_button, qt.Qt.MouseButton.LeftButton)
        self.assertEqual(reader.shown_page, 1)
        reader.keys.timer.timeout.emit()
        QTest.mouseRelease(reader.next_button, qt.Qt.MouseButton.LeftButton)
        self.wait(reader)
        self.assertEqual(reader.shown_page, 2)
        self.assertFalse(reader.keys.timer.isActive())
        reader.go(4); self.wait(reader)
        QTest.keyPress(reader.canvas, qt.Qt.Key.Key_Right)
        reader.keys.timer.timeout.emit()
        self.assertEqual(reader.pages.path, path)
        self.assertFalse(reader.keys.timer.isActive())
        QTest.keyRelease(reader.canvas, qt.Qt.Key.Key_Right)

    def test_hold_does_not_queue_or_skip_pages_when_loading_is_slow(self):
        from threading import Event
        from PySide6.QtTest import QTest
        from features.comics.ui import reader as module
        reader = self.reader(self.archive('slow.cbz'), wide=False)
        entered, release = Event(), Event()
        original = module.read_candidates
        def delayed(pages, index):
            entered.set()
            if not release.wait(5):
                raise TimeoutError('Test did not release the page load')
            return original(pages, index)
        with patch.object(reader.page_cache, 'lookup', return_value=None), patch.object(module, 'read_candidates', delayed):
            try:
                reader.keys.timer.setInterval(60_000)
                QTest.keyPress(reader.canvas, qt.Qt.Key.Key_Right)
                self.wait_until(entered.is_set, message='Slow page load did not start')
                for _ in range(4):
                    reader.keys.timer.timeout.emit()
                self.assertTrue(reader.busy)
                self.assertEqual(reader.shown_page, 0)
                self.assertEqual(reader.page, 1)
                self.assertIsNone(reader.pending_page)
                QTest.keyRelease(reader.canvas, qt.Qt.Key.Key_Right)
            finally:
                QTest.keyRelease(reader.canvas, qt.Qt.Key.Key_Right)
                release.set()
                self.wait(reader)
        self.assertEqual(reader.shown_page, 1)

    def test_preloaded_pages_turn_without_archive_reads_and_reset_for_new_file(self):
        from features.comics.ui import reader_cache, reader_pages
        first = self.archive('1-cache.cbz', colors=('red',) * 12)
        second = self.archive('2-cache.cbz', colors=('blue',) * 12)
        reader = self.reader(first, wide=False)
        reader.set_mode('single'); self.wait_cache(reader)
        self.assertTrue({0, 1, 2, 3}.issubset(reader.page_cache.images))
        with patch.object(reader_pages, 'read_image', side_effect=AssertionError('Cached pages should not decode')):
            reader.step(1)
            self.assertFalse(reader.busy)
            self.assertEqual(reader.shown_page, 1)
            reader.step(-1)
            self.assertFalse(reader.busy)
            self.assertEqual(reader.shown_page, 0)
        reader.go(6); self.wait(reader); self.wait_cache(reader)
        self.assertTrue({3, 4, 5, 6, 7, 8, 9}.issubset(reader.page_cache.images))
        self.assertLessEqual(len(reader.page_cache.images), reader_cache.CACHE_PAGES)
        reader.next_file_button.click(); self.wait(reader); self.wait_cache(reader)
        self.assertEqual(reader.pages.path, second)
        self.assertEqual(reader.page_cache.images[0].pixelColor(0, 0), qt.QColor('blue'))

    def test_hold_stops_on_window_deactivation_and_empty_status_bar_is_hidden(self):
        from PySide6.QtTest import QTest
        reader = self.reader(self.archive('focus.cbz'), wide=False)
        self.assertTrue(reader.statusBar().isHidden())
        QTest.keyPress(reader.canvas, qt.Qt.Key.Key_Right)
        self.app.sendEvent(reader, qt.QEvent(qt.QEvent.Type.WindowDeactivate))
        self.assertFalse(reader.keys.timer.isActive())
        reader.statusBar().showMessage('A page could not be read')
        self.assertFalse(reader.statusBar().isHidden())
        reader.statusBar().clearMessage()
        self.assertTrue(reader.statusBar().isHidden())
        self.assertEqual(reader.controls.layout().contentsMargins().bottom(), 3)

    def test_preload_memory_budget_keeps_nearest_pages_without_reloading_evictions(self):
        from features.comics.ui import reader_cache
        reader = self.reader(self.archive('budget.cbz', colors=('orange',) * 12), wide=False)
        self.wait_cache(reader)
        cache = reader.page_cache
        image_bytes = reader.images[0].sizeInBytes()
        cache.set_pages(reader.pages)
        with patch.object(reader_cache, 'CACHE_BYTES', image_bytes * 2), patch.object(
                reader_cache, 'read_image', wraps=reader_cache.read_image) as decode:
            cache.update(reader.images, reader.shown_page, reader.displayed_pages[-1])
            self.wait_cache(reader)
            self.assertEqual(set(cache.images), {0, 1})
            self.assertLessEqual(sum(image.sizeInBytes() for image in cache.images.values()), image_bytes * 2)
            self.assertLessEqual(decode.call_count, 3)
            self.assertFalse(cache.busy)

    def test_close_waits_for_inflight_preload_and_discards_its_result(self):
        from threading import Event
        from shiboken6 import isValid
        from features.comics.ui import reader_cache
        reader = self.reader(self.archive('closing.cbz'), wide=False)
        self.wait_cache(reader)
        cache = reader.page_cache
        cache.set_pages(reader.pages)
        entered, release = Event(), Event()
        original = reader_cache.read_image
        def delayed(pages, index):
            entered.set(); release.wait(5)
            return original(pages, index)
        with patch.object(reader_cache, 'read_image', delayed):
            cache.update(reader.images, reader.shown_page, reader.displayed_pages[-1])
            deadline = time.monotonic() + 5
            while not entered.is_set():
                self.assertLess(time.monotonic(), deadline)
                self.app.processEvents(); time.sleep(.005)
            reader.close()
            self.assertTrue(reader.closing)
            self.assertTrue(cache.busy)
            self.assertTrue(reader.isHidden())
            release.set()
            while isValid(reader) and cache.busy:
                self.assertLess(time.monotonic(), deadline)
                self.app.processEvents(); time.sleep(.005)
            self.app.processEvents()
            self.assertEqual(cache.images, {})
