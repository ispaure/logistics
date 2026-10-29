"""Bound UI work without relying on machine-dependent timing thresholds."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, get_ident
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from mobile.app import LogisticsMobile
from mobile.browser_ui import FileBrowser


class ResponsivenessTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        LogisticsMobile.storage_root = Path(self.temp.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)

    def test_settings_are_lazy_and_native_selection_does_not_reenter_navigation(self):
        app = self.app
        self.assertFalse(hasattr(app, 'settings_navigation'))
        with patch.object(app.native_host, 'activate', wraps=app.native_host.activate) as activate:
            self.assertTrue(app.select_destination('settings'))
            activate.assert_not_called()
        navigation = app.settings_navigation
        self.assertTrue(app.routes.roots['settings'].children)
        app.native_host.activate('settings')
        app.select_destination('home')
        app.native_host.activate('home')
        with patch.object(navigation, 'reflow') as reflow:
            app.show_documents()
            reflow.assert_not_called()
        app.select_destination('settings')
        self.assertIs(app.settings_navigation, navigation)

    def test_workspace_return_reuses_page_controls_and_source_rows(self):
        from mobile.folder_hub_ui import FolderHubUI
        app = self.app
        local = app.private_root / 'LocalFiles' / 'Notes'
        local.mkdir(parents=True)
        app.select_destination('files')
        app.native_host.activate('files')
        page = app.folder_picker_view
        root = app.routes.roots['files']
        rows = app.folder_list.children[0]
        buttons = dict(app.folder_buttons)
        app.select_destination('home')
        app.native_host.activate('home')
        with patch.object(FolderHubUI, 'build_folder_picker', side_effect=AssertionError('Rebuilt page')), \
                patch('mobile.folder_hub_ui.source_tab') as style, \
                patch.object(app.adaptive, 'prepare') as prepare:
            self.assertTrue(app.select_destination('files'))
        self.assertIs(app.folder_picker_view, page)
        self.assertEqual(root.children, [page])
        self.assertIs(app.folder_list.children[0], rows)
        self.assertEqual(app.folder_buttons, buttons)
        style.assert_not_called()
        prepare.assert_not_called()
        # A real subgroup change still updates both selectors, exactly once.
        with patch('mobile.folder_hub_ui.source_tab') as style:
            app.folder_local_buttons['Rclone'].on_press()
            self.assertEqual(style.call_args_list, [
                unittest.mock.call(app.folder_local_buttons['Rclone'], True),
                unittest.mock.call(app.folder_local_buttons['Others'], False)])
            style.reset_mock()
            app.update_folder_list(app.folder_all_choices)
            style.assert_not_called()

    def test_retained_workspace_refreshes_folder_creation_and_removal(self):
        app = self.app
        root = app.private_root / 'LocalFiles'
        root.mkdir(exist_ok=True)
        (root / 'Old').mkdir()
        app.select_destination('files')
        page = app.folder_picker_view
        self.assertIn('Old', app.folder_buttons)
        app.show_home()
        (root / 'Old').rmdir()
        (root / 'New').mkdir()
        self.assertTrue(app.select_destination('files'))
        self.assertIs(app.folder_picker_view, page)
        self.assertNotIn('Old', app.folder_buttons)
        self.assertIn('New', app.folder_buttons)

    def test_retained_workspace_refreshes_lock_state_and_hidden_source_cache(self):
        app = self.app
        app.cloud_client = SimpleNamespace(generation=1, package_records=(), cancel=lambda: None)
        retained = [dict(zip='Fixture.zip', remotes=['Secret'], crypt_remotes=['Secret'])]
        root = app.private_root / 'LocalCryptFolders' / 'fixture'
        root.mkdir(parents=True)
        (root / 'file').write_bytes(b'fixture')
        app.hub_crypt_roots = {'Secret': ('Secret', 'fixture')}
        app.folder_local_group = 'Rclone'
        with patch.object(app, 'retained_credential_associations', return_value=retained):
            app.select_destination('files')
            app.change_folder_source('rclone')
            def icon():
                return app.folder_buttons['Secret'].parent.children[0].control_icon
            self.assertEqual(icon(), 'folder_locked')
            cloud_rows = app.folder_list.children[0]
            app.change_folder_source('Local')
            app.cloud_client.package_records = (dict(package_name='Fixture.zip', remotes=['Secret']),)
            app.show_home()
            app.select_destination('files')
            self.assertEqual(icon(), 'folder_unlocked')
            app.change_folder_source('rclone')
            # The cached native hierarchy is updated in place when only its
            # credential state changes; returning to it must not rebuild rows.
            self.assertIs(app.folder_list.children[0], cloud_rows)
            self.assertEqual(icon(), 'folder_unlocked')
            # Explicit refresh must notice a lock even with unchanged names.
            app.cloud_client.package_records = ()
            app.loop.run_until_complete(app.refresh_folder_hub())
            self.assertEqual(icon(), 'folder_locked')
            app.change_folder_source('Local')
            self.assertEqual(icon(), 'folder_locked')

    def test_retained_workspace_keeps_credential_filter_and_transfer_actions(self):
        app = self.app
        app.cloud_client = SimpleNamespace(generation=1, package_records=(
            dict(package_name='First.zip', remotes=['One']),
            dict(package_name='Second.zip', remotes=['Two'])), cancel=lambda: None)
        app.select_destination('files')
        app.change_folder_source('rclone')
        app.folder_credential.value = 'First'
        self.assertEqual(set(app.folder_buttons), {'One'})
        page = app.folder_picker_view
        rows = app.folder_list.children[0]
        app.show_home()
        app.transfer_busy = True
        app.select_destination('files')
        self.assertIs(app.folder_picker_view, page)
        self.assertIs(app.folder_list.children[0], rows)
        self.assertEqual(app.folder_credential.value, 'First')
        self.assertEqual(set(app.folder_buttons), {'One'})
        self.assertEqual(app.folder_source_actions.children, [app.folder_transfers_button])
        app.transfer_busy = False
        app.loop.run_until_complete(app.refresh_folder_hub())
        self.assertEqual(app.folder_source_actions.children, [])

    def test_file_tap_opens_without_loading_information_but_explicit_selection_keeps_it(self):
        selected, opened = [], []
        details = Mock(return_value=[('Title', 'A book')])
        browser = FileBrowser(selected=selected.append, open_file=opened.append, details=details)
        provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
        row = dict(path='Book.epub', name='Book.epub', directory=False)
        browser.set_entries(provider, '', [row])
        selected.clear()  # Publishing a folder snapshot clears the old selection.

        async def exercise():
            entry = browser.entries[0]
            await browser.activate_entry(entry)
            self.assertEqual(selected, [row])
            self.assertEqual(opened, [row])
            details.assert_not_called()
            await browser.select(entry)
            details.assert_called_once()
            self.assertTrue(any(getattr(child, 'text', '') == 'Title: A book' for child in browser.info.children))
            await browser.close()
        self.app.loop.run_until_complete(exercise())

    def test_local_and_localcrypt_listings_do_not_read_content_in_list_or_tiles(self):
        app = self.app
        app.show_cloud(present=False)
        app.loop.run_until_complete(app.show_files())
        original_client = app.cloud_client
        client = SimpleNamespace(supports_streaming=True, request=Mock(side_effect=AssertionError('Content request')))
        app.cloud_client = client
        self.addCleanup(setattr, app, 'cloud_client', original_client)
        provider = SimpleNamespace(root=Path(self.temp.name), relative=lambda path: path,
            open=Mock(side_effect=AssertionError('File content read')))
        rows = [dict(path=name, name=name, directory=False, revision=(1, index))
                for index, name in enumerate(['Book.epub', 'Comic.cbz', 'Image.jpg', 'Note.md'])]
        async def exercise():
            for private in (False, True):
                provider.private = private
                app.file_provider = provider
                for mode in ('List', 'Tiles'):
                    app.file_browser.mode = mode
                    app.populate_file_browser(rows)
                    await asyncio.sleep(.02)
                    self.assertEqual(len(app.file_browser.native_list.data) if mode == 'List' else len(app.file_browser.buttons), 4)
                    self.assertIsNone(app.file_browser.thumbnail)
                    self.assertIsNotNone(app.file_browser.details)
                    provider.open.assert_not_called()
                    client.request.assert_not_called()
        app.loop.run_until_complete(exercise())

    def test_local_markdown_initial_render_runs_once_off_ui_thread(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        from mobile.preview import markdown_preview
        app = self.app
        app.show_cloud(present=False)
        path = Path(self.temp.name) / 'Note.md'
        path.write_text('# Hello\n\nA local note.\n')
        ui_thread = get_ident()
        rendered_threads = []
        def render(*args, **kwargs):
            rendered_threads.append(get_ident())
            return markdown_preview(*args, **kwargs)
        with patch('mobile.preview.markdown_preview', side_effect=render):
            app.loop.run_until_complete(app.open_crypt(copies=LocalTextCopies(LocalFiles(path.parent)), key=path.name))
        self.assertEqual(len(rendered_threads), 1)
        self.assertNotEqual(rendered_threads[0], ui_thread)
        owner = app.private_sessions.active
        self.assertEqual(owner.crypt_text.value, path.read_text())
        self.assertIn(owner.crypt_preview, owner.crypt_content.children)
        app.loop.run_until_complete(asyncio.sleep(0))

    def test_file_tap_rejects_listing_replaced_during_selection(self):
        opened = []
        provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
        row = dict(path='Note.md', name='Note.md', directory=False)
        browser = FileBrowser(open_file=opened.append)
        browser.set_entries(provider, '', [row])
        async def selected(value):
            if value is not None:
                await asyncio.sleep(0)
                browser.set_entries(provider, '', [dict(row, revision='replaced')])
        browser.on_selected = selected
        async def exercise():
            entry = browser.entries[0]
            await browser.activate_entry(entry)
            self.assertEqual(opened, [])
            self.assertFalse(browser.navigation_busy)
            await browser.close()
        self.app.loop.run_until_complete(exercise())

    def test_selection_styles_only_the_rows_that_changed(self):
        from mobile.browser_ui import highlight_entry
        browser = FileBrowser()
        provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
        rows = [dict(path=f'{i}.md', name=f'{i}.md', directory=False) for i in range(40)]
        browser.set_entries(provider, '', rows)
        browser.selected = browser.entries[0].identity
        browser.highlight_selection()
        with patch('mobile.browser_ui.highlight_entry', wraps=highlight_entry) as style:
            browser.highlight_selection()
            style.assert_not_called()
            browser.selected = browser.entries[1].identity
            browser.highlight_selection()
            style.assert_not_called()  # Native selection does not repaint Python rows.
            self.assertEqual(browser.native_list.selection.entry.identity, browser.selected)
        self.app.loop.run_until_complete(browser.close())

    def test_cancel_during_markdown_render_does_not_publish_reader(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        app = self.app
        app.show_cloud(present=False)
        path = Path(self.temp.name) / 'Cancel.md'
        path.write_text('# Cancel me')
        release = Event()

        async def exercise():
            entered = asyncio.Event()
            def render(*args, **kwargs):
                app.loop.call_soon_threadsafe(entered.set)
                release.wait(10)
                return '<html>cancelled passage</html>'
            with patch('mobile.preview.markdown_preview', side_effect=render):
                opening = asyncio.create_task(app.open_crypt(copies=LocalTextCopies(LocalFiles(path.parent)), key=path.name))
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    owner = next(iter(app.private_sessions.controllers.values()))
                    owner.cancel_cloud()
                finally:
                    release.set()
                self.assertFalse(await opening)
            self.assertFalse(app.private_sessions.controllers)
            self.assertIsNone(app.private_sessions.active)
        app.loop.run_until_complete(exercise())

    def test_markdown_render_error_keeps_source_without_rerendering_on_ui_thread(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        app = self.app
        app.show_cloud(present=False)
        path = Path(self.temp.name) / 'Source.md'
        path.write_text('# Keep original text')
        with patch('mobile.preview.markdown_preview', side_effect=ValueError('Cannot render this image')) as render:
            self.assertTrue(app.loop.run_until_complete(app.open_crypt(
                copies=LocalTextCopies(LocalFiles(path.parent)), key=path.name)))
            render.assert_called_once()
        owner = app.private_sessions.active
        self.assertEqual(owner.crypt_text.value, path.read_text())
        self.assertIn(owner.crypt_text, owner.crypt_content.children)
        self.assertIn('Cannot render this image', owner.crypt_title.text)


if __name__ == '__main__':
    unittest.main()
