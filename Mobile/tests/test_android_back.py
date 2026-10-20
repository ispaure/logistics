"""Android Back policy with real retained panels on Toga's dummy backend."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import toga
from logisticsmobile.app import LogisticsMobile


class AndroidBackTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        LogisticsMobile.storage_root = Path(self.directory.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        self.routes = self.app.routes
        self.app.show_documents(destination='documents')
        self.app.show_cloud(present=False)

    def settle(self):
        async def wait():
            if self.routes.back_task is not None:
                await self.routes.back_task
            await asyncio.sleep(0)
        self.app.loop.run_until_complete(wait())

    def test_each_tab_root_returns_home_then_defers_to_android(self):
        self.app.show_documents_hub()
        callback = Mock()
        self.routes.back_callback = callback
        for destination in ('files', 'documents', 'chat', 'settings'):
            with self.subTest(destination=destination):
                self.app.select_destination(destination)
                self.app.native_host.activate(destination)
                self.routes.selection_changed()
                self.assertTrue(callback.setEnabled.call_args.args[0])
                self.assertTrue(self.routes.system_back())
                self.assertEqual(self.app.native_host.state.destination, 'home')
                self.assertFalse(callback.setEnabled.call_args.args[0])
                self.assertFalse(self.routes.system_back())
        self.routes.back_callback = None

    def test_workspace_entry_back_returns_to_overview_after_child_history(self):
        app = self.app
        (app.private_root / 'LocalFiles' / 'Projects' / 'Child').mkdir(parents=True)
        app.show_locations()
        app.loop.run_until_complete(app.browse_hub_folder('Projects'))
        app.loop.run_until_complete(app.browser_file_folder(
            next(row for row in app.file_rows.values() if row['name'] == 'Child')))
        self.assertTrue(self.routes.system_back())
        self.settle()
        self.assertEqual(app.file_path, 'Projects')
        self.assertTrue(self.routes.system_back())
        self.settle()
        self.assertFalse(self.routes.screens['files'])
        self.assertEqual(app.native_host.state.destination, 'files')

    def test_nested_settings_back_and_tab_switch_keep_independent_stacks(self):
        self.app.show_settings()
        with patch.object(self.app.adaptive, 'content_width', return_value=390):
            nav = self.app.settings_navigation
            nav.reflow()
            nav.choose('Text')
            self.app.text_font_size_choice.value = '24'
            self.app.show_view(toga.Label('Connections'), route='connections')
            self.app.native_host.activate('files')
            self.assertTrue(self.routes.system_back())
            self.assertEqual(self.app.native_host.state.destination, 'home')
            self.app.native_host.activate('settings')
            self.assertTrue(self.routes.system_back())
            self.assertEqual(self.routes.screens['settings'][-1][0], 'settings-category')
            self.assertEqual(self.app.text_font_size_choice.value, '24')
            self.assertTrue(self.routes.system_back())
            self.assertFalse(self.routes.screens['settings'])
            self.assertTrue(self.routes.system_back())
            self.assertEqual(self.app.native_host.state.destination, 'home')

    def test_action_handoff_returns_to_source_tab_after_tools_and_tab_switches(self):
        app = self.app
        app.show_view(toga.Label('Folder listing'), destination='files', route='browser')
        origin = app.body
        app.show_view(toga.Label('Opened file'), destination='documents', route='opened-file')
        app.show_view(toga.Label('Reader tools'), route='tools')
        app.select_destination('settings')
        app.native_host.activate('settings')
        app.select_destination('documents')
        app.native_host.activate('documents')
        self.routes.selection_changed()
        self.assertTrue(self.routes.system_back())
        self.assertEqual(app.native_host.state.destination, 'documents')
        with patch.object(self.routes, 'guard', return_value=False):
            self.assertTrue(self.routes.system_back())
            self.assertEqual(app.native_host.state.destination, 'documents')
        self.assertTrue(self.routes.system_back())
        self.assertEqual(app.native_host.state.destination, 'files')
        self.assertIs(app.body, origin)

    def test_replacing_destination_root_discards_old_action_origin(self):
        app = self.app
        app.show_view(toga.Label('Origin'), destination='files', root=True)
        app.show_view(toga.Label('Opened file'), destination='documents', route='opened-file')
        self.assertIn(('documents', 'opened-file'), self.routes.origins)
        app.show_documents_hub()
        self.assertNotIn(('documents', 'opened-file'), self.routes.origins)
        self.assertTrue(self.routes.system_back())
        self.assertEqual(app.native_host.state.destination, 'home')

    def test_entering_folder_browser_keeps_folder_hub_as_its_parent(self):
        app = self.app
        app.loop.run_until_complete(app.show_files())
        self.assertTrue(self.routes.back())
        self.assertEqual(app.native_host.state.destination, 'files')
        self.assertFalse(self.routes.screens['files'])

    def test_local_folder_history_search_and_hub_are_separate_back_steps(self):
        app = self.app
        app.loop.run_until_complete(app.show_files())
        root = app.private_root / 'LocalFiles'
        (root / 'First').mkdir()
        (root / 'Second').mkdir()
        for folder in ('First', 'Second'):
            self.assertTrue(app.loop.run_until_complete(app.browser_file_location(('Local files', folder))))
        browser = app.file_browser
        browser.open_search()
        browser.search.value = 'missing'
        panel = app.body
        self.assertTrue(self.routes.system_back())
        self.assertEqual(browser.search.value, '')
        self.assertEqual(app.file_path, 'Second')
        self.assertTrue(self.routes.system_back())
        self.assertNotIn(browser.search_panel, browser.widget.children)
        self.assertFalse(browser.search_open)
        self.assertTrue(self.routes.system_back())
        self.settle()
        self.assertEqual(app.file_path, 'First')
        self.assertIs(app.body, panel)
        self.assertTrue(self.routes.system_back())
        self.settle()
        self.assertEqual(app.file_path, '')
        self.assertTrue(self.routes.system_back())
        self.assertFalse(self.routes.screens['files'])

    def test_direct_folder_shortcut_falls_back_to_parent(self):
        app = self.app
        app.loop.run_until_complete(app.show_files())
        (app.private_root / 'LocalFiles' / 'Nested').mkdir()
        app.loop.run_until_complete(app.browser_file_location(('Local files', 'Nested')))
        app.file_browser.history.clear()
        self.assertTrue(self.routes.system_back())
        self.settle()
        self.assertEqual(app.file_path, '')

    def test_form_cancel_does_not_consume_underlying_folder_history(self):
        app = self.app
        app.loop.run_until_complete(app.show_files())
        app.show_view(toga.Label('Rename'), route='file-actions')
        panel = app.body
        with patch.object(app.file_browser, 'go_back') as previous:
            self.assertTrue(self.routes.back())
            self.assertIsNot(app.body, panel)
            previous.assert_not_called()

    def test_document_search_and_compact_drawer_preserve_draft(self):
        app = self.app
        app.create_chosen_document('txt')
        owner = app.editor_view
        owner.editor.value = 'Keep my draft'
        owner.toggle_search()
        app.adaptive.menu_open['documents'] = True
        with patch.object(app.adaptive, 'width', return_value=390):
            app.adaptive.wide = False
            self.assertTrue(self.routes.system_back())
            self.assertFalse(app.adaptive.menu_open['documents'])
            self.assertIsNotNone(owner.search.box.parent)
            self.assertTrue(self.routes.system_back())
            self.assertIsNone(owner.search.box.parent)
        self.assertEqual(owner.editor.value, 'Keep my draft')
        self.assertTrue(self.routes.system_back())
        self.assertIn(owner.session.id, app.workspace.sessions)

    def test_chat_drawer_back_keeps_conversation_and_unsent_text(self):
        app = self.app
        app.show_chat()
        with patch.object(app.adaptive, 'width', return_value=390):
            app.chat_drawer_open = True
            app.chat_prompt.value = 'Unsent question'
            current = app.chat_current
            self.assertTrue(self.routes.system_back())
            self.assertFalse(app.chat_drawer_open)
            self.assertEqual(app.native_host.state.destination, 'chat')
            self.assertEqual(app.chat_current, current)
            self.assertEqual(app.chat_prompt.value, 'Unsent question')

    def test_help_drawer_then_page_history_then_settings(self):
        from logisticsmobile.documentation_ui import show_documentation
        root = Path(self.directory.name).resolve() / 'docs'
        root.mkdir()
        first, second = root / 'docs.md', root / 'next.md'
        first.write_text('# First\n\n[Next](next.md)')
        second.write_text('# Next')
        self.app.show_settings()
        owner = show_documentation(self.app, root, first)
        owner.open_page(second)
        owner.show_browse()
        self.assertTrue(self.routes.system_back())
        self.assertFalse(owner.sidebar.sidebar_open)
        self.assertEqual(owner.path, second)
        self.assertTrue(self.routes.system_back())
        self.assertEqual(owner.path, first)
        self.assertTrue(self.routes.system_back())
        self.assertNotIn(owner.view, self.app.body.children)
        self.assertEqual(self.app.native_host.state.destination, 'settings')

    def test_async_back_is_serialized_and_failure_retains_panel(self):
        app = self.app
        app.loop.run_until_complete(app.show_files())
        browser = app.file_browser
        browser.history.visit(('Local files', 'previous'))
        browser.history.visit(('Local files', 'current'))
        async def exercise():
            release = asyncio.Event()
            async def navigate(location):
                await release.wait()
                return False
            browser.on_navigate = Mock(side_effect=navigate)
            panel = app.body
            self.assertTrue(self.routes.system_back())
            self.assertTrue(self.routes.system_back())
            await asyncio.sleep(0)
            browser.on_navigate.assert_called_once()
            release.set()
            await self.routes.back_task
            self.assertEqual(browser.history.current, ('Local files', 'current'))
            self.assertIs(app.body, panel)
            self.assertIsNone(self.routes.back_task)
        app.loop.run_until_complete(exercise())

    def test_checkpoint_failure_blocks_route_pop_and_home_switch(self):
        self.app.show_settings()
        self.app.show_view(toga.Label('Nested'), route='nested')
        with patch.object(self.routes, 'guard', return_value=False):
            panel = self.app.body
            self.assertTrue(self.routes.system_back())
            self.assertIs(self.app.body, panel)
        self.routes.back()
        with patch.object(self.routes, 'guard', return_value=False):
            self.assertTrue(self.routes.system_back())
            self.assertEqual(self.app.native_host.state.destination, 'settings')

    def test_speech_back_hides_controls_without_stopping_playback(self):
        panel = SimpleNamespace(hide=Mock())
        overlay = SimpleNamespace(panel=panel)
        panel.overlay = overlay
        self.app._speech_overlays = [overlay]
        with patch.object(self.app, 'mark_navigation') as navigate:
            self.assertTrue(self.routes.system_back())
            panel.hide.assert_called_once_with()
            navigate.assert_not_called()

    def test_transfer_review_back_cancels_scan_but_transfer_details_do_not_cancel_work(self):
        app = self.app
        review = toga.Box(children=[toga.Label('Comparison')])
        app._transfer_review_view = review
        app._cancel_transfer_review = Mock()
        app.show_view(review, destination='files', route='transfer-review')
        self.assertTrue(self.routes.system_back())
        app._cancel_transfer_review.assert_called_once_with()
        app._cancel_transfer_review.reset_mock()
        app.show_view(toga.Label('Writing'), destination='files', route='transfers')
        self.assertTrue(self.routes.system_back())
        app._cancel_transfer_review.assert_not_called()

    def test_comic_back_reveals_controls_then_tools_return_to_reader_then_origin(self):
        from Mobile.native_tests.tests.logisticsmobile.fixtures import make_books
        app = self.app
        folder = app.private_root / 'fixtures'
        folder.mkdir()
        _, comic = make_books(folder)
        app.loop.run_until_complete(app.show_files())
        origin = app.body
        app.loop.run_until_complete(app.open_download(path=comic))
        reader = app.readers.active
        self.assertTrue(reader.reader_immersive)
        self.assertTrue(self.routes.system_back())
        self.assertFalse(reader.reader_immersive)
        self.assertIn(reader.library_view, app.body.children)
        panel = app.body
        reader.show_reader_tools()
        self.assertTrue(self.routes.system_back())
        self.assertIs(app.body, panel)
        self.assertTrue(self.routes.system_back())
        self.assertEqual(app.native_host.state.destination, 'files')
        self.assertIs(app.body, origin)
        self.assertIn(reader.session.id, app.workspace.sessions)

    def test_pdf_back_closes_search_then_fullscreen_then_returns_to_origin(self):
        from Mobile.tests.test_pdf_reader import native_pdf, PDF
        app = self.app
        path = app.private_root / 'fixture.pdf'
        path.write_bytes(PDF)
        app.loop.run_until_complete(app.show_files())
        origin = app.body
        with patch('features.pdf.document.PDFDocument.open', native_pdf):
            app.loop.run_until_complete(app.open_download(path=path))
            reader = app.private_sessions.active
            reader.pdf_tools.toggle()
            panel = app.body
            self.assertTrue(self.routes.system_back())
            self.assertNotIn(reader.pdf_tools.panel, reader.pdf_tools.widget.children)
            self.assertIs(app.body, panel)
            reader.toggle_private_reading_mode()
            self.assertTrue(reader.crypt_immersive)
            self.assertTrue(self.routes.system_back())
            self.assertFalse(reader.crypt_immersive)
            self.assertTrue(self.routes.system_back())
            self.assertEqual(app.native_host.state.destination, 'files')
            self.assertIs(app.body, origin)

    def test_epub_back_closes_compact_chapters_before_leaving_reader(self):
        from Mobile.native_tests.tests.logisticsmobile.fixtures import make_books
        app = self.app
        folder = app.private_root / 'fixtures'
        folder.mkdir()
        epub, _ = make_books(folder)
        app.loop.run_until_complete(app.open_download(path=epub))
        reader = app.readers.active
        reader.chapter_sidebar.show_sidebar()
        panel = app.body
        self.assertTrue(self.routes.system_back())
        self.assertFalse(reader.chapter_sidebar.sidebar_open)
        self.assertIs(app.body, panel)
        self.assertTrue(self.routes.system_back())
        self.assertNotIn(reader.library_view, app.body.children)

    def test_provider_epub_native_text_fallback_back_closes_chapter_tools(self):
        from Mobile.native_tests.tests.logisticsmobile.fixtures import make_books
        from services.documents.readers import PrivateReader
        app = self.app
        folder = app.private_root / 'fixtures'
        folder.mkdir()
        epub, _ = make_books(folder)
        private = PrivateReader('Private.epub', epub.read_bytes())
        with patch.object(app.crypt_copies, 'open', return_value=private), patch(
                'features.books.mobile.provider_reader.private_webview_supported', return_value=False):
            app.loop.run_until_complete(app.open_crypt(copies=app.crypt_copies, key='a' * 32))
        reader = app.private_sessions.active
        tools = reader.provider_epub_view.tools
        tools.toggle()
        panel = app.body
        self.assertTrue(self.routes.system_back())
        self.assertNotIn(tools.panel, tools.widget.children)
        self.assertIs(app.body, panel)
        self.assertTrue(self.routes.system_back())
        self.assertNotIn(reader.crypt_view, app.body.children)

    def test_notes_library_back_closes_browse_then_retraces_links(self):
        from commonUtils.runtime.local_files import LocalFiles
        from logisticsmobile.obsidian import open_vault
        app = self.app
        vault = app.private_root / 'Vault'
        vault.mkdir()
        (vault / 'First.md').write_text('# First')
        (vault / 'Second.md').write_text('# Second')
        owner = app.loop.run_until_complete(open_vault(app, LocalFiles(app.private_root), 'Vault'))
        self.addCleanup(owner.dispose)
        async def exercise():
            await owner.open_note('Vault/First.md')
            await owner.open_note('Vault/Second.md')
        app.loop.run_until_complete(exercise())
        owner.sidebar.show_sidebar()
        self.assertTrue(self.routes.system_back())
        self.assertFalse(owner.sidebar.sidebar_open)
        self.assertEqual(owner.path, 'Vault/Second.md')
        self.assertTrue(self.routes.system_back())
        self.settle()
        self.assertEqual(owner.path, 'Vault/First.md')

    def test_android_listener_dispatches_policy_and_restores_callback_after_tab_change(self):
        from logisticsmobile.routes import MobileRoutes
        host = self.app.native_host
        callback = Mock()
        bridge = SimpleNamespace(install=Mock(return_value=callback), Listener=object)
        java = SimpleNamespace(dynamic_proxy=lambda base: object)
        host.adapter = SimpleNamespace(impl=SimpleNamespace(_native_activity=object()))
        self.addCleanup(setattr, host, 'adapter', None)
        with patch.dict('sys.modules', {'java': java,
                'io.github.ispaure.commonutils': SimpleNamespace(NavigationBack=bridge)}):
            with patch.object(self.routes, 'on_render', None), patch.object(self.routes, 'changed'):
                self.routes.install()
            self.addCleanup(self.routes.uninstall)
            with patch.object(MobileRoutes, 'system_back', return_value=True) as back:
                self.assertTrue(self.routes.listener.onBackRequested())
                back.assert_called_once_with()
            self.routes.sync_back('settings')
            callback.setEnabled.assert_called_with(True)
            self.routes.sync_back('home')
            callback.setEnabled.assert_called_with(False)

    def test_remote_browser_retraces_remote_locations_before_popping_route(self):
        from unittest.mock import AsyncMock
        from logisticsmobile.browser_ui import FileBrowser
        app = self.app
        navigate = AsyncMock(return_value=True)
        browser = FileBrowser(navigate=navigate, preview=False)
        self.addCleanup(lambda: app.loop.run_until_complete(browser.close()))
        app.remote_browser = browser
        app.show_view(browser.widget, destination='files', route='remote-browser')
        browser.history.visit(('Remote', 'First'))
        browser.history.visit(('Remote', 'Second'))
        panel = app.body
        self.assertTrue(self.routes.system_back())
        self.settle()
        navigate.assert_awaited_once_with(('Remote', 'First'))
        self.assertIs(app.body, panel)

    def test_wide_document_sidebar_remains_a_companion_when_leaving_detail(self):
        app = self.app
        app.create_chosen_document('txt')
        app.adaptive.menu_open['documents'] = True
        with patch.object(app.adaptive, 'width', return_value=900):
            app.adaptive.render()
            self.assertTrue(app.adaptive.wide)
            self.assertTrue(self.routes.system_back())
            self.assertFalse(self.routes.screens['documents'])
            self.assertTrue(app.adaptive.menu_open['documents'])
