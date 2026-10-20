"""Native widget contracts for feature-owned reader navigation and metadata."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from logisticsmobile.app import LogisticsMobile
from services.documents.readers import PrivateReader
from commonUtils.runtime.document_access import LocalDocuments
from Mobile.native_tests.tests.logisticsmobile.fixtures import make_books


class ReaderParityUITests(unittest.TestCase):
    def host(self, root):
        LogisticsMobile.storage_root = root
        self.addCleanup(setattr, LogisticsMobile, "storage_root", None)
        app = LogisticsMobile("Logistics", "io.github.ispaure.logisticsmobile")
        self.addCleanup(app.loop.close)
        self.addCleanup(app.main_window.close)
        return app

    def test_auto_spread_uses_metadata_for_page_order_and_swipe_direction(self):
        from io import BytesIO
        from PIL import Image
        for rtl in (False, True):
            with self.subTest(right_to_left=rtl), TemporaryDirectory() as directory:
                root = Path(directory)
                app = self.host(root)
                self.assertEqual(app.preferences.values['comic_layout'], 'auto')
                source = root / 'order.cbz'
                with ZipFile(source, 'w') as archive:
                    for index, color in enumerate(('red', 'blue', 'green', 'yellow')):
                        data = BytesIO()
                        Image.new('RGBA', (90, 100), color).save(data, format='PNG')
                        archive.writestr(f'page{index}.png', data.getvalue())
                    archive.writestr('ComicInfo.xml', '<ComicInfo><Manga>' + ('YesAndRightToLeft' if rtl else 'No') + '</Manga></ComicInfo>')
                record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), source)
                async def exercise():
                    with patch('logisticsmobile.reader_ui.ReaderUI.comic_viewport', return_value=(1100, 1000)):
                        await app.open_book(record['id'])
                        owner = app.readers.active
                        self.assertEqual(owner.book_reader.right_to_left, rtl)
                        self.assertEqual(owner.comic_navigation.visible, (0, 1))
                        self.assertTrue(owner.book_content.children[0].magnifier_enabled)
                        owner.set_reading_mode(False)
                        self.assertFalse(owner.book_content.children[0].magnifier_enabled)
                        footer = owner.page_footer
                        self.assertEqual(list(footer.widget.children),
                            [owner.next_page if rtl else owner.previous_page, footer.slider,
                             owner.previous_page if rtl else owner.next_page])
                        self.assertEqual(owner.next_page.control_icon, 'back' if rtl else 'forward')
                        self.assertEqual(owner.previous_page.control_icon, 'forward' if rtl else 'back')
                        self.assertFalse(owner.previous_page.enabled)
                        self.assertEqual(footer.slider.value, 3 if rtl else 0)
                        pixels = owner.book_content.children[0].canvas.image._impl.native.raw
                        self.assertEqual(pixels.getpixel((20, 20)), (0, 0, 255, 255) if rtl else (255, 0, 0, 255))
                        owner.swipe_book_page(-1 if rtl else 1)
                        await owner._comic_swipe_task
                        self.assertEqual(owner.comic_navigation.visible, (2, 3))
                        await owner.previous_book_page()
                        self.assertEqual(owner.comic_navigation.visible, (0, 1))
                        footer.slider.value = 0 if rtl else 3
                        self.assertEqual(owner.comic_navigation.visible, (0, 1))
                        await footer.release(footer.slider)
                        self.assertEqual(owner.book_record['position'], 3)
                        self.assertFalse(owner.next_page.enabled)
                        footer.slider.value = 3 if rtl else 0
                        await footer.release(footer.slider)
                        self.assertEqual(owner.book_record['position'], 0)
                        private = PrivateReader('Private.cbz', source.read_bytes())
                        app.show_cloud()
                        with patch.object(app.crypt_copies, 'open', return_value=private):
                            await app.open_crypt(copies=app.crypt_copies, key='c' * 32)
                        provider = app.private_sessions.active
                        self.assertTrue(provider.provider_spread.magnifier_enabled)
                        provider.toggle_private_reading_mode()
                        self.assertFalse(provider.provider_spread.magnifier_enabled)
                        footer = provider.page_footer
                        self.assertEqual(provider.next_page.control_icon, 'back' if rtl else 'forward')
                        self.assertIs(footer.widget.children[0], provider.next_page if rtl else provider.previous_page)
                        footer.slider.value = 0 if rtl else 3
                        await footer.release(footer.slider)
                        self.assertEqual(provider.crypt_page.value, private.labels[3])
                        self.assertFalse(provider.next_page.enabled)
                        self.assertFalse(provider.provider_spread.magnifier_enabled)
                        provider.toggle_private_reading_mode()
                        self.assertTrue(provider.provider_spread.magnifier_enabled)
                        app.private_sessions.close(provider.session.id, discard=True)
                app.loop.run_until_complete(exercise())

    def test_epub_navigation_search_precise_bookmark_resume_and_stale_callback(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = self.host(root)
            app.show_library()
            fixtures = root / "fixtures"
            fixtures.mkdir()
            epub, _ = make_books(fixtures)
            record = app.reader_manager().catalog.library_store.import_book(
                LocalDocuments(), epub
            )

            async def exercise():
                await app.open_book(record["id"])
                owner = app.readers.active
                from test_markdown_speech import Engine
                speaker = next(button for button in owner.reader_header.children
                    if getattr(button, 'control_icon', None) == 'speaker')
                with patch('features.books.mobile.speech_view.NativeSpeech', Engine):
                    speaker.on_press()
                    await owner.speech_panel.ready_task
                    self.assertTrue(owner.speech_panel.play_button.enabled)
                    owner.close_read_aloud()
                bridge = owner.epub_view._chapter_bridge
                self.assertFalse(bridge.navigation(None, "https://example.invalid/"))
                bridge.navigation(None, bridge.root + "position?offset=7")
                await owner._epub_location_task
                self.assertEqual(owner.book_record["location"]["offset"], 7)
                await owner.toggle_bookmark()
                self.assertIn(
                    dict(path=owner.book_reader.spine[0], offset=7),
                    owner.book_record["epub_bookmarks"],
                )
                owner.show_epub_search()
                owner.epub_query.value = "chapter"
                await owner.find_epub_next()
                if getattr(owner, "_epub_location_task", None):
                    await owner._epub_location_task
                expected = owner.epub_offset
                owner.release_book_reader()
                await owner.open_book(record["id"])
                self.assertEqual(owner.epub_offset, expected)
                bridge.navigation(None, bridge.root + "position?offset=99")
                self.assertEqual(owner.epub_offset, expected)
                owner.show_book_metadata()
                owner.book_metadata_fields["title"].value = "Updated mobile title"
                await owner.save_book_metadata()
                await app.readers.catalog.wait_for_refresh()
                self.assertEqual(
                    owner.book_reader.title,
                    "Updated mobile title",
                    owner.book_metadata_status.text,
                )

            app.loop.run_until_complete(exercise())

    def test_provider_epub_passage_search_bookmarks_and_close_cleanup(self):
        import toga
        class MemoryWebView(toga.WebView):
            def clear_private_content(self):
                self.set_content('about:blank', '')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = self.host(root)
            fixtures = root / "fixtures"
            fixtures.mkdir()
            epub, _ = make_books(fixtures)
            app.show_cloud()
            private = PrivateReader("Private.epub", epub.read_bytes())

            async def exercise():
                with patch.object(app.crypt_copies, "open", return_value=private), patch(
                    'features.books.mobile.provider_reader.private_webview_supported', return_value=True
                ), patch('features.books.mobile.provider_reader.PrivateWebView', MemoryWebView):
                    self.assertTrue(
                        await app.open_crypt(copies=app.crypt_copies, key="a" * 32),
                        app.cloud_status.value,
                    )
                owner = app.private_sessions.active
                panel = owner.provider_epub_view
                from test_markdown_speech import Engine
                speaker = next(button for button in owner.reader_toolbar.children
                    if getattr(button, 'control_icon', None) == 'speaker')
                with patch('features.books.mobile.speech_view.NativeSpeech', Engine):
                    speaker.on_press()
                    await panel.speech_panel.ready_task
                    self.assertTrue(panel.speech_panel.play_button.enabled)
                    panel.close_read_aloud()
                panel.query.value = "chapter"
                panel.find()
                panel.seek(7)
                owner.show_provider_layout()
                self.assertFalse(hasattr(owner, "provider_epub_view"))
                owner.provider_font.value = "24"
                await owner.apply_provider_layout()
                panel = owner.provider_epub_view
                await __import__("asyncio").sleep(0)
                self.assertIs(owner.provider_epub_view, panel)
                self.assertEqual(panel.offset, 7)
                self.assertFalse(owner.page_suspended)
                owner.toggle_private_bookmark()
                self.assertEqual(len(owner.epub_session_bookmarks), 1)
                self.assertTrue(owner._provider_epub_locations)
                self.assertTrue(
                    app.private_sessions.close(owner.session.id, discard=True)
                )
                self.assertEqual(panel.text.value, "")
                self.assertEqual(owner.epub_session_bookmarks, set())
                self.assertEqual(owner._provider_epub_locations, {})
                self.assertIsNone(panel.book)

            app.loop.run_until_complete(exercise())

    def test_imported_spreads_advance_backward_and_keep_page_on_failed_load(self):
        import struct
        import zlib

        def chunk(kind, data):
            return (
                struct.pack(">I", len(data))
                + kind
                + data
                + struct.pack(">I", zlib.crc32(kind + data))
            )

        data = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 100, 200, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\x00" + b"\xff\x00\x00\xff" * 100) * 200))
            + chunk(b"IEND", b"")
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = self.host(root)
            app.preferences.save(comic_layout="double")
            source = root / "comic.cbz"
            with ZipFile(source, "w") as archive:
                for number in range(4):
                    archive.writestr(f"page{number}.png", data)
                archive.writestr(
                    "ComicInfo.xml",
                    "<ComicInfo><Manga>YesAndRightToLeft</Manga></ComicInfo>",
                )
            record = app.reader_manager().catalog.library_store.import_book(
                LocalDocuments(), source
            )

            async def exercise():
                await app.open_book(record["id"])
                owner = app.readers.active
                self.assertEqual(
                    owner.comic_navigation.visible, (0, 1), owner.book_status.text
                )
                self.assertEqual(len(owner.book_content.children[0].canvases), 1)
                await owner.next_book_page()
                self.assertEqual(owner.book_record["position"], 2)
                self.assertFalse(owner.next_page.enabled)
                await owner.previous_book_page()
                self.assertEqual(owner.book_record["position"], 0)
                before = owner.book_content.children[0]
                with patch.object(
                    owner.book_reader,
                    "read_page",
                    side_effect=ValueError("broken second page"),
                ):
                    # Navigation owns the original bound read method; replace it explicitly.
                    with patch.object(
                        owner.comic_navigation,
                        "read_page",
                        side_effect=ValueError("broken page"),
                    ):
                        await owner.next_book_page()
                self.assertIs(owner.book_content.children[0], before)
                self.assertEqual(owner.book_record["position"], 0)

            app.loop.run_until_complete(exercise())


class ReaderBridgeLifecycleTests(unittest.TestCase):
    def test_trusted_marker_and_disposed_bridge_ignore_late_native_events(self):
        from features.books.mobile.presentation import chapter_view

        class View:
            def __init__(self):
                self.scripts = []

            def set_content(self, root, content):
                self.root, self.content = root, content

            def evaluate_javascript(self, script):
                self.scripts.append(script)

        view = View()
        events = []
        chapter_view(
            "<html><head></head><body>Passage</body></html>",
            view,
            on_event=lambda *event: events.append(event),
        )
        bridge = view._chapter_bridge
        self.assertIn(
            'name="logistics-reader-root" content="' + bridge.root, view.content
        )
        bridge.loaded(view)
        self.assertIn("marker.content !== options.root", view.scripts[-1])
        self.assertNotIn("document.baseURI", view.scripts[-1])
        bridge.dispose()
        scripts = list(view.scripts)
        bridge.loaded(view)
        bridge.seek(9)
        self.assertFalse(bridge.turn(1))
        bridge.navigation(view, bridge.root + "position?offset=9")
        self.assertEqual(view.scripts, scripts)
        self.assertEqual(events, [])

    def test_private_html_size_limit_rejects_before_toolkit_or_disk_fallback(self):
        from features.books.mobile.private_view import PrivateWebView, MAX_HTML
        from types import SimpleNamespace

        view = SimpleNamespace(private_closed=False, private_configured=True)
        with self.assertRaises(ValueError):
            PrivateWebView.set_content(
                view, "https://logistics.invalid/", "😀" * (MAX_HTML // 4 + 1)
            )
        view.private_configured = False
        with self.assertRaises(RuntimeError):
            PrivateWebView.set_content(view, "", "")

    def test_layout_refresh_defers_while_zoomed_and_stops_after_session_end(self):
        from features.comics.mobile.presentation import watch_layout
        from types import SimpleNamespace
        import asyncio

        async def exercise():
            state = dict(alive=True, viewport=(100, 200), calls=0)
            canvas = SimpleNamespace(zoom_scale=2)

            async def refresh():
                state["calls"] += 1
                state["alive"] = False

            async def tick(_):
                if state["viewport"] == (100, 200):
                    state["viewport"] = (200, 100)
                else:
                    self.assertEqual(state["calls"], 0)
                    canvas.zoom_scale = 1

            with patch("asyncio.sleep", side_effect=tick):
                await watch_layout(
                    alive=lambda: state["alive"],
                    available=lambda: True,
                    viewport=lambda: state["viewport"],
                    view=lambda: canvas,
                    reload=refresh, changed=lambda: tick(0),
                )
            self.assertEqual(state["calls"], 1)

        asyncio.run(exercise())

    def test_rich_width_watcher_updates_on_rotation_and_retires_with_owner(self):
        from features.books.mobile.presentation import watch_width
        from types import SimpleNamespace
        import asyncio

        async def exercise():
            widths = iter([732, 395])
            state = dict(alive=True, width=395)
            widget = SimpleNamespace(style=SimpleNamespace(width="none"))
            observed = []

            async def tick(_):
                observed.append(widget.style.width)
                try:
                    state["width"] = next(widths)
                except StopIteration:
                    state["alive"] = False

            with patch("asyncio.sleep", side_effect=tick):
                await watch_width(
                    alive=lambda: state["alive"],
                    width=lambda: state["width"],
                    view=lambda: widget, changed=lambda: tick(0),
                )
            self.assertEqual(observed, ["none", 732, 395])

        asyncio.run(exercise())


class CompositeRenderingTests(unittest.TestCase):
    def test_sampled_decode_keeps_draw_resolution(self):
        from features.comics.mobile.decoding import sample_size
        self.assertEqual(sample_size((8000, 12000), (1000, 1500)), 8)
        self.assertEqual(sample_size((8000, 12000), (1500, 3000)), 4)
        self.assertEqual(sample_size((80, 120), (100, 150)), 1)

    def test_native_composite_preserves_manga_order_gutter_and_alpha(self):
        from features.comics.mobile.composite import compose_spread
        from Mobile.native_tests.tests.logisticsmobile.reader_parity_probe import (
            image_bytes,
        )

        red = image_bytes(b"\xff\x00\x00\xff", 100, 200)
        blue = image_bytes(b"\x00\x00\xff\xff", 80, 160)
        for rtl in (False, True):
            image = compose_spread([red, blue], right_to_left=rtl)
            pixels = image._impl.native.raw
            self.assertEqual(pixels.size, (208, 200))
            self.assertEqual(
                pixels.getpixel((20, 20)), (0, 0, 255, 255) if rtl else (255, 0, 0, 255)
            )
            self.assertEqual(
                pixels.getpixel((180, 20)),
                (255, 0, 0, 255) if rtl else (0, 0, 255, 255),
            )
            self.assertEqual(pixels.getpixel((104, 20)), (0, 0, 0, 0))

    def test_composite_uses_one_zoom_owner_and_retires_pixels_and_callbacks(self):
        import toga
        from features.comics.mobile.presentation import SpreadView
        from Mobile.native_tests.tests.logisticsmobile.reader_parity_probe import (
            image_bytes,
        )

        class Canvas(toga.Box):
            def __init__(self, *, image, on_page, on_toggle, description, style):
                self.image, self.on_page, self.on_toggle, self.zoom_scale = (
                    image,
                    on_page,
                    on_toggle,
                    1,
                )
                super().__init__(style=style)

            def fit_page(self):
                self.zoom_scale = 1

            def dispose(self):
                self.image = self.on_page = self.on_toggle = None

        events = []
        data = image_bytes(b"\xff\x00\x00\xff")
        view = SpreadView(
            [data, data], canvas=Canvas, on_page=events.append, on_toggle=lambda: None
        )
        self.assertEqual(len(view.canvases), 1)
        view.canvas.zoom_scale = 2
        view.turn(1)
        self.assertEqual(events, [])
        view.fit_page()
        view.turn(1)
        self.assertEqual(events, [1])
        canvas = view.canvas
        view.replace([data, data], right_to_left=True)
        self.assertIs(view.canvas, canvas)
        self.assertEqual(canvas.zoom_scale, 1)
        previous = canvas.image
        with patch('features.comics.mobile.composite.compose_spread', side_effect=ValueError('decode')):
            with self.assertRaises(ValueError):
                view.replace([data])
        self.assertIs(canvas.image, previous)
        view.dispose()
        self.assertIsNone(view.canvas.image)
        self.assertIsNone(view.canvas.on_page)
        view.turn(1)
        self.assertEqual(events, [1])

    def test_provider_native_composition_failure_keeps_displayed_pixels_and_position(
        self,
    ):
        from Mobile.native_tests.tests.logisticsmobile.reader_parity_probe import (
            image_bytes,
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = ReaderParityUITests.host(self, root)
            app.preferences.save(comic_layout="double")
            source = root / "comic.cbz"
            with ZipFile(source, "w") as archive:
                for index in range(4):
                    archive.writestr(f"{index}.png", image_bytes(b"\xff\x00\x00\xff"))
            private = PrivateReader("Private.cbz", source.read_bytes())
            app.show_cloud()

            async def exercise():
                with patch.object(app.crypt_copies, "open", return_value=private):
                    self.assertTrue(
                        await app.open_crypt(copies=app.crypt_copies, key="b" * 32)
                    )
                owner = app.private_sessions.active
                before = owner.provider_spread
                image = before.canvas.image
                with patch(
                    "features.comics.mobile.composite.compose_spread",
                    side_effect=ValueError("native allocation failed"),
                ):
                    owner.page_footer.slider.value = 2
                    await owner.page_footer.release(owner.page_footer.slider)
                self.assertIs(owner.provider_spread, before)
                self.assertIs(before.canvas.image, image)
                self.assertIn(before, owner.crypt_content.children)
                self.assertEqual(owner.crypt_reader.comic_navigation.visible, (0, 1))
                self.assertEqual(owner.crypt_page.value, owner.crypt_reader.labels[0])
                self.assertEqual(owner.page_footer.slider.value, 0)
                self.assertTrue(
                    app.private_sessions.close(owner.session.id, discard=True)
                )

            app.loop.run_until_complete(exercise())


class SpeechAndLibraryUITests(unittest.TestCase):
    def test_read_aloud_is_retired_before_changing_chapter(self):
        class Engine:
            ready, error, default_voice = True, "", "Offline"
            voices = {"Offline": None}

            def __init__(self, loop):
                self.closed, self.calls = False, []

            def speak(self, *args):
                self.calls.append(args)

            def stop(self):
                pass

            def close(self):
                self.closed = True

        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = ReaderParityUITests.host(self, root)
            folder = root / "fixtures"
            folder.mkdir()
            epub, _ = make_books(folder)
            record = app.reader_manager().catalog.library_store.import_book(
                LocalDocuments(), epub
            )

            async def exercise():
                await app.open_book(record["id"])
                owner = app.readers.active
                with patch("features.books.mobile.speech_view.NativeSpeech", Engine):
                    owner.show_read_aloud()
                    panel = owner.speech_panel
                    await panel.ready_task
                    panel.session.play(owner.epub_text.text, end=9, voice="Offline")
                    if getattr(owner, "_epub_location_task", None):
                        await owner._epub_location_task
                    await owner.move_book_page(1)
                    self.assertTrue(panel.closed and panel.engine.closed)
                    self.assertEqual(panel.session.ranges, [])
                    self.assertFalse(hasattr(owner, "speech_panel"))

            app.loop.run_until_complete(exercise())

    def test_collection_search_and_recursive_local_batch_preserve_other_resources(self):
        from Mobile.native_tests.tests.logisticsmobile.reader_parity_probe import (
            image_bytes,
        )
        from features.comics.library import ComicDocument

        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = ReaderParityUITests.host(self, root)
            local = app.private_root / "LocalFiles"
            (local / "Comics/nested").mkdir(parents=True)
            sources = [local / "Comics/one.cbz", local / "Comics/nested/two.cbz"]
            data = image_bytes(b"\xff\x00\x00\xff")
            for source in sources:
                with ZipFile(source, "w") as archive:
                    archive.writestr("page.png", data)
                    archive.writestr(
                        "ComicInfo.xml",
                        "<ComicInfo><Writer>Distinct Author</Writer><Tags>Space</Tags></ComicInfo>",
                    )
            catalog = app.reader_manager().catalog
            catalog.library_store.import_book(LocalDocuments(), sources[0])

            async def exercise():
                catalog.refresh_library()
                await catalog.metadata_task
                catalog.filter_library()
                self.assertEqual(
                    [button.text for button in catalog.library_row_buttons], []
                )
                app.show_cloud()
                await app.show_files(local_root=True)
                app.file_location.value = "Comics"
                await app.browse_files()
                app.file_selection.value = "Select an item…"
                await app.edit_local_comic_folder()
                view = app.local_comic_batch_view
                view.metadata_inputs["Title"].value = "Batch title"
                view.metadata_switches["Title"].value = True
                await view.metadata_apply(None)
                self.assertIn("2 saved; 0 failed", view.metadata_status.text)
                for source in sources:
                    self.assertEqual(
                        ComicDocument(source).info.get_field("Title"), "Batch title"
                    )
                    with ZipFile(source) as archive:
                        self.assertEqual(archive.read("page.png"), data)

            app.loop.run_until_complete(exercise())

    def test_batch_suggestions_are_explicit_and_apply_cannot_reenter(self):
        from features.comics.mobile.metadata import batch_form
        from types import SimpleNamespace
        import asyncio

        info = SimpleNamespace(
            FIELDS=["Title", "Writer"],
            get_field=lambda key: "Original" if key == "Title" else "Alice",
        )

        async def exercise():
            entered = asyncio.Event()
            release = asyncio.Event()
            calls = []

            async def save(changes):
                calls.append(changes)
                entered.set()
                await release.wait()
                return "Saved"

            view = batch_form(
                [SimpleNamespace(info=info)],
                save=save,
                back=lambda w: None,
                cancel=lambda w: None,
                choices={"Writer": ["Alice", "Bob"]},
            )
            self.assertFalse(view.metadata_switches["Writer"].value)
            self.assertEqual(view.metadata_inputs["Writer"].value, "Alice")
            selectors = [
                child
                for child in view.content.children
                if child.__class__.__name__ == "Selection"
            ]
            selectors[0].value = "Bob"
            self.assertEqual(view.metadata_inputs["Writer"].value, "Alice, Bob")
            self.assertTrue(view.metadata_switches["Writer"].value)
            task = asyncio.create_task(view.metadata_apply(None))
            await entered.wait()
            self.assertTrue(view.metadata_inputs["Writer"].readonly)
            await view.metadata_apply(None)
            self.assertEqual(len(calls), 1)
            release.set()
            await task
            self.assertFalse(view.metadata_inputs["Writer"].readonly)

        asyncio.run(exercise())
