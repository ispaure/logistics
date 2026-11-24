"""Search routes retain populated results beneath files and folder visits."""

import asyncio
from pathlib import Path
from unittest import TestCase
from unittest.mock import AsyncMock, patch

import toga
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from mobile_build.tests.support.app import create_app

TEST_STAGE = TestStage.REGRESSION


class SearchPanelTests(TestCase):
    def setUp(self):
        self.app = create_app(self)
        from services.documents.locations import collection_path
        self.root = collection_path(self.app.private_root) / 'search-panel-fixture'
        (self.root / 'Needle folder/Child').mkdir(parents=True)
        (self.root / 'Needle.txt').write_text('Search file')
        (self.root / 'Needle folder/Child/Inner.txt').write_text('Inner file')

    def test_documents_library_loads_local_comic_tile_thumbnails(self):
        from base64 import b64encode
        from unittest.mock import Mock
        from zipfile import ZipFile
        from mobile_build.native_tests.tests.logisticsmobile.browser_thumbnail_checks import png

        app = self.app
        cover = png(30, (20, 70, 110))
        encoded = b64encode(cover).decode()
        with ZipFile(self.root / 'Volume.cbz', 'w') as archive:
            archive.writestr('01.png', cover)
        bridge = Mock()
        bridge.request.return_value = {'data': encoded}

        async def exercise():
            app.show_documents_hub()
            self.assertTrue(await app.hub_controller().browse_document_library(
                'Local files', provider=LocalFiles(self.root), folder='', title='Comics'))
            browser = app.adaptive.browsers['documents'].browser
            browser.show_tiles()
            self.assertTrue(browser._previews_visible)
            entry = next(entry for entry in browser.entries if entry.suffix == '.cbz')
            box, fallback = browser._tile_previews[entry.identity]
            async with asyncio.timeout(5):
                while box.children[0] is fallback:
                    await asyncio.sleep(.01)
            bridge.request.assert_called_once_with(
                'image_thumbnail', data=encoded, width=browser._tile_thumbnail_size()[0],
                height=browser._tile_thumbnail_size()[1])

            app.show_view(toga.Box(), destination='documents', route='test-reader', title='Volume')
            self.assertFalse(browser._previews_visible)
            self.assertTrue(app.routes.back())
            self.assertTrue(browser._previews_visible)

        with patch('mobile.browser_preview.local_image_bridge', return_value=bridge):
            app.loop.run_until_complete(exercise())

    def test_file_search_retains_results_under_files_and_nested_folders(self):
        app = self.app
        app.show_documents_hub()
        app.loop.run_until_complete(app.hub_controller().browse_document_library(
            'Local files', provider=LocalFiles(self.root), folder='', title='Fixture'))
        browser = app.adaptive.browsers['documents'].browser
        parent = browser.widget.parent
        opener = AsyncMock(side_effect=lambda row: app.show_view(toga.Box(),
            destination='documents', route='test-reader', title=row['name']))
        browser.on_open_file = opener
        panel = browser.open_search()
        browser.search.value = 'Needle'
        app.loop.run_until_complete(asyncio.sleep(.5))
        tree = browser.tree
        result_rows = list(browser.native_list.data)
        self.assertEqual({row.title for row in result_rows}, {'Needle.txt', 'Needle folder'})
        self.assertIsNone(browser.native_list.menu_provider)
        self.assertIsNone(getattr(browser.native_list.on_primary_action, '_raw', None))
        self.assertIsNone(browser.close_search_button.parent)
        self.assertEqual(panel.view._ios_toolbar_buttons, [])
        self.assertEqual(panel.view._ios_toolbar_leading, [panel.close_button])

        file = next(entry for entry in browser.entries if not entry.container)
        app.loop.run_until_complete(browser.activate_entry(file))
        opener.assert_awaited_once()
        app.routes.back()
        self.assertIs(app.routes.body().children[0], panel.view)
        self.assertIs(browser.tree, tree)
        self.assertEqual(list(browser.native_list.data), result_rows)
        self.assertEqual(browser.search.value, 'Needle')

        folder = next(entry for entry in browser.entries if entry.container)
        app.loop.run_until_complete(browser.activate_entry(folder))
        folder_browser = app.routes.body().children[0]._search_folder
        app.loop.run_until_complete(folder_browser.activate_entry(folder_browser.entries[0]))
        self.assertEqual(app.routes.body().children[0]._search_folder.entries[0].label, 'Inner.txt')
        app.routes.back()
        app.routes.back()
        self.assertIs(app.routes.body().children[0], panel.view)
        self.assertIs(browser.tree, tree)
        self.assertEqual(browser.search.value, 'Needle')
        panel.close()
        self.assertIs(browser.widget.parent, parent)
        self.assertEqual(browser.search.value, '')
        self.assertFalse(browser.search_open)

    def test_library_subfolder_reflows_with_the_retained_libraries_list(self):
        from mobile.documents_hub import library_folder_button, library_folder_row
        app = self.app
        with patch.object(app.adaptive, 'content_width', return_value=640) as width, \
                patch('mobile.fold_layout.division', return_value=None):
            app.show_documents_hub()
            hub = app.hub_controller()
            app.loop.run_until_complete(hub.browse_document_library(
                'Local files', provider=LocalFiles(self.root), folder='', title='Fixture'))
            drawer = app.adaptive.browsers['documents']
            page, nav, body = drawer.page, hub._document_collection_navigation, hub._document_collection_body
            record = dict(name='Fixture', source='Local files', folder='')
            row = library_folder_row(library_folder_button(record, None), record)
            hub.document_books_list.add(row)
            app.loop.run_until_complete(drawer.open_folder({'path': 'Needle folder/Child'}))
            listing = drawer.browser.tree
            sidebar = drawer.library_sidebar
            for available, host in ((640, body), (900, sidebar), (640, body), (900, sidebar)):
                width.return_value = available
                app.adaptive.render()
                wide = host is sidebar
                self.assertIs(hub.visible_library_drawer(), drawer)
                self.assertIs(nav.parent, host)
                self.assertEqual(page.style.direction, 'row' if wide else 'column')
                if wide:
                    self.assertEqual(sidebar.children[0].text, 'Documents')
                    self.assertIs(sidebar.children[1], nav)
                self.assertEqual(getattr(row, '_document_library_selected', False), wide)
                self.assertEqual(nav in page._bottom_scrolls, wide)
                self.assertIs(drawer.browser.tree, listing)
                self.assertEqual(drawer.breadcrumb.value, 'Child')
                self.assertEqual(drawer.folder, 'Needle folder/Child')
                self.assertEqual(len(app.routes.screens['documents']), 1)
            app.loop.run_until_complete(drawer.up())
            self.assertEqual(drawer.breadcrumb.value, 'Needle folder')
            app.loop.run_until_complete(drawer.up())
            self.assertEqual(drawer.breadcrumb.value, 'Fixture')
            self.assertTrue(app.loop.run_until_complete(drawer.up()))
            self.assertIsNone(hub.visible_library_drawer())
            self.assertIs(nav.parent, body)
            self.assertFalse(row._document_library_selected)

    def test_documents_search_retains_results_and_folder_return_boundary(self):
        from mobile.document_search import scan_local_documents
        from mobile_build.tests.workspace.test_hub_documents import widgets
        app = self.app
        app.show_documents_hub()
        panel = app.open_document_search()
        app.document_search.value = 'Needle'
        hub = app.hub_controller()
        hub._document_search_delay.cancel()
        hits, failures = scan_local_documents(app, 'Needle')
        hub.clear_document_search_results()
        hub.publish_document_search(hits, failures)
        results = list(hub.document_search_results.children)
        # A reader refresh must not clear/restart a completed query.
        hub._document_query_started = 'needle'
        with patch.object(hub._documents_file_search, 'start') as start:
            hub.refresh_document_list()
            start.assert_not_called()
        buttons = [w for w in widgets(hub.document_search_results) if isinstance(w, toga.Button)]
        self.assertEqual({b.text for b in buttons}, {'Needle.txt', 'Needle folder'})
        folder = next(b for b in buttons if b.text == 'Needle folder')
        app.loop.run_until_complete(folder.on_press())
        app.routes.back()
        self.assertIs(app.routes.body().children[0], panel.view)
        self.assertEqual(list(hub.document_search_results.children), results)
        self.assertEqual(app.document_search.value, 'Needle')
        panel.close()
        self.assertFalse(app.documents_search_open)

    def test_workspaces_search_uses_the_selected_local_subtab_without_a_folder(self):
        app = self.app
        app.show_locations()
        owner = app.folder_controller()
        owner.folder_source = 'Local'
        for group, scope in [('Others', 'device'), ('Rclone', 'copies')]:
            owner.folder_local_group = group
            panel = owner.open_workspace_search()
            self.assertEqual(panel.destination, 'files')
            self.assertEqual(app.hub_controller()._documents_file_search.scope, scope)
            self.assertIs(app.routes.body().children[0], panel.view)
            scroll = app.hub_controller()._document_search_scroll
            panel.close()
            self.assertIsNone(scroll.content)
        owner.folder_source = 'rclone'
        self.assertFalse(owner.open_workspace_search())

    def test_workspace_search_scopes_separate_device_files_and_copies(self):
        from mobile.document_search import scan_local_documents
        app = self.app
        copies, device = self.root / 'copies', self.root / 'device'
        copies.mkdir()
        device.mkdir()
        (copies / 'Needle copy.txt').write_text('copy')
        (device / 'Needle device.txt').write_text('device')
        roots = {'Local files': LocalFiles(copies), 'Shared files': LocalFiles(device)}
        with (patch.object(app, 'ordinary_file_roots', return_value=roots),
              patch.object(app, 'existing_crypt_locations', return_value={}),
              patch.object(app, 'linked_crypt_locations', return_value={})):
            for scope, name in [('copies', 'Needle copy.txt'), ('device', 'Needle device.txt')]:
                hits, failures = scan_local_documents(app, 'Needle', scope=scope)
                self.assertFalse(failures)
                self.assertEqual([hit['name'] for hit in hits], [name])

    def test_library_folder_toolbar_switches_view_and_selects_items(self):
        app = self.app
        app.show_documents_hub()

        async def exercise():
            for category in ('books', 'comics'):
                with self.subTest(category=category):
                    await app.hub_controller().browse_document_library(
                        'Local files', provider=LocalFiles(self.root), folder='', title='Fixture', category=category)
                    drawer = app.adaptive.browsers['documents']
                    browser = drawer.browser
                    back, search, switch, select = drawer.folder_toolbar_actions()
                    self.assertTrue(back.enabled)
                    self.assertEqual([button.control_icon for button in (search, switch, select)],
                                     ['find', 'file_tiles', 'selected_item'])
                    self.assertTrue(select.enabled)

                    await drawer.open_folder({'path': 'Needle folder'})
                    browser.switch_view()
                    self.assertTrue(await drawer.up())
                    self.assertEqual(browser.mode, 'Tiles')
                    self.assertIs(browser.mounted_listing(), browser._tile_scroll)
                    self.assertEqual(switch.control_icon, 'contents')

                    drawer.begin_file_selection()
                    entry = next(entry for entry in browser.entries if not entry.container)
                    await browser.activate_entry(entry)
                    self.assertEqual(browser.checked_entries, {entry.identity})
                    self.assertEqual(drawer.file_selection_count.text, '1 selected')
                    self.assertEqual(back.accessible_name, 'Exit selection')
                    drawer.back_action()()
                    self.assertFalse(browser.checked_entries)
                    self.assertEqual(back.accessible_name, 'Back to Libraries')
                    self.assertTrue(await drawer.up())

        app.loop.run_until_complete(exercise())

    def test_library_bulk_actions_return_to_the_current_folder(self):
        app = self.app
        app.set_feature_enabled('archives', True, refresh=False)
        app.show_documents_hub()

        async def exercise():
            await app.hub_controller().browse_document_library(
                'Local files', provider=LocalFiles(self.root), folder='', title='Fixture', category='books')
            drawer = app.adaptive.browsers['documents']
            browser = drawer.browser
            picker = app.editor_picker()

            async def select_file():
                drawer.begin_file_selection()
                entry = next(entry for entry in browser.entries if entry.label == 'Needle.txt')
                await browser.activate_entry(entry)

            await select_file()
            await drawer.create_file_archive()
            await picker.confirm_editor_file()
            self.assertTrue((self.root / 'Archive.zip').is_file())
            self.assertIs(app.routes.body().children[0], drawer.page)

            await select_file()
            await drawer.move_checked_files()
            picker.cancel_text_destination()
            self.assertIs(app.routes.body().children[0], drawer.page)

            await select_file()
            await drawer.move_checked_files()
            await picker.browser_editor_location((picker.save_as_storage.value, 'Needle folder'))
            await picker.confirm_editor_file()
            self.assertIs(app.routes.body().children[0], drawer.page)
            self.assertEqual(drawer.status.value, 'Move finished.')
            self.assertFalse((self.root / 'Needle.txt').exists())

            await drawer.open_folder({'path': 'Needle folder'})
            await select_file()
            with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
                await drawer.delete_checked_files()
            self.assertFalse((self.root / 'Needle folder/Needle.txt').exists())
            self.assertIs(app.routes.body().children[0], drawer.page)
            self.assertEqual(drawer.folder, 'Needle folder')

        app.loop.run_until_complete(exercise())

    def test_cancelled_checkpoint_keeps_the_existing_search_scope_and_results(self):
        app = self.app
        app.show_documents_hub()
        panel = app.open_document_search()
        hub = app.hub_controller()
        with patch.object(app, 'checkpoint', return_value=False):
            self.assertFalse(hub.open_document_search(destination='files', scope='copies'))
        self.assertIs(hub._document_search_route, panel)
        self.assertTrue(panel.active)
        self.assertIsNone(hub._documents_file_search.scope)
        panel.close()
