"""The Documents hub searches local filenames and rejects stale private results."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
from threading import Event
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from commonUtils.testing.stages import TestStage
from commonUtils.testing.waiting import wait_until
from commonUtils.runtime.resources.local import LocalFiles
from mobile.document_search import scan_local_documents
from mobile_build.tests.support.app import create_app

TEST_STAGE = TestStage.REGRESSION


class LocalDocumentSearchTests(TestCase):
    def setUp(self):
        self.app = create_app(self)

    def test_note_search_opening_remembers_one_choice_for_the_whole_library(self):
        from unittest.mock import AsyncMock, patch
        from mobile.obsidian import open_search_note

        app = self.app
        root = app.private_root / 'search-note-fixture'
        (root / 'Vault/.obsidian').mkdir(parents=True)
        (root / 'Vault/Sub').mkdir()
        for name in ('One.md', 'Two.md'):
            (root / 'Vault/Sub' / name).write_text('# Test')
        provider = LocalFiles(root)
        regular = AsyncMock(return_value=True)
        owner = AsyncMock()
        owner.open_note.return_value = True
        dialog = AsyncMock(return_value='remember-notes')
        with patch.object(app.main_window, 'dialog', dialog), \
                patch('mobile.obsidian.open_vault', new=AsyncMock(return_value=owner)) as vault:
            for name in ('One.md', 'Two.md'):
                result = app.loop.run_until_complete(open_search_note(app, provider, 'Vault/Sub/' + name, regular=regular))
                self.assertTrue(result)
            dialog.assert_awaited_once()
            self.assertEqual(app.preferences.values['notes_search_open'], 'notes')
            self.assertEqual(vault.await_args.args[2], 'Vault')
            self.assertEqual(owner.open_note.await_args.args, ('Vault/Sub/Two.md',))
            regular.assert_not_awaited()
            app.preferences.save(notes_search_open='viewer')
            self.assertTrue(app.loop.run_until_complete(open_search_note(app, provider, 'Vault/Sub/One.md', regular=regular)))
            regular.assert_awaited_once()

    def test_local_epub_thumbnail_uses_the_provider_content_revision(self):
        from base64 import b64decode, b64encode
        from unittest.mock import Mock
        from mobile.browser_preview import LocalThumbnails
        from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books, png_page

        path, _ = make_books(self.app.private_root, embed_cover=True)
        provider = LocalFiles(path.parent)
        bridge = Mock(supports_streaming=True)
        bridge.request.return_value = {'data': b64encode(png_page()).decode()}
        result = LocalThumbnails(provider, bridge, '').load(provider.entry(path.name), (80, 80), lambda: False)
        self.assertEqual(result, png_page())
        self.assertEqual(bridge.request.call_args.args, ('image_thumbnail',))
        self.assertEqual(b64decode(bridge.request.call_args.kwargs['data']), png_page())

    def test_libraries_default_and_favourites_opens_and_removes_existing_entries(self):
        import toga
        from mobile.favourites import catalog
        from mobile_build.tests.workspace.test_hub_documents import widgets
        from services.documents.locations import collection_path
        app = self.app
        self.assertEqual(app.documents_view, 'Libraries')
        path = collection_path(app.private_root) / 'Pinned.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('# Pinned favourite')
        catalog(app).remember(dict(type='local', path=str(path)), path.name,
                              dict(kind='markdown'), favourite=True)
        app.show_documents_hub()
        self.assertEqual(list(app.document_view_buttons), ['Libraries', 'Favourites', 'Recent'])
        self.assertEqual(list(app.document_results.children), [app.document_libraries_list])
        favourites = app.document_view_buttons['Favourites']
        self.assertEqual(favourites.accessible_name, 'Favourites')
        self.assertEqual(favourites.text, 'Favourites')
        self.assertEqual(favourites.style.height, 48)
        favourites.on_press()
        self.assertEqual(list(app.document_results.children), [app.document_favourites_list])
        button = next(w for w in widgets(app.document_favourites_list)
                      if isinstance(w, toga.Button) and w.text == path.name)
        app.loop.run_until_complete(button.on_press())
        self.assertEqual(app.native_host.state.destination, 'documents')
        self.assertIn('Pinned favourite', app.private_sessions.active.crypt_reader.text)
        app.show_documents_hub()
        favourite_widgets = list(widgets(app.document_favourites_list))
        self.assertFalse(any(isinstance(w, toga.Button) and w.text == 'Remove'
                             for w in favourite_widgets))
        menu, = (w.document_actions for w in favourite_widgets if hasattr(w, 'document_actions'))
        remove = dict(menu.load_actions())['Remove from Favourites']
        app.loop.run_until_complete(remove())
        self.assertEqual(catalog(app).entries(), [])

    def test_search_button_and_android_back_restore_documents_collection(self):
        import toga
        from mobile_build.tests.workspace.test_hub_documents import widgets
        app = self.app
        app.show_documents_hub()
        app.document_view_buttons['Recent'].on_press()
        self.assertIsNone(app.document_search.parent)
        search = next(w for w in widgets(app.body) if isinstance(w, toga.Button)
                      and getattr(w, 'accessible_name', '') == 'Search documents')
        search.on_press()
        self.assertIsNotNone(app.document_search.parent)
        self.assertEqual(list(app.document_results.children), [app.document_recent_list])
        self.assertIsNotNone(app.document_views.parent)
        self.assertTrue(app.routes.screens['documents'][-1][0].startswith('search:'))
        self.assertTrue(app.routes.system_back())
        self.assertEqual(app.native_host.state.destination, 'documents')
        self.assertIsNone(app.document_search.parent)
        self.assertEqual(list(app.document_results.children), [app.document_recent_list])
        self.assertIsNotNone(app.document_views.parent)
        self.assertFalse(app.documents_search_open)

    def test_matching_folders_and_filename_rows_open_directly_without_menus(self):
        import toga
        from mobile_build.tests.workspace.test_hub_documents import widgets
        app = self.app
        from services.documents.locations import collection_path
        root = collection_path(app.private_root)
        (root / 'Nested/Needle folder').mkdir(parents=True)
        (root / 'Nested/Needle.md').write_text('body')
        hits, failures = scan_local_documents(app, 'needle')
        self.assertFalse(failures)
        folder = next(hit for hit in hits if hit['name'] == 'Needle folder')
        self.assertTrue(folder['directory'])
        app.show_documents_hub()
        app.publish_document_search(hits, [])
        rows = list(widgets(app.document_search_results))
        titles = [w for w in rows if isinstance(w, toga.Button) and w.text in {hit['name'] for hit in hits}]
        self.assertEqual(len(titles), len(hits))
        self.assertTrue(all(button.style.flex == 1 for button in titles))
        self.assertFalse(any(isinstance(w, toga.Label) and 'Nested/' in w.text for w in rows))
        menus = [w.document_actions for w in rows if hasattr(w, 'document_actions')]
        self.assertEqual(menus, [])
        app.hub_controller().clear_document_search_results()
        self.assertTrue(all(menu.disposed for menu in menus))

    def test_recursive_local_shared_received_and_unlocked_crypt_names_only(self):
        app = self.app
        base = app.private_root / 'search-fixture'
        providers = {}
        for label in ('Local files', 'Shared files', 'Received Files', 'Fixture - Encrypted Copy'):
            root = base / label
            (root / 'One/Two/Three').mkdir(parents=True)
            (root / 'One/Two/Three/Needle.md').write_text('contents never searched')
            (root / 'Different.txt').write_text('Needle')
            providers[label] = LocalFiles(root)
        from features.rclone.localcrypt.mobile.resources import CryptFiles
        from mobile_build.tests.transfers.test_localcrypt_access import Client
        crypt = CryptFiles(base / 'ciphertext', Client(), 'Fixture', namespace='b' * 64)
        (crypt.root / 'One/Two/Three').mkdir(parents=True)
        (crypt.root / 'One/Two/Three/Needle.md').write_bytes(b'opaque cipher fixture')
        (crypt.root / 'Different.txt').write_bytes(b'opaque cipher fixture')
        providers['Fixture - Encrypted Copy'] = crypt
        progress = []
        with (patch.object(app, 'ordinary_file_roots', return_value={label: p for label, p in providers.items() if not p.private}),
              patch.object(app, 'existing_crypt_locations', return_value={'Fixture - Encrypted Copy': crypt}),
              patch.object(app, 'linked_crypt_locations', return_value={}),
              patch.object(app, 'storage_provider', side_effect=lambda label, roots: roots[label]),
              patch.object(LocalFiles, 'open', side_effect=AssertionError('Search read file content'))):
            hits, failures = scan_local_documents(
                app, 'nEeDlE', progress=lambda *update: progress.append(update))
        self.assertFalse(failures)
        from itertools import groupby

        def group(update):
            _, phase, _, location = update
            return location, phase in ('cached_hints', 'crypt_cached_hints')

        storage_counts = []
        for (_, cache_pass), updates in groupby(progress, group):
            checked = [count for count, _, _, _ in updates]
            self.assertEqual(checked[0], 0)
            self.assertEqual(checked, sorted(checked))
            if not cache_pass:
                storage_counts.append(checked[-1])
        self.assertEqual(storage_counts, [5, 5, 5, 5])
        self.assertIn('refreshing', [phase for _, phase, _, _ in progress])
        self.assertEqual(list(dict.fromkeys(location for _, phase, _, location in progress
                                            if phase != 'crypt_cached_hints')),
                         ['Local files', 'Shared files', 'Received Files', 'Fixture'])
        self.assertTrue(any(0 < len(preview) < len(hits) for _, _, preview, _ in progress))
        self.assertTrue(all(hits[:len(preview)] == list(preview) for _, _, preview, _ in progress))
        self.assertEqual({hit['location'] for hit in hits}, set(providers))
        self.assertTrue(all(hit['name'] == 'Needle.md' for hit in hits))
        self.assertEqual(next(hit['source'] for hit in hits if hit['private']), dict(
            type='crypt', remote='Fixture', identity='a' * 64, namespace='b' * 64,
            key='One/Two/Three/Needle.md'))
        self.assertFalse(list(base.rglob('*.sqlite*')))
        self.assertTrue(crypt.closed)

    def test_verified_cache_hits_publish_before_live_scan_and_deleted_names_are_refreshed(self):
        from mobile.local_sources import PhoneFiles
        from services.documents.locations import MobileLocalFiles
        from mobile.document_search import _scan_locations

        app = self.app
        phone = PhoneFiles(app.private_root)
        copy_root = app.private_root / 'test-copy'
        copy_root.mkdir()
        copies = MobileLocalFiles(copy_root)
        roots = {'On this device': phone, 'Rclone Copies': copies}
        (phone.root / 'old-needle.txt').touch()
        (copies.root / 'cached-needle.txt').touch()
        with (patch.object(app, 'storage_provider', side_effect=lambda label, roots: roots[label]),
              patch.object(app, 'feature_enabled', return_value=False)):
            def scan(progress=None):
                hits, failures = _scan_locations(app, roots, 'needle',
                                                cancelled=lambda: False, progress=progress)
                self.assertEqual(failures, [])
                return [hit['path'] for hit in hits]

            self.assertEqual(scan(), ['old-needle.txt', 'cached-needle.txt'])
            (phone.root / 'old-needle.txt').unlink()
            (phone.root / 'new-needle.txt').touch()
            progress = []
            with patch.object(copies, 'entry', wraps=copies.entry) as validate:
                self.assertEqual(scan(lambda *row: progress.append(row)),
                                 ['cached-needle.txt', 'new-needle.txt'])
                validate.assert_called_once_with('cached-needle.txt')
            first = next((phase, [hit['path'] for hit in hits]) for _, phase, hits, _ in progress if hits)
            self.assertEqual(first, ('cached_hints', ['cached-needle.txt']))
            with patch.object(phone, 'entry', wraps=phone.entry) as validate:
                self.assertEqual(set(scan()), {'cached-needle.txt', 'new-needle.txt'})
                validate.assert_called_once_with('new-needle.txt')

    def test_notes_documents_and_browser_reuse_one_physical_folder_snapshot(self):
        from contextlib import closing
        from sqlite3 import connect
        from features.notes_library import library_files
        from mobile.browser_ui import FileBrowser
        from mobile.document_search import _scan_locations
        from mobile.local_sources import PhoneFiles
        from mobile.obsidian import VaultBrowser

        app = self.app
        phone = PhoneFiles(app.private_root)
        folder = phone.root / 'Vault'
        folder.mkdir()
        (folder / 'Needle.md').write_text('a separate body phrase')
        (phone.root / 'Outside Needle.md').touch()
        # Notes can open a provider rooted directly at the same physical
        # folder that Workspaces sees as a child of On My Phone.
        library_provider = LocalFiles(folder)
        notes = VaultBrowser(app, library_provider, '', 'files')
        browser = FileBrowser()
        self.addCleanup(notes.dispose)
        self.addCleanup(lambda: app.loop.run_until_complete(browser.close()))
        warm = browser.local_search.search(phone, 'Vault', 'needle')
        self.assertEqual([row['path'] for row in warm.rows], ['Vault/Needle.md'])

        from services.documents import locations
        listing = locations.local_folder_snapshot
        def cold_only(provider, path, **kwargs):
            if provider.root / path == folder:
                self.fail('The already indexed physical folder was scanned again')
            return listing(provider, path, **kwargs)

        with (patch.object(locations, 'local_folder_snapshot', side_effect=cold_only),
              patch('mobile.device_name_cache.local_folder_snapshot', side_effect=cold_only),
              patch.object(app, 'storage_provider', side_effect=lambda label, roots: roots[label]),
              patch.object(app, 'feature_enabled', return_value=False)):
            note_hits = library_files.search(notes.library, 'needle', include_text=False)
            body_hits = library_files.search(notes.library, 'separate body phrase', include_text=True)
            global_hits, failures = _scan_locations(app, {'On My Phone': phone}, 'needle',
                                                    cancelled=lambda: False, progress=None)
        self.assertEqual([row['path'] for row in note_hits.rows], ['Needle.md'])
        self.assertEqual([row['path'] for row in body_hits.rows], ['Needle.md'])
        self.assertEqual({hit['path'] for hit in global_hits}, {'Vault/Needle.md', 'Outside Needle.md'})
        self.assertEqual(failures, [])
        cache = app.private_root / 'Cache'
        self.assertFalse((cache / 'directory-index.sqlite3').exists())
        with closing(connect(cache / 'device-filenames.sqlite3')) as database:
            self.assertEqual(database.execute('SELECT count(*) FROM folders WHERE path = ?',
                                              (str(folder),)).fetchone()[0], 1)

    def test_search_replaces_views_opens_disk_file_and_clear_restores_collection(self):
        app = self.app
        from services.documents.locations import collection_path
        path = collection_path(app.private_root) / 'Deep/Unique filename.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('# Opened from a file search')
        app.show_documents_hub()
        self.assertFalse(hasattr(app.body.children[0], '_workspace_frame'))
        self.assertEqual(app.document_search.placeholder, 'Search local documents')
        app.document_view_buttons['Recent'].on_press()
        app.open_document_search()
        app.document_search.value = 'unique filename'
        self.assertIsNotNone(app.document_views.parent)
        search = app.hub_controller()._documents_file_search

        async def wait():
            task = await wait_until(lambda: search.task, timeout=5, interval=.01,
                                    message='Filename query did not start a document search task')
            await wait_until(task.done, timeout=5, interval=.01,
                             message='Filename search task did not complete')
            await task

        app.loop.run_until_complete(wait())
        from mobile_build.tests.workspace.test_hub_documents import widgets
        import toga
        result = next(w for w in widgets(app.document_search_results)
                      if isinstance(w, toga.Button) and w.text == path.name)
        app.loop.run_until_complete(result.on_press())
        self.assertEqual(app.native_host.state.destination, 'documents')
        self.assertIn('Opened from a file search', app.private_sessions.active.crypt_reader.text)
        app.show_documents_hub()
        app.document_search.value = ''
        self.assertIsNotNone(app.document_views.parent)
        hub = app.hub_controller()
        self.assertIs(app.document_views.parent, hub._document_collection_header)
        self.assertFalse(any(getattr(child, 'text', None) == 'Recent'
                             for child in hub._document_results_pane.children))
        self.assertEqual(list(app.document_results.children), [app.document_recent_list])

    def test_collections_keep_their_rows_and_controls_across_width_and_fold_changes(self):
        from mobile.fold_layout import Division
        from toga.style.pack import COLUMN, ROW

        app = self.app
        app.show_documents_hub()
        hub = app.hub_controller()
        controls = list(app.document_view_buttons.values())
        app.document_view_buttons['Recent'].on_press()
        body = hub._document_collection_body
        nav = hub._document_collection_navigation
        detail = hub._document_collection_detail
        with (patch.object(app.adaptive, 'content_width', return_value=260) as width,
              patch('mobile.fold_layout.division', return_value=None) as fold):
            app.reflow_documents_hub()
            self.assertEqual(body.style.direction, COLUMN)
            self.assertEqual([len(row.children) for row in app.document_views.children], [2, 1])
            width.return_value = 350
            app.reflow_documents_hub()
            self.assertEqual(len(app.document_views.children), 1)
            self.assertEqual(app.document_view_buttons['Recent']._impl._surface_roles[:2],
                             ('hover', 'text'))

            width.return_value = 600
            app.reflow_documents_hub()
            self.assertEqual(body.style.direction, COLUMN)
            self.assertEqual(app.document_views.children[0].style.direction, ROW)
            self.assertEqual(app.document_view_buttons['Recent']._impl._surface_roles[:2],
                             ('hover', 'text'))

            fold.return_value = Division(x=278, y=0, width=27, height=400)
            app.reflow_documents_hub()
            self.assertEqual(nav.style.width, 278)
            self.assertEqual(detail.style.margin_left, 27)

            fold.return_value = Division(x=0, y=210, width=600, height=22)
            app.reflow_documents_hub()
            self.assertEqual(body.style.direction, COLUMN)
            self.assertEqual(nav.style.height, 210)
            self.assertEqual(detail.style.margin_top, 22)
            self.assertEqual(detail.style.margin_left, 0)

            fold.return_value = None
            width.return_value = 350
            app.reflow_documents_hub()
            self.assertEqual(detail.style.margin_top, 0)
            self.assertEqual(list(app.document_view_buttons.values()), controls)
            self.assertEqual(list(app.document_results.children), [app.document_recent_list])

    def test_rotating_collections_and_opening_search_hide_the_inactive_native_pane(self):
        from unittest.mock import Mock

        app = self.app
        app.show_documents_hub()
        hub = app.hub_controller()
        results = hub._document_results_scroll
        companion = hub._document_companion
        with (patch.object(app.adaptive, 'content_width', return_value=900) as width,
              patch('mobile.fold_layout.division', return_value=None),
              patch.object(results._impl, 'set_hidden', Mock()) as hide_results,
              patch.object(companion._impl, 'set_hidden', Mock()) as hide_companion):
            app.reflow_documents_hub()
            hide_results.assert_called_with(True)
            hide_companion.assert_called_with(False)
            self.assertIs(app.document_results.parent, hub._document_collection_header)
            self.assertEqual(list(hub._document_collection_detail.children),
                             [app._documents_status_row, companion])

            # A compact portrait layout must not leave the empty browser's
            # native frame painted over the now full-height collection list.
            width.return_value = 440
            app.reflow_documents_hub()
            hide_results.assert_called_with(False)
            hide_companion.assert_called_with(True)
            self.assertEqual(list(companion.children), [])
            self.assertIs(app.document_results.parent, hub._document_results_pane)
            self.assertEqual(list(hub._document_collection_detail.children),
                             [app._documents_status_row, results])

            width.return_value = 900
            app.reflow_documents_hub()
            hide_results.assert_called_with(True)
            hide_companion.assert_called_with(False)
            app._documents_status_row.add(app.document_search)
            app.reflow_documents_hub()
            hide_results.assert_called_with(False)
            hide_companion.assert_called_with(True)
            self.assertEqual(list(companion.children), [])
            self.assertIs(app.document_results.parent, hub._document_results_pane)

    def test_replaced_query_and_credentials_cannot_publish_late_worker(self):
        app = self.app
        app.show_documents_hub()
        started, release = Event(), Event()
        def slow(*args, **kwargs):
            kwargs['progress'](4501, 'cached', (), 'Fixture')
            started.set()
            release.wait(4)
            return [dict(name='Private stale.md')], []
        owner = app.hub_controller()._documents_file_search
        published = []
        owner.publish = lambda *args: published.append(args)
        async def run():
            app.documents_query = 'private'
            with patch('mobile.document_search.scan_local_documents', side_effect=slow):
                owner.start('private')
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                await wait_until(lambda: '4,501 checked' in app.hub_controller()._documents_search_status.text,
                                 timeout=2, interval=.01, message='No progress in the Documents status row')
                self.assertIn('Checking folders for changes', app.hub_controller()._documents_search_status.text)
                hub = app.hub_controller()
                self.assertEqual(hub._documents_search_location.text, 'Fixture')
                self.assertEqual(list(hub._documents_search_header.children),
                                 [hub._documents_search_location, hub._documents_search_status])
                with patch.object(app, 'cloud_client', SimpleNamespace(generation=2)):
                    release.set()
                    await owner.task
            self.assertEqual(published, [])
        try:
            app.loop.run_until_complete(run())
        finally:
            release.set()

    def test_document_search_appends_hits_without_replacing_or_resorting_rows(self):
        import toga
        from mobile.ui_metrics import WRAPPED_FILENAME_ROW_HEIGHT
        from mobile_build.tests.workspace.test_hub_documents import widgets

        app = self.app
        app.show_documents_hub()
        hub = app.hub_controller()
        hub.clear_document_search_results()

        def hit(name):
            return dict(name=name, path=name, location='Local files', private=False, directory=False,
                        source=dict(type='local', path=str(app.private_root / name)))

        first = hit('Zulu - A long filename that needs to wrap in a narrow viewport.txt')
        second = hit('Alpha.txt')
        hub.show_document_search_progress(5, 'cached_hints', (first,), 'Local files')
        self.assertEqual(hub._documents_search_status.text, 'Searching saved filenames… · 5 checked')
        group = hub._document_search_group
        original = group.children[0]
        hub.show_document_search_progress(9, '', (first, second))
        hub.publish_document_search([first, second], [], checked_localcrypt_cache=True)
        self.assertIs(group.children[0], original)
        buttons = [w for w in widgets(group) if isinstance(w, toga.Button) and w.text.endswith('.txt')]
        self.assertEqual([button.text for button in buttons], [first['name'], second['name']])
        self.assertEqual(buttons[0].accessible_name, first['name'])
        self.assertEqual(buttons[0].style.height, WRAPPED_FILENAME_ROW_HEIGHT)
        self.assertEqual([button.parent.style.margin_bottom for button in buttons], [0, 0])
        self.assertEqual(hub._documents_search_status.text, '2 matches · LocalCrypt cache checked')

    def test_libraries_have_direct_lists_with_bounded_discovery(self):
        app = self.app
        from services.documents.locations import collection_path
        from services.documents.migrations.mobile_layout import prepare_android
        from services.documents.mobile_locations import _enabled, phone_path
        from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
        self.addCleanup(_enabled.discard, app.private_root)
        prepare_android(app.private_root)
        copies = collection_path(app.private_root)
        root = copies / 'One/Vault'
        (root / '.obsidian').mkdir(parents=True)
        # Library discovery is bounded; note paths inside a library are not.
        note = root / 'Two/Three/Note.md'
        note.parent.mkdir(parents=True)
        note.write_text('# Note')
        (root.parent / 'Two/Three/TooDeep/.obsidian').mkdir(parents=True)
        device_library = phone_path(app.private_root) / 'Calibre'
        for book_library in (device_library, copies / 'One/More Books', copies / 'One/Two/Too Deep'):
            book_library.mkdir(parents=True)
            (book_library / 'metadata.db').touch()
        (root.parent / 'Fake Books/metadata.db').mkdir(parents=True)
        book_folder = root.parent / 'More Books/Author/Book'
        book_folder.mkdir(parents=True)
        epub, _ = make_books(book_folder)
        (root.parent / 'Local Comics').mkdir()
        (root.parent / 'remoteConfig.ini').write_text('[LogisticsComics]\nlibraries=Local Comics\n')
        app.show_documents_hub()
        app.document_view_buttons['Libraries'].on_press()
        from mobile_build.tests.workspace.test_hub_documents import widgets, labels
        import toga
        for section, title, status_size in ((app.document_notes_list, 'Notes', 12),
                                             (app.document_books_list, 'Books', 13),
                                             (app.document_comics_list, 'Comics', 13)):
            heading = next(w for w in widgets(section) if getattr(w, 'text', '') == title)
            self.assertEqual(labels(heading.parent), [title, '– Looking for libraries…'])
            self.assertEqual(heading.style.font_size, 19)
            self.assertEqual(heading.parent.children[1].style.font_size, status_size)
        async def wait():
            await app._notes_discovery_task
            await app.hub_controller()._document_comics_discovery
            await app.hub_controller()._document_books_discovery
        app.loop.run_until_complete(wait())
        self.assertEqual([w.text for w in app.document_notes_list.children if isinstance(w, toga.Label)][:1], ['Notes'])
        self.assertEqual(labels(app.document_comics_list)[0], 'Comics')
        self.assertEqual(labels(app.document_books_list), ['Books'])
        book_rows = [w for w in widgets(app.document_books_list) if isinstance(w, toga.Button)]
        self.assertEqual([row.text for row in book_rows], ['Calibre', 'More Books'])
        libraries = [w.text for w in widgets(app.document_libraries_list) if isinstance(w, toga.Button)]
        self.assertIn('Vault', libraries)
        self.assertNotIn('TooDeep', libraries)
        from features.notes_library.notes import NotesLibrary
        from services.documents.locations import CollectionFiles
        library = NotesLibrary(CollectionFiles(app.private_root), 'One/Vault')
        self.addCleanup(library.close)
        self.assertEqual(library.read_text('One/Vault/Two/Three/Note.md'), '# Note')
        self.assertFalse(any(getattr(w, 'text', '') in ('Refresh libraries', 'Open Books & Comics library')
                             for w in widgets(app.document_libraries_list)))
        def assert_library(folder):
            self.assertEqual(app.native_host.state.destination, 'documents')
            drawer = app.adaptive.browser('documents')
            self.assertEqual(drawer.folder, folder)
            self.assertIsNone(drawer.storage.parent)
            return drawer

        async def android_back():
            self.assertTrue(app.routes.system_back())
            if app.routes.back_task is not None:
                await app.routes.back_task
            await asyncio.sleep(0)

        def assert_libraries():
            self.assertEqual(app.native_host.state.destination, 'documents')
            self.assertFalse(app.routes.screens['documents'])
            self.assertEqual(app.documents_view, 'Libraries')

        async def browse():
            await book_rows[0].on_press()
            drawer = assert_library('Calibre')
            self.assertEqual(drawer.parent_button.accessible_name, 'Back to Libraries')
            drawer.parent_button.on_press()
            if app.routes.back_task is not None:
                await app.routes.back_task
            await asyncio.sleep(0)
            assert_libraries()

            comic_row = next(w for w in widgets(app.document_comics_list)
                             if isinstance(w, toga.Button) and w.text == 'Local Comics')
            await comic_row.on_press()
            assert_library('One/Local Comics')
            await android_back()
            assert_libraries()

            await book_rows[-1].on_press()
            drawer = assert_library('One/More Books')
            author = next(entry.payload for entry in drawer.browser.entries if entry.container)
            await drawer.open_folder(author)
            assert_library('One/More Books/Author')
            await android_back()
            assert_library('One/More Books')
            await drawer.open_folder(author)
            book_row = next(entry.payload for entry in drawer.browser.entries if entry.container)
            await drawer.open_folder(book_row)
            file = next(entry.payload for entry in drawer.browser.entries if entry.label == epub.name)
            self.assertTrue(await drawer.open_file(file))

        app.loop.run_until_complete(browse())
        self.assertEqual(app.private_sessions.active.crypt_reader.kind, '.epub')
        self.assertEqual(app.native_host.state.destination, 'documents')

    def test_encrypted_notes_library_displays_its_nested_name_once(self):
        app = self.app
        root = app.private_root / 'encrypted-discovery-fixture'
        (root / 'Projects/Vault/.obsidian').mkdir(parents=True)
        with (patch.object(app, 'existing_crypt_locations', return_value={'Vault - Encrypted Copy': 'Vault'}),
              patch('features.rclone.localcrypt.mobile.resources.encrypted_storage',
                    side_effect=lambda *args, **kwargs: LocalFiles(root))):
            app.show_documents_hub()
            app.document_view_buttons['Libraries'].on_press()
            app.loop.run_until_complete(app._notes_discovery_task)
        from mobile_build.tests.workspace.test_hub_documents import widgets
        button, = (widget for widget in widgets(app.document_notes_list)
                   if getattr(widget, 'text', '') == 'Vault')
        self.assertEqual(button.text, 'Vault')
        self.assertIn('Vault - Encrypted Copy / Projects', button.accessible_name)
        self.assertFalse(getattr(button, 'leading_icons', None))
        self.assertEqual(button._source_caption.children[-1].text, 'Encrypted library')

    def test_unlock_is_last_header_action_and_returns_to_each_origin(self):
        app = self.app
        app.show_cloud(present=False)
        with (patch.object(app, 'home_unlock_candidates', return_value=[('fixture', dict(zip='Fixture.zip'))]),
              patch.object(app.cloud_controller(), 'show_retained_unlock') as unlock):
            for destination, show in [('home', app.show_home), ('files', app.show_locations),
                                      ('documents', app.show_documents_hub)]:
                show()
                root = app.routes.roots[destination].children[0]
                header, buttons = root._destination_actions
                self.assertIs(header.children[-1], buttons[0])
                self.assertEqual(buttons[0].accessible_name, 'Unlock LocalCrypt')
                buttons[0].on_press()
                self.assertEqual(unlock.call_args.kwargs['destination'], destination)
                unlock.call_args.kwargs['resume']()
                self.assertEqual(app.native_host.state.destination, destination)
        with patch.object(app, 'home_unlock_candidates', return_value=[]):
            app.show_documents_hub()
            root = app.routes.roots['documents'].children[0]
            header, buttons = root._destination_actions
            self.assertIsNone(buttons[0].parent)

    def test_apple_toolbar_exposes_current_document_commands(self):
        app = self.app
        with patch.object(app, 'home_unlock_candidates', return_value=[('fixture', {})]):
            app.show_documents_hub()
            root = app.body.children[0]
            actions = root._ios_toolbar_buttons()
            self.assertEqual([button.accessible_name for button in actions],
                             ['New document', 'Search documents', 'Unlock LocalCrypt'])
