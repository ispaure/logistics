"""Check browser pagination, search and preview lifecycle with host fixtures."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from mobile.app import LogisticsMobile
from mobile.browser_ui import FileBrowser
import toga
from commonUtils.ui.native_browser import NativeBrowser


class NativeBrowserTests(unittest.TestCase):
    def test_tile_columns_follow_the_browser_pane_and_keep_the_visible_file(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from mobile_build.tests.support.app import create_app

        app = create_app(self)
        provider = LocalFiles(app.private_root)
        for index in range(48):
            (provider.root / f'{index:02}.txt').write_text('File')

        async def exercise():
            await app.show_files(location=('Local files', ''))
            browser = app.file_browser
            app.file_provider, app.file_path = provider, ''
            app.populate_file_browser(provider.list())
            browser.show_tiles()
            browser._reflow_tile_columns(400)
            self.assertEqual(browser.tile_columns, 2)
            row = 5
            anchor = browser._tile_entries[row * 2].identity
            browser._tile_scroll._impl.set_position(0, row * browser.TILE_ROW_HEIGHT)
            browser._reflow_tile_columns(475)
            self.assertEqual(browser.tile_columns, 3)
            visible_row = row * 2 // 3
            tiles = browser._tile_row_views[visible_row].children
            self.assertEqual(len(tiles), 3)
            self.assertIn(browser.entry_rows[anchor], tiles)
            await asyncio.sleep(0)
            self.assertEqual(browser.vertical_position, visible_row * browser.TILE_ROW_HEIGHT)
            browser._reflow_tile_columns(645)
            self.assertEqual(browser.tile_columns, 3)
            browser._reflow_tile_columns(280)
            self.assertEqual(browser.tile_columns, 2)
            self.assertEqual(len(browser._tile_row_views[visible_row * 3 // 2].children), 2)
            await browser.close()

        app.loop.run_until_complete(exercise())

    def test_unlocked_localcrypt_covers_display_without_reusable_thumbnail_caches(self):
        from zipfile import ZipFile
        from commonUtils.runtime.resources.local import LocalFiles
        from services.documents.mobile_reading import DocumentReadCapabilities
        from mobile_build.native_tests.tests.logisticsmobile.browser_thumbnail_checks import png
        from mobile_build.tests.support.app import create_app

        class LocalCryptFixture(LocalFiles):
            private = True
            document_capabilities = DocumentReadCapabilities(True, True, True, True)
            locked = False

            def check(self):
                if self.locked:
                    raise ValueError('Locked')

            def thumbnail(self, path, size, *, member, password, cancelled):
                self.check()
                self.assert_cover(path, member)
                return cover

        app = create_app(self)
        provider = LocalCryptFixture(app.private_root)
        provider.assert_cover = lambda path, member: self.assertEqual((path, member), ('Nested/Book.cbz', '02.png'))
        cover = png(25, (22, 88, 110))
        (provider.root / 'Nested').mkdir()
        with ZipFile(provider.root / 'Nested/Book.cbz', 'w') as archive:
            archive.writestr('00.bmp', b'An unsupported extra page')
            archive.writestr('10.png', cover)
            archive.writestr('02.png', cover)

        async def exercise():
            await app.show_files(location=('Local files', ''))
            browser = app.file_browser
            app.file_provider, app.file_path = provider, 'Nested'
            app.populate_file_browser(provider.list('Nested'))
            browser.show_tiles()
            entry, = browser.entries
            box, placeholder = browser._tile_previews[entry.identity]
            async with asyncio.timeout(5):
                while box.children[0] is placeholder:
                    await asyncio.sleep(.01)
            self.assertFalse(browser.icons)
            self.assertFalse(browser.work.decoded)
            app.show_home()
            self.assertIs(box.children[0], placeholder)
            await app.show_files()
            with patch.object(browser, '_visible_rows', return_value=(0,)):
                browser.show_list()
                row, = browser.native_list.data
                async with asyncio.timeout(5):
                    while not row.thumbnail:
                        await asyncio.sleep(.01)
                self.assertFalse(browser.icons)
                self.assertFalse(browser.work.decoded)
                app.show_home()
                self.assertFalse(row.thumbnail)
            provider.locked = True
            self.assertFalse(browser.thumbnails.can_publish())
            await browser.close()

        app.loop.run_until_complete(exercise())

    def test_automatic_image_previews_exclude_private_local_subclasses(self):
        from base64 import b64decode
        from commonUtils.runtime.resources.local import LocalFiles
        from mobile_build.tests.support.app import create_app

        class PrivateLocalFiles(LocalFiles):
            private = True

        app = create_app(self)
        root = app.private_root / 'preview-fixture'
        root.mkdir()
        data = b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII=')
        (root / 'image.png').write_bytes(data)
        app.loop.run_until_complete(app.show_files(location=('Local files', '')))
        browser = app.file_browser
        for private in (False, True):
            with self.subTest(private=private):
                provider = (PrivateLocalFiles if private else LocalFiles)(root)
                app.file_provider, app.file_path = provider, ''
                if private:
                    # CryptFiles inherits LocalFiles too. Its automatic browser
                    # presentation must never open/decrypt a private image.
                    with patch.object(provider, 'open', side_effect=AssertionError('Automatic private read')):
                        app.populate_file_browser(provider.list(), location=('Private fixture', ''))
                        self.assertFalse(browser.thumbnails.enabled)
                        self.assertFalse(browser.thumbnails.supports(browser.entries[0]))
                        browser.show_tiles()
                        app.loop.run_until_complete(browser.select(browser.entries[0]))
                        if browser.tasks:
                            app.loop.run_until_complete(asyncio.gather(*tuple(browser.tasks)))
                        self.assertFalse(browser.icons)
                        self.assertTrue(callable(browser.details))
                        # An explicit private preview still uses its own native
                        # provider API, independently of automatic folder icons.
                        from mobile.browser_preview import callbacks
                        from unittest.mock import Mock
                        provider.thumbnail = Mock(return_value=b'explicit native preview')
                        explicit_preview, _ = callbacks(provider, app.cloud_client)
                        self.assertEqual(explicit_preview(provider.entry('image.png'), (160, 160), lambda: False),
                                         b'explicit native preview')
                        provider.thumbnail.assert_called_once()
                else:
                    app.populate_file_browser(provider.list(), location=('Ordinary fixture', ''))
                    self.assertTrue(browser.thumbnails.enabled)
                    self.assertTrue(browser.thumbnails.supports(browser.entries[0]))
                    self.assertTrue(browser.native_list.observe_rows)

    def test_information_preview_reuses_thumbnail_and_rejects_late_selection(self):
        from base64 import b64decode
        from commonUtils.runtime.resources.local import LocalFiles
        from commonUtils.filesystem.image_previews import local_native_image
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            provider = LocalFiles(directory)
            data = b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII=')
            (provider.root / 'image.png').write_bytes(data)
            (provider.root / 'note.md').write_text('Note')
            browser = NativeBrowser(thumbnail=lambda row, size, cancelled:
                local_native_image(provider, row['path'], cancelled))
            async def check():
                browser.set_entries(provider, '', provider.list())
                image = next(row for row in browser.entries if row.label == 'image.png')
                await browser.select(image)
                for _ in range(100):
                    if any(isinstance(child, toga.ImageView) for child in browser.info.children):
                        break
                    await asyncio.sleep(.01)
                self.assertTrue(any(isinstance(child, toga.ImageView) for child in browser.info.children))
                note = next(row for row in browser.entries if row.label == 'note.md')
                await browser.select(note)
                await asyncio.sleep(.02)
                self.assertFalse(any(isinstance(child, toga.ImageView) for child in browser.info.children))
                with patch('commonUtils.filesystem.network.is_network_location', return_value=True), \
                        patch.object(provider, 'open', side_effect=AssertionError('Network image read')):
                    self.assertEqual(local_native_image(provider, 'image.png'), b'')
                await browser.close()
            try:
                app.loop.run_until_complete(check())
            finally:
                app.main_window.close()
                close_loop(app.loop)

    def test_scrolled_list_builds_only_the_anchored_tile_window(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from mobile_build.tests.support.app import create_app

        app = create_app(self)
        root = app.private_root / 'tile-anchor'
        root.mkdir()
        for index in range(165):
            (root / f'{index:03}.txt').write_text('File')

        async def exercise():
            await app.show_files(location=('Local files', ''))
            browser = app.file_browser
            app.file_provider, app.file_path = LocalFiles(root), ''
            app.populate_file_browser(app.file_provider.list(), location=('Ordinary fixture', ''))
            index = 151  # The second card in its tile row must survive the round trip.
            entry = browser._list_entries[index]
            browser.selected = entry.identity
            tile_extent = browser.TILE_ROW_HEIGHT * ((len(browser._list_entries) + 1) // 2)
            built = []
            build = browser._tile_card

            def detached_card(tile):
                self.assertIsNone(browser._tile_scroll.parent)
                built.append(tile.identity)
                return build(tile)

            with patch.object(browser, '_visible_rows', return_value=range(index, 165)), \
                    patch.object(type(browser._tile_scroll._impl), '__module__', 'toga_android.widgets.scrollcontainer'), \
                    patch.object(browser._tile_scroll._impl, 'get_max_vertical_position',
                                 return_value=tile_extent - 640), \
                    patch.object(browser, '_tile_card', side_effect=detached_card):
                browser.show_tiles()
                self.assertEqual(built, list(browser._tile_cards))
                self.assertIn(entry.identity, built)
                self.assertIs(browser.mounted_listing(), browser._tile_scroll)
                self.assertEqual(browser.vertical_position, (index // 2) * browser.TILE_ROW_HEIGHT)
                self.assertEqual(browser.selected, entry.identity)

            with patch.object(browser.native_list._impl, 'set_vertical_position', create=True) as scroll:
                browser.show_list()
                scroll.assert_called_once_with(index * browser.native_list.appearance.row_height)
            self.assertEqual(browser.selected, entry.identity)

            with patch.object(browser, '_visible_rows', return_value=range(6)):
                browser.show_tiles()
            self.assertEqual(browser._tile_range[0], 0)
            self.assertEqual(browser.vertical_position, 0)
            await browser.close()

        app.loop.run_until_complete(exercise())

    def test_recycled_viewport_keeps_both_decoder_slots_until_workers_return(self):
        from threading import Event
        from commonUtils.runtime.resources.local import LocalFiles
        from mobile_build.native_tests.tests.logisticsmobile.browser_thumbnail_checks import png
        from mobile_build.tests.support.app import create_app

        app = create_app(self)
        root = app.private_root / 'held-previews'
        root.mkdir()
        data = png(30, (10, 50, 100))
        for index in range(6):
            (root / f'{index}.png').write_bytes(data)
        viewport = [0, 1, 2]
        gate = Event()
        calls = []

        def load(_source, row, _size, _cancelled):
            calls.append(row['path'])
            gate.wait()
            return data

        async def wait_for(predicate):
            async with asyncio.timeout(5):
                while not predicate():
                    await asyncio.sleep(.01)

        async def exercise():
            await app.show_files(location=('Local files', ''))
            browser = app.file_browser
            app.file_provider, app.file_path = LocalFiles(root), ''
            app.populate_file_browser(app.file_provider.list(), location=('Local files', ''))
            with patch.object(type(browser.thumbnails), 'load', load), \
                    patch.object(browser, '_visible_rows', lambda: viewport):
                try:
                    await wait_for(lambda: len(calls) == 2)
                    self.assertCountEqual(calls, ['0.png', '1.png'])
                    held = tuple(browser._preview_jobs.values())
                    browser._preview_update.cancel()
                    browser._preview_update = None
                    browser._schedule_previews(1)  # The native row notification must take priority.
                    fallback = browser._preview_update
                    viewport[:] = [3, 4, 5]
                    browser._row_visible(browser.native_list.data[3])
                    self.assertTrue(fallback.cancelled())
                    self.assertLess(browser._preview_update.when(), fallback.when())
                    await wait_for(lambda: all(job.is_set() for job in held))
                    self.assertCountEqual(calls, ['0.png', '1.png'])
                    self.assertEqual(len(browser._preview_jobs), 2)
                    gate.set()
                    await wait_for(lambda: browser.native_list.data[5].thumbnail)
                    self.assertEqual({key[0].name for key in browser.icons}, {'3.png', '4.png', '5.png'})
                finally:
                    gate.set()
                    await browser.close()

        app.loop.run_until_complete(exercise())

    def test_native_search_callback_recurses_without_running_loop_context(self):
        from services.documents.locations import CollectionFiles
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            provider = CollectionFiles(Path(directory))
            (provider.root / 'nested' / 'deep').mkdir(parents=True)
            (provider.root / 'nested' / 'deep' / 'Needle.md').write_text('nested')
            browser = FileBrowser()
            try:
                browser.set_entries(provider, '', provider.list(), location=('Local files', ''))
                # Native synchronous callbacks can run between asyncio dispatches.
                browser.search.value = 'needle'
                async def finish():
                    for _ in range(100):
                        await asyncio.sleep(.01)
                        if any(entry.payload['path'].endswith('Needle.md') for entry in browser.entries):
                            return
                    self.fail('Typing in search did not discover the nested local file')
                app.loop.run_until_complete(finish())
                self.assertEqual([entry.payload['path'] for entry in browser.entries],
                                 ['nested/deep/Needle.md'])
                browser.close_search()
                app.loop.run_until_complete(asyncio.sleep(.45))
                self.assertEqual([entry.payload['path'] for entry in browser.entries], ['nested'])
            finally:
                app.loop.run_until_complete(browser.close())
                app.main_window.close()
                close_loop(app.loop)

    def test_views_pagination_info_and_stale_thumbnail(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            async def check():
                provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
                rows = [dict(path=f'{index}.txt', name=f'{index}.txt', directory=False, size=index) for index in range(30)]
                selected = []
                browser = NativeBrowser(selected=selected.append, details=lambda row, cancelled: [('Title', 'Shared provider title')])
                browser.set_entries(provider, '', rows)
                self.assertNotIn(browser.search_panel, browser.widget.children)
                browser.search_button.on_press()
                self.assertIn(browser.search_panel, browser.widget.children)
                self.assertEqual(browser.search_panel.children[0], browser.search)
                self.assertNotIn(browser.sort, browser.search_panel.children)
                browser.search.value = 'no-match'
                browser.close_search_button.on_press()
                self.assertEqual(browser.search.value, '')
                self.assertNotIn(browser.search_panel, browser.widget.children)
                self.assertEqual(len(browser.buttons), 24)
                browser.next_page()
                self.assertEqual(len(browser.buttons), 6)
                browser.show_tiles()
                self.assertEqual(len(browser.buttons), 16)
                await browser.buttons[browser.entries[0].identity].on_press()
                self.assertEqual(selected[-1]['path'], '0.txt')
                self.assertIn('Size: 0 B', [child.text for child in browser.info.children])
                self.assertIn('Title: Shared provider title', [child.text for child in browser.info.children])
                browser.icons[(Path('/virtual/0.txt'), None)] = b'outdated'
                browser.set_entries(provider, '', rows)
                self.assertEqual(browser.icons, {})
                gate = asyncio.Event()
                async def slow(entry, image, epoch, cancelled):
                    await gate.wait()
                    if epoch == browser.epoch and not cancelled.is_set():
                        browser.icons[(entry.identity, entry.revision)] = b'stale'
                browser._load_thumbnail = slow
                browser.thumbnail = lambda *args: b'fixture'
                browser.render()
                browser.stop()
                gate.set()
                await browser.close()
                self.assertFalse(browser.icons)
                self.assertFalse(browser.buttons)
                self.assertFalse(browser.tasks)
                self.assertFalse(browser.info.children)
            try:
                app.loop.run_until_complete(check())
            finally:
                app.main_window.close()
                close_loop(app.loop)
