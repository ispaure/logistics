"""EPUB navigation returns to the passage and keeps tools out of the text."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import toga
from commonUtils.runtime.document_access import LocalDocuments
from features.books.epub import EPUBBook
from features.books.mobile.provider_reader import RichBookView
from features.books.mobile.text_reader import TextBookView
from mobile.app import LogisticsMobile
from services.documents.readers import PrivateReader
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books


class EpubUXTests(unittest.TestCase):
    def test_host_high_contrast_controls_imported_and_private_epub_bridges(self):
        from types import SimpleNamespace as NS
        from features.books.mobile.presentation import ChapterBridge
        from mobile.page_animation import sync_preferences
        imported_view, private_view = Mock(), Mock()
        imported = ChapterBridge(imported_view, root='https://logistics.invalid/a/', motion_enabled=False)
        private = ChapterBridge(private_view, root='https://logistics.invalid/b/')
        imported.loaded(imported_view)
        self.assertIn('"motion": false', imported_view.evaluate_javascript.call_args.args[0])
        private.ready = True
        app = NS(preferences=NS(values={'android_eink': 'true'}),
                 readers=NS(controllers={'one': NS(epub_view=NS(_chapter_bridge=imported))}),
                 private_sessions=NS(controllers={'two': NS(provider_epub_view=NS(webview=NS(_chapter_bridge=private)))}))
        sync_preferences(app)
        private_view.evaluate_javascript.assert_called_with('window.reader && window.reader.setMotion(false)')
        app.preferences.values['android_eink'] = 'false'
        sync_preferences(app)
        imported_view.evaluate_javascript.assert_called_with('window.reader && window.reader.setMotion(true)')
        private_view.evaluate_javascript.assert_called_with('window.reader && window.reader.setMotion(true)')

    def test_private_ios_retirement_clears_live_dom_before_blank_load(self):
        from types import SimpleNamespace
        from features.books.mobile.private_view import PrivateWebView
        events = []
        native = SimpleNamespace(stopLoading=lambda: events.append('stop'),
            evaluateJavaScript=lambda script, **kwargs: events.append(('clear', script)),
            loadHTMLString=lambda content, **kwargs: events.append(('blank', content)),
            navigationDelegate=object(), UIDelegate=object())
        view = SimpleNamespace(private_closed=False, _impl=SimpleNamespace(native=native),
            factory=SimpleNamespace(WebView=type('IOSWebView', (), {'__module__': 'toga_iOS.widgets.webview'})))
        PrivateWebView.clear_private_content(view)
        self.assertTrue(view.private_closed)
        self.assertEqual(events[0], 'stop')
        self.assertEqual(events[1][0], 'clear')
        self.assertIn('document.open()', events[1][1])
        self.assertEqual(events[2], ('blank', ''))
        self.assertIsNone(native.navigationDelegate)
        self.assertIsNone(native.UIDelegate)
        count = len(events)
        PrivateWebView.clear_private_content(view)
        self.assertEqual(len(events), count)

    def test_stop_then_play_queries_visible_page_and_keeps_selection_bounds(self):
        import json
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from features.books.locations import ChapterText
        from features.books.mobile.presentation import speech_source
        from features.books.mobile.speech_view import ReadAloudPanel
        from test_markdown_speech import Engine

        async def exercise():
            chapter = ChapterText('<html><body><p>First page. Second page. Third page.</p></body></html>')
            web = SimpleNamespace(evaluate_javascript=AsyncMock(return_value=json.dumps(
                {'selection': None, 'offset': 12})))
            async def source():
                return await speech_source(web, chapter, 4)
            panel = ReadAloudPanel(loop=asyncio.get_running_loop(), source=source,
                on_range=lambda *args: None, close=lambda *args: None,
                engine=Engine(asyncio.get_running_loop()))
            try:
                await panel.ready_task
                await panel.play()
                self.assertEqual(panel.engine.calls[-1][0], 'Second page.')
                panel.session.stop()
                web.evaluate_javascript.return_value = json.dumps({'selection': None, 'offset': 25})
                await panel.toggle_playback()
                self.assertEqual(panel.engine.calls[-1][0], 'Third page.')
                panel.session.stop()
                web.evaluate_javascript.return_value = json.dumps(
                    {'selection': {'start': 12, 'end': 18}, 'offset': 25})
                await panel.play()
                self.assertEqual(panel.engine.calls[-1][0], 'Second')
            finally:
                panel.dispose()
        asyncio.run(exercise())

    def test_position_burst_writes_latest_once_and_focus_requests_flush(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            epub, _ = make_books(root)
            LogisticsMobile.storage_root = root / 'app'
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), epub)
                async def exercise():
                    await app.open_book(record['id'])
                    owner = app.readers.active
                    with patch.object(owner.library_store, 'progress', wraps=owner.library_store.progress) as write:
                        for offset in range(20):
                            owner.epub_event(owner.book_reader, owner.book_epoch, 0, 'position', offset)
                        await __import__('asyncio').sleep(0)
                        app.checkpoint()
                        self.assertTrue(owner._epub_flush.is_set())
                        await owner._epub_location_task
                        self.assertEqual(write.call_count, 1)
                        self.assertEqual(owner.book_record['location']['offset'], min(19, owner.epub_text.length))
                    await app.reader_manager().catalog.wait_for_refresh()
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()
                LogisticsMobile.storage_root = None

    def test_imported_page_is_mounted_before_progress_write_and_survives_failure(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            epub, _ = make_books(root)
            LogisticsMobile.storage_root = root / 'app'
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), epub)
                def write(*args, **kwargs):
                    owner = next(iter(app.readers.controllers.values()))
                    self.assertTrue(owner.book_content.children)
                    self.assertIs(owner.book_content.children[0], owner.epub_view)
                    raise OSError('synthetic progress failure')
                with patch('mobile.library.LibraryStore.progress', side_effect=write):
                    app.loop.run_until_complete(app.open_book(record['id']))
                owner = app.readers.active
                self.assertTrue(owner.book_content.children)
                self.assertIn('Cannot save reading position', owner.book_status.text)
            finally:
                app.loop.run_until_complete(app.reader_manager().catalog.wait_for_refresh())
                app.main_window.close()
                app.loop.close()
                LogisticsMobile.storage_root = None

    def test_prepared_private_chapter_reuses_worker_index(self):
        from features.books.mobile.content import indexed_chapter
        import threading
        with TemporaryDirectory() as directory:
            epub, _ = make_books(Path(directory))
            book = EPUBBook(epub)
            async def prepare():
                from features.books.locations import ChapterText
                threads = []
                def index(content):
                    threads.append(threading.get_ident())
                    return ChapterText(content)
                with patch('features.books.locations.ChapterText', side_effect=index):
                    result = await asyncio.to_thread(indexed_chapter, book, 0, links=True)
                self.assertNotIn(threading.get_ident(), threads)
                return result
            prepared = asyncio.run(prepare())
            with patch('features.books.mobile.text_reader.ChapterText', side_effect=AssertionError('UI indexing')):
                panel = TextBookView(book, 0, prepared=prepared, on_chapter=Mock(), on_position=Mock())
            self.assertIs(panel.chapter, prepared[1])
            panel.dispose()

    def test_private_tools_preserve_passage_and_search_feedback(self):
        class MemoryWebView(toga.WebView):
            def clear_private_content(self):
                self.set_content('about:blank', '')

        with TemporaryDirectory() as directory:
            epub, _ = make_books(Path(directory))
            book = EPUBBook(epub)
            for view_type in (TextBookView, RichBookView):
                with self.subTest(view=view_type.__name__), patch(
                    'features.books.mobile.provider_reader.PrivateWebView', MemoryWebView
                ):
                    on_position = Mock()
                    panel = view_type(book, 0, offset=7, on_chapter=Mock(), on_position=on_position)
                    self.assertNotIn(panel.tools.panel, panel.tools.widget.children)
                    panel.tools.toggle()
                    self.assertEqual(panel.offset, 7)
                    if isinstance(panel, RichBookView):
                        panel.show_find()
                    panel.query.value = 'no such passage exists'
                    panel.find()
                    if isinstance(panel, RichBookView):
                        self.assertIn(panel.find_box, panel.children)
                        self.assertTrue(panel.sidebar.sidebar_open is False)
                    else:
                        self.assertIn(panel.tools.panel, panel.tools.widget.children)
                    self.assertIn('No matching', panel.status.text)
                    panel.query.value = 'Native'
                    panel.find()
                    self.assertNotIn(panel.tools.panel, panel.tools.widget.children)
                    on_position.assert_called_with(panel.offset)
                    offset = panel.offset
                    panel.tools.toggle()
                    panel.tools.toggle()
                    self.assertEqual(panel.offset, offset)
                    panel.dispose()
                    self.assertEqual(panel.query.value, '')
                    self.assertEqual(list(panel.toc.items), [])

    def test_imported_chapter_and_bookmark_return_to_reading_with_progress(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            epub, _ = make_books(fixtures)
            record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), epub)

            async def until(predicate):
                for _ in range(100):
                    if predicate():
                        return
                    await asyncio.sleep(.01)
                self.fail('Reader navigation did not settle')

            async def exercise():
                await app.open_book(record['id'])
                owner = app.readers.active
                self.assertEqual(app.preferences.values['reading_theme'], 'system')
                self.assertEqual(owner.reading_frame.margin, 0)
                owner.epub_event(owner.book_reader, owner.book_epoch, 0, 'position', 7)
                await owner._epub_location_task
                self.assertIn('Chapter 1 of 2', owner.page_footer.spacer.accessible_name)
                await owner.toggle_bookmark()
                with patch.object(owner, 'show_library', wraps=owner.show_library) as show:
                    menu = owner.library_view._workspace_menu_button
                    with patch.object(app.adaptive, 'show_browser') as browse:
                        menu.on_press()
                        browse.assert_not_called()
                    entry = next(entry for entry in owner.contents_choices.values() if entry.index == 1)
                    await owner.chapter_tree.choose(entry)
                    await until(lambda: show.called and not owner.book_busy and owner.book_record['position'] == 1)
                    self.assertEqual(owner.book_record['position'], 1)
                    show.reset_mock()
                    owner.show_reader_tools()
                    owner.bookmark_selector.value = next(iter(owner.epub_bookmark_choices))
                    await until(lambda: show.called and not owner.book_busy and owner.book_record['position'] == 0)
                    self.assertEqual(owner.book_record['position'], 0)
                    self.assertEqual(owner.epub_offset, 7)
                    self.assertIn('Chapter 1 of 2', owner.page_footer.spacer.accessible_name)
                app.readers.close(owner.session.id)

            app.loop.run_until_complete(exercise())

    def test_private_hamburger_opens_contents_and_bookmarks_without_moving_passage(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            epub, _ = make_books(fixtures)
            app.show_cloud()
            private = PrivateReader('Private.epub', epub.read_bytes())

            async def exercise():
                with patch.object(app.crypt_copies, 'open', return_value=private):
                    self.assertTrue(await app.open_crypt(copies=app.crypt_copies, key='a' * 32))
                owner = app.private_sessions.active
                panel = owner.provider_epub_view
                panel.seek(7)
                menu = owner.crypt_view._workspace_menu_button
                self.assertNotIn(panel.tools.button, panel.tools.widget.children)
                with patch.object(app.adaptive, 'show_browser') as browse:
                    menu.on_press()
                    browse.assert_not_called()
                self.assertIn(panel.tools.panel, panel.tools.widget.children)
                self.assertIn(panel.toc, panel.tools.panel.children)
                self.assertIn(owner.crypt_bookmark_selector, panel.tools.panel.children)
                self.assertEqual(panel.offset, 7)
                owner.crypt_bookmark_button.on_press()
                self.assertEqual(owner.epub_session_bookmarks, {(0, 7)})
                menu.on_press()
                self.assertNotIn(panel.tools.panel, panel.tools.widget.children)
                await owner.move_private_page(1)
                self.assertIs(owner.crypt_bookmark_selector.parent, owner.provider_epub_view.tools.panel)
                self.assertTrue(app.private_sessions.close(owner.session.id, discard=True))

            app.loop.run_until_complete(exercise())
