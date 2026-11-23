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
        self.assertEqual(list(app.document_view_buttons), ['Libraries', 'Favourites', 'Open', 'Recent'])
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
        self.assertEqual(list(app.document_results.children), [app.document_search_results])
        self.assertIsNone(app.document_views.parent)
        self.assertTrue(app.routes.system_back())
        self.assertEqual(app.native_host.state.destination, 'documents')
        self.assertIsNone(app.document_search.parent)
        self.assertEqual(list(app.document_results.children), [app.document_recent_list])
        self.assertIsNotNone(app.document_views.parent)
        self.assertFalse(app.documents_search_open)

    def test_matching_folders_and_filename_rows_have_browser_actions(self):
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
        self.assertEqual(len(menus), len(hits))
        self.assertTrue(all('Show in folder' in [name for name, _ in menu.load_actions()] for menu in menus))
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
        checked = [count for count, _, _, _ in progress]
        self.assertEqual(checked, sorted(checked))
        self.assertEqual(checked[-1], 20)
        self.assertIn('refreshing', [phase for _, phase, _, _ in progress])
        self.assertEqual(list(dict.fromkeys(location for _, _, _, location in progress)), list(providers))
        self.assertTrue(any(0 < len(preview) < len(hits) for _, _, preview, _ in progress))
        self.assertTrue(all(hits[:len(preview)] == list(preview) for _, _, preview, _ in progress))
        self.assertEqual({hit['location'] for hit in hits}, set(providers))
        self.assertTrue(all(hit['name'] == 'Needle.md' for hit in hits))
        self.assertEqual(next(hit['source'] for hit in hits if hit['private']), dict(
            type='crypt', remote='Fixture', identity='a' * 64, namespace='b' * 64,
            key='One/Two/Three/Needle.md'))
        self.assertFalse(list(base.rglob('*.sqlite*')))
        self.assertTrue(crypt.closed)

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
        app.document_search.value = 'unique filename'
        self.assertIsNone(app.document_views.parent)
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
        self.assertEqual(hub._document_collection_title.text, 'Recent')
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
            self.assertEqual([len(row.children) for row in app.document_views.children], [2, 2])
            width.return_value = 350
            app.reflow_documents_hub()
            self.assertEqual(len(app.document_views.children), 1)
            self.assertEqual(app.document_view_buttons['Recent']._impl._surface_roles[:2],
                             ('transparent', 'accent'))

            width.return_value = 600
            app.reflow_documents_hub()
            self.assertEqual(body.style.direction, ROW)
            self.assertEqual(nav.style.width, 160)
            self.assertEqual(app.document_view_buttons['Recent']._impl._surface_roles[:2],
                             ('hover', 'accent'))

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

    def test_replaced_query_and_credentials_cannot_publish_late_worker(self):
        app = self.app
        app.show_documents_hub()
        started, release = Event(), Event()
        def slow(*args, **kwargs):
            kwargs['progress'](4501, 'cached', (), 'Fixture - Encrypted Copy')
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
                self.assertIn('cached LocalCrypt names', app.hub_controller()._documents_search_status.text)
                self.assertIn('Fixture - Encrypted Copy', app.hub_controller()._documents_search_status.text)
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
        from mobile_build.tests.workspace.test_hub_documents import widgets

        app = self.app
        app.show_documents_hub()
        hub = app.hub_controller()
        hub.clear_document_search_results()

        def hit(name):
            return dict(name=name, path=name, location='Local files', private=False, directory=False,
                        source=dict(type='local', path=str(app.private_root / name)))

        first, second = hit('Zulu.txt'), hit('Alpha.txt')
        hub.show_document_search_progress(5, '', (first,))
        group = hub._document_search_group
        original = group.children[0]
        hub.show_document_search_progress(9, '', (first, second))
        hub.publish_document_search([first, second], [])
        self.assertIs(group.children[0], original)
        self.assertEqual([w.text for w in widgets(group) if isinstance(w, toga.Button) and w.text.endswith('.txt')],
                         ['Zulu.txt', 'Alpha.txt'])
        self.assertEqual(hub._documents_search_status.text, '2 matches')

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
        app.show_documents_hub()
        app.document_view_buttons['Libraries'].on_press()
        async def wait():
            await app._notes_discovery_task
            await app.hub_controller()._document_comics_discovery
            await app.hub_controller()._document_books_discovery
        app.loop.run_until_complete(wait())
        from mobile_build.tests.workspace.test_hub_documents import widgets, labels
        import toga
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
        app.loop.run_until_complete(book_rows[0].on_press())
        self.assertEqual(app.file_storage.value, 'Shared files')
        self.assertEqual(app.file_path, 'Calibre')
        app.loop.run_until_complete(book_rows[-1].on_press())
        self.assertEqual(app.native_host.state.destination, 'files')
        self.assertEqual(app.file_storage.value, 'Local files')
        self.assertEqual(app.file_path, 'One/More Books')
        author = next(row for row in app.file_rows.values() if row['directory'])
        app.loop.run_until_complete(app.browser_file_folder(author))
        book = next(row for row in app.file_rows.values() if row['directory'])
        app.loop.run_until_complete(app.browser_file_folder(book))
        app.browser_file_selected(next(row for row in app.file_rows.values() if row['name'] == epub.name))
        self.assertTrue(app.loop.run_until_complete(app.read_managed_file()))
        self.assertEqual(app.private_sessions.active.crypt_reader.kind, '.epub')

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
        rows = app.document_notes_list.children[1]
        button, = rows.children
        self.assertEqual(button.text, 'Vault')
        self.assertIn('Vault - Encrypted Copy / Projects', button.accessible_name)
        self.assertIn(('storage_unlocked', 'Encrypted library, unlocked'), button.leading_icons)

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
