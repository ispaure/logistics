"""Reader paging owns swipes while Workspaces retains the source folder."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from mobile.app import LogisticsMobile
from mobile.page_animation import page_direction, begin_page_slide, finish_page_slide
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books


class ReaderNavigationTests(unittest.TestCase):
    def test_documents_reselection_returns_to_list_but_switching_tabs_retains_reader(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                fixtures = root / 'fixtures'
                fixtures.mkdir()
                epub, _ = make_books(fixtures)
                from commonUtils.runtime.resources.documents import LocalDocuments

                def tap(destination):
                    host = app.native_host
                    host.root._impl._set_value('current_tab_index', host.destinations.index(destination))
                    host.root.on_select()

                async def exercise():
                    store = app.reader_manager().catalog.library_store
                    record = store.import_book(LocalDocuments(), epub)
                    app.show_documents_hub()
                    await app.open_book(record['id'])
                    owner = app.readers.active
                    panel = app.body
                    # Programmatic activation and a return from Home retain the reader.
                    app.native_host.activate('documents')
                    self.assertIs(app.body, panel)
                    tap('home')
                    tap('documents')
                    self.assertIs(app.body, panel)
                    with patch.object(app, 'checkpoint', return_value=False):
                        tap('documents')
                    self.assertIs(app.body, panel)
                    self.assertTrue(app.routes.screens['documents'])
                    # Reselect from a nested reader page goes straight to the list.
                    owner.show_reader_appearance()
                    tap('documents')
                    self.assertEqual(app.native_host.state.destination, 'documents')
                    self.assertIs(app.body, app.routes.roots['documents'])
                    self.assertFalse(app.routes.screens['documents'])
                    self.assertIn(owner.session.id, app.workspace.sessions)
                    await app.open_book(record['id'])
                    self.assertIs(app.readers.active, owner)
                    await app.readers.catalog.metadata_task
                    await app.readers.catalog.library_scan_task
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_volume_paging_uses_real_library_owner_and_stops_on_appearance_route(self):
        from mobile.android_volume_pages import VolumePages, target
        from commonUtils.runtime.resources.documents import LocalDocuments
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                fixtures = root / 'fixtures'
                fixtures.mkdir()
                _, comic = make_books(fixtures)
                async def exercise():
                    store = app.reader_manager().catalog.library_store
                    record = store.import_book(LocalDocuments(), comic)
                    app.preferences.save(comic_volume_pages='true', comic_layout='single')
                    await app.open_book(record['id'])
                    owner = app.readers.active
                    handler = VolumePages.__new__(VolumePages)
                    handler.app, handler.task = app, None
                    self.assertIs(target(app)[0], owner)
                    self.assertTrue(handler.press(1))
                    await handler.task
                    self.assertEqual(owner.book_record['position'], 1)
                    self.assertTrue(handler.press(-1))
                    await handler.task
                    self.assertEqual(owner.book_record['position'], 0)
                    owner.show_reader_appearance()
                    self.assertIsNone(target(app))
                    self.assertFalse(handler.press(1))
                    owner.show_library()
                    self.assertIs(target(app)[0], owner)
                    app.show_home()
                    self.assertIsNone(target(app))
                    await app.readers.catalog.metadata_task
                    await app.readers.catalog.library_scan_task
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_all_documents_from_home_reader_keeps_session_and_can_resume(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                fixtures = root / 'fixtures'
                fixtures.mkdir()
                paths = make_books(fixtures)
                from commonUtils.runtime.resources.documents import LocalDocuments

                async def exercise():
                    store = app.reader_manager().catalog.library_store
                    for path in paths:
                        record = store.import_book(LocalDocuments(), path)
                        app.show_home()
                        await app.open_book(record['id'])
                        owner = app.readers.active
                        key = owner.session.id
                        self.assertEqual(app.native_host.state.destination, 'home')
                        self.assertEqual(app.routes.screens['home'][-1][0], 'reader:' + key)
                        self.assertFalse(app.routes.origins)
                        owner.reader_actions.invoke(dict(owner.reader_actions.actions)['All documents'])
                        self.assertEqual(app.native_host.state.destination, 'documents')
                        self.assertFalse(app.routes.screens['documents'])
                        self.assertIs(app.body, app.routes.roots['documents'])
                        self.assertIn(key, app.workspace.sessions)
                        self.assertFalse(app.routes.origins)
                        await app.open_book(record['id'])
                        self.assertIs(app.readers.active, owner)
                        self.assertEqual(owner.session.id, key)
                    await app.readers.catalog.metadata_task
                    await app.readers.catalog.library_scan_task
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_folder_open_keeps_workspaces_and_back_restores_browser(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.show_cloud(present=False)
                from services.documents.locations import collection_path
                fixtures = collection_path(app.private_root) / 'fixtures'
                fixtures.mkdir(parents=True)
                epub, comic = make_books(fixtures)
                async def exercise():
                    for path in (comic, epub):
                        await app.show_files()
                        await app.browser_file_location(('Local files', 'fixtures'))
                        row = next(row for row in app.file_rows.values() if row['name'] == path.name)
                        app.browser_file_selected(row)
                        origin = app.body
                        file_path = app.file_path
                        with patch.object(app.native_host.chrome, 'set_page_swipes',
                                          wraps=app.native_host.chrome.set_page_swipes) as policy:
                            await app.read_managed_file()
                            self.assertEqual(app.native_host.state.destination, 'files')
                            owner = app.readers.active
                            self.assertTrue(policy.call_args.args[0])
                            if path == comic:
                                with patch('mobile.page_animation.begin_page_slide') as begin, patch(
                                        'mobile.page_animation.finish_page_slide') as finish:
                                    for rtl in (False, True):
                                        owner.book_reader.right_to_left = rtl
                                        for index, expected in ((1, -1 if rtl else 1), (0, 1 if rtl else -1)):
                                            await owner.move_book_page(index)
                                            self.assertEqual(begin.call_args.args[1], expected)
                                            self.assertEqual(finish.call_args.args[1], expected)
                            if path == epub:
                                with patch('mobile.page_animation.begin_page_slide') as begin:
                                    await owner.move_book_page(1)
                                    self.assertEqual(begin.call_args.args[1], 1)
                                    await owner.move_book_page(0)
                                    self.assertEqual(begin.call_args.args[1], -1)
                            owner.set_reading_mode(False)
                            app.adaptive.render()
                            self.assertTrue(policy.call_args.args[0])
                            owner.set_reading_mode(True)
                            app.adaptive.render()
                            self.assertTrue(policy.call_args.args[0])
                            self.assertTrue(app.routes.back())
                            self.assertIs(app.body, origin)
                            self.assertEqual(app.file_path, file_path)
                            self.assertFalse(policy.call_args.args[0])
                            self.assertNotIn(owner.session.id, app.workspace.sessions)
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_slide_direction_tracks_page_order_and_manga(self):
        for rtl in (False, True):
            self.assertEqual(page_direction(None, 0, right_to_left=rtl), 0)
            self.assertEqual(page_direction(3, 3, right_to_left=rtl), 0)
            self.assertEqual(page_direction(2, 4, right_to_left=rtl), -1 if rtl else 1)
            self.assertEqual(page_direction(4, 2, right_to_left=rtl), 1 if rtl else -1)
        content = Mock()
        for direction, preferences in ((0, {}), (1, {'android_eink': 'true'})):
            begin_page_slide(content, direction, preferences)
            finish_page_slide(content, direction, preferences)
        self.assertEqual(content.mock_calls, [])

    def test_high_contrast_cancels_inflight_native_page_motion(self):
        from types import SimpleNamespace
        for backend in ('toga_iOS.widgets.box', 'toga_android.widgets.box'):
            impl = type('Backend', (), {'__module__': backend})()
            impl.native = Mock()
            content = SimpleNamespace(_impl=impl)
            begin_page_slide(content, 1, {'android_eink': 'true'})
            finish_page_slide(content, 1, {'android_eink': 'true'})
            if backend.startswith('toga_iOS.'):
                impl.native.layer.removeAnimationForKey.assert_called_once_with('transition')
                impl.native.layer.addAnimation.assert_not_called()
            else:
                impl.native.clearAnimation.assert_called_once_with()
                impl.native.startAnimation.assert_not_called()

    def test_cancelling_ios_snapshot_releases_pixels_and_removes_its_wrapper(self):
        from types import SimpleNamespace as NS
        from mobile.page_animation import cancel_page_slide
        impl = type('Backend', (), {'__module__': 'toga_iOS.widgets.box'})()
        impl.native = NS(clipsToBounds=True, layer=Mock())
        snapshot = Mock()
        wrapper = Mock()
        state = impl._ios_page_slide = NS(snapshot=snapshot, wrapper=wrapper, blocks=(object(),))
        content = NS(_impl=impl)
        cancel_page_slide(content)
        self.assertIsNone(impl._ios_page_slide)
        self.assertIsNone(state.snapshot)
        self.assertEqual(state.blocks, ())
        self.assertIsNone(state.wrapper)
        self.assertIsNone(snapshot.image)
        wrapper.removeFromSuperview.assert_called_once_with()
        snapshot.layer.removeAllAnimations.assert_called_once_with()
        snapshot.removeFromSuperview.assert_called_once_with()
        cancel_page_slide(content)
        snapshot.removeFromSuperview.assert_called_once_with()

    def test_ios_capture_resolves_the_native_window_getter(self):
        from types import SimpleNamespace as NS
        import sys
        geometry = NS(origin=NS(x=0, y=0), size=NS(width=320, height=480))
        window = NS(bounds=geometry, drawViewHierarchyInRect=Mock())
        root = object()
        native = NS(bounds=geometry, window=lambda: window, layer=Mock())
        def convert(rect, *, toView):
            self.assertIn(toView, (root, window))
            return rect
        native.convertRect = convert
        impl = type('Backend', (), {'__module__': 'toga_iOS.widgets.box'})()
        impl.native, impl.container = native, NS(native=root)
        content = NS(_impl=impl, children=[])
        renderer, picture, bezier = Mock(), Mock(), Mock()
        renderer.imageWithActions.side_effect = lambda block: (block(None), object())[1]
        classes = {'UIGraphicsImageRenderer': Mock(), 'UIImageView': Mock(), 'UIBezierPath': bezier}
        classes['UIGraphicsImageRenderer'].alloc.return_value.initWithSize.return_value = renderer
        classes['UIImageView'].alloc.return_value.initWithImage.return_value = picture
        objc = NS(ObjCClass=classes.__getitem__, Block=lambda function, *args: function,
                  objc_id=object(), CGRect=lambda *args: args)
        reduced = Mock(return_value=False)
        with patch.dict(sys.modules, {'rubicon.objc': objc}), \
                patch('ctypes.CDLL', return_value=NS(UIAccessibilityIsReduceMotionEnabled=reduced)), \
                patch('mobile.appearance.apple_color', return_value=Mock()):
            begin_page_slide(content, 1, {})
        window.drawViewHierarchyInRect.assert_called_once()
        self.assertIs(impl._ios_page_slide.snapshot, picture)


class VolumePageTests(unittest.IsolatedAsyncioTestCase):
    """Volume paging follows the visible document, preferences and privacy."""

    def fixture(self, *, private=False, kind='epub'):
        from types import SimpleNamespace as NS
        from unittest.mock import AsyncMock
        from mobile.android_volume_pages import VolumePages
        surface = NS(children=[], _reader_session_id='book')
        owner = NS(session=NS(kind=kind), book_busy=False, cloud_busy=False,
                   library_view=surface, crypt_view=surface,
                   previous_book_page=AsyncMock(), next_book_page=AsyncMock(),
                   previous_private_page=AsyncMock(), next_private_page=AsyncMock())
        manager = NS(controllers={'book': owner})
        app = NS(active_host=True, body=surface,
                 screen_privacy=NS(inactive=False, resume_locked=False),
                 preferences=NS(values={'epub_volume_pages': 'false', 'comic_volume_pages': 'false'}),
                 visible_reader=lambda: 'book', reader_tool_back=lambda view: None,
                 readers=None if private else manager, private_sessions=manager if private else None,
                 loop=__import__('asyncio').get_running_loop())
        handler = VolumePages.__new__(VolumePages)
        handler.app, handler.task = app, None
        return app, owner, handler

    async def test_defaults_and_independent_book_comic_mapping(self):
        for private in (False, True):
            for kind in ('epub', 'comic'):
                with self.subTest(private=private, kind=kind):
                    app, owner, handler = self.fixture(private=private, kind=kind)
                    self.assertFalse(handler.press(1))
                    other = 'comic' if kind == 'epub' else 'epub'
                    app.preferences.values[other + '_volume_pages'] = 'true'
                    self.assertFalse(handler.press(1))
                    app.preferences.values[kind + '_volume_pages'] = 'true'
                    self.assertTrue(handler.press(1))
                    await handler.task
                    self.assertTrue(handler.press(-1))
                    await handler.task
                    prefix = 'private' if private else 'book'
                    getattr(owner, 'next_' + prefix + '_page').assert_awaited_once()
                    getattr(owner, 'previous_' + prefix + '_page').assert_awaited_once()

    async def test_hidden_tools_locked_background_and_other_formats_keep_volume(self):
        from types import SimpleNamespace as NS
        for state in ('hidden', 'tool', 'locked', 'background', 'inactive', 'reset', 'pdf'):
            with self.subTest(state=state):
                app, owner, handler = self.fixture()
                app.preferences.values['epub_volume_pages'] = 'true'
                if state == 'hidden':
                    app.body = NS(children=[])
                elif state == 'tool':
                    app.reader_tool_back = lambda view: lambda: None
                elif state == 'locked':
                    app.screen_privacy.resume_locked = True
                elif state == 'background':
                    app.active_host = False
                elif state == 'inactive':
                    app.screen_privacy.inactive = True
                elif state == 'reset':
                    app._reset_scheduled = True
                else:
                    owner.session.kind = 'pdf'
                self.assertFalse(handler.press(1))
                self.assertIsNone(handler.task)

    async def test_busy_and_queued_presses_do_not_double_turn_or_change_volume(self):
        app, owner, handler = self.fixture()
        app.preferences.values['epub_volume_pages'] = 'true'
        owner.book_busy = True
        self.assertTrue(handler.press(1))
        self.assertIsNone(handler.task)
        owner.book_busy = False
        self.assertTrue(handler.press(1))
        first = handler.task
        self.assertTrue(handler.press(1))
        self.assertIs(handler.task, first)
        await first
        owner.next_book_page.assert_awaited_once()
        self.assertTrue(handler.press(-1))
        app.screen_privacy.resume_locked = True
        await handler.task
        owner.previous_book_page.assert_not_awaited()

    async def test_android_options_persist_separately_and_ios_hides_them(self):
        from mobile.preferences import Preferences
        from features.books.mobile.appearance import ReaderAppearance
        with TemporaryDirectory() as folder:
            prefs = Preferences(Path(folder).resolve())
            self.assertEqual(prefs.values['epub_volume_pages'], 'false')
            self.assertEqual(prefs.values['comic_volume_pages'], 'false')
            with patch('features.books.mobile.appearance.sys.platform', 'android'):
                book = ReaderAppearance(prefs.values, lambda widget: None)
                comic = ReaderAppearance(prefs.values, lambda widget: None, kind='comic')
                self.assertFalse(book.volume_pages.value)
                self.assertFalse(comic.volume_pages.value)
                book.volume_pages.value = True
                prefs.save(**book.settings())
                saved = Preferences(Path(folder).resolve())
                self.assertEqual(saved.values['epub_volume_pages'], 'true')
                self.assertEqual(saved.values['comic_volume_pages'], 'false')
                comic.volume_pages.value = True
                prefs.save(**comic.settings())
                self.assertEqual(prefs.values['epub_volume_pages'], 'true')
                self.assertEqual(prefs.values['comic_volume_pages'], 'true')
            with patch('features.books.mobile.appearance.sys.platform', 'ios'):
                book = ReaderAppearance(prefs.values, lambda widget: None)
                self.assertIsNone(book.volume_pages)
                self.assertNotIn('epub_volume_pages', book.settings())
            with self.assertRaises(ValueError):
                prefs.save(epub_volume_pages='yes')
            with self.assertRaises(ValueError):
                prefs.save(comic_volume_pages='yes')
