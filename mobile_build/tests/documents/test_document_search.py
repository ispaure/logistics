"""The Documents hub searches local filenames and rejects stale private results."""
import asyncio
from threading import Event
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from commonUtils.testing.stages import TestStage
from commonUtils.runtime.resources.local import LocalFiles
from mobile.document_search import scan_local_documents
from mobile_build.tests.support.app import create_app

TEST_STAGE = TestStage.REGRESSION


class LocalDocumentSearchTests(TestCase):
    def setUp(self):
        self.app = create_app(self)

    def test_libraries_default_and_heart_opens_and_removes_existing_favourites(self):
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
        self.assertEqual(list(app.document_view_buttons), ['Libraries', 'Favourites', 'Open', 'Recent', 'Saved'])
        self.assertEqual(list(app.document_results.children), [app.document_libraries_list])
        heart = app.document_view_buttons['Favourites']
        self.assertEqual(heart.accessible_name, 'Favourites')
        self.assertEqual(heart.control_icon, 'favourite')
        self.assertEqual(heart.style.width, 48)
        heart.on_press()
        self.assertEqual(list(app.document_results.children), [app.document_favourites_list])
        button = next(w for w in widgets(app.document_favourites_list)
                      if isinstance(w, toga.Button) and w.text == path.name)
        app.loop.run_until_complete(button.on_press())
        self.assertEqual(app.native_host.state.destination, 'documents')
        self.assertIn('Pinned favourite', app.private_sessions.active.crypt_reader.text)
        app.show_documents_hub()
        remove = next(w for w in widgets(app.document_favourites_list)
                      if isinstance(w, toga.Button) and w.text == 'Remove')
        app.loop.run_until_complete(remove.on_press())
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
        self.assertFalse(any(isinstance(w, toga.Label) and 'Nested/' in w.text for w in rows))
        menus = [w._document_search_menu for w in rows if hasattr(w, '_document_search_menu')]
        self.assertEqual(len(menus), len(hits))
        self.assertTrue(all('Show in folder' in [name for name, _ in menu.raw_actions] for menu in menus))
        app.hub_controller().clear_document_search_results()
        self.assertTrue(all(menu.disposed for menu in menus))

    def test_recursive_local_shared_received_and_unlocked_crypt_names_only(self):
        app = self.app
        base = app.private_root / 'search-fixture'
        providers = {}
        for label in ('Local files', 'Shared files', 'Received Files', 'LocalCrypt: Fixture'):
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
        providers['LocalCrypt: Fixture'] = crypt
        with (patch.object(app, 'ordinary_file_roots', return_value={label: p for label, p in providers.items() if not p.private}),
              patch.object(app, 'existing_crypt_locations', return_value={'LocalCrypt: Fixture': crypt}),
              patch.object(app, 'linked_crypt_locations', return_value={}),
              patch.object(app, 'storage_provider', side_effect=lambda label, roots: roots[label]),
              patch.object(LocalFiles, 'open', side_effect=AssertionError('Search read file content'))):
            hits, failures = scan_local_documents(app, 'nEeDlE')
        self.assertFalse(failures)
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
        async def wait():
            await asyncio.sleep(.35)
            await app.hub_controller()._documents_file_search.task
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
        parent = app.document_views.parent
        self.assertEqual(parent.children.index(app.document_views),
                         parent.children.index(app._documents_status_row) + 1)
        self.assertEqual(list(app.document_results.children), [app.document_recent_list])

    def test_replaced_query_and_credentials_cannot_publish_late_worker(self):
        app = self.app
        app.show_documents_hub()
        started, release = Event(), Event()
        def slow(*args, **kwargs):
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
                with patch.object(app, 'cloud_client', SimpleNamespace(generation=2)):
                    release.set()
                    await owner.task
            self.assertEqual(published, [])
        try:
            app.loop.run_until_complete(run())
        finally:
            release.set()

    def test_libraries_are_two_direct_lists_with_deep_notes(self):
        app = self.app
        from services.documents.locations import collection_path
        root = collection_path(app.private_root) / 'One/Two/Three/Vault'
        (root / '.obsidian').mkdir(parents=True)
        (root / 'Note.md').write_text('# Note')
        app.show_documents_hub()
        app.document_view_buttons['Libraries'].on_press()
        async def wait():
            await app._notes_discovery_task
            await app.hub_controller()._document_comics_discovery
        app.loop.run_until_complete(wait())
        from mobile_build.tests.workspace.test_hub_documents import widgets, labels
        import toga
        self.assertEqual([w.text for w in app.document_notes_list.children if isinstance(w, toga.Label)][:1], ['Notes'])
        self.assertEqual(labels(app.document_comics_list)[0], 'Comics')
        self.assertIn('Vault', [w.text for w in widgets(app.document_libraries_list) if isinstance(w, toga.Button)])
        self.assertFalse(any(getattr(w, 'text', '') in ('Refresh libraries', 'Open Books & Comics library')
                             for w in widgets(app.document_libraries_list)))

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

    def test_short_vertical_bar_keeps_unlock_and_both_file_commands_reachable(self):
        app = self.app
        with patch.object(app, 'home_unlock_candidates', return_value=[('fixture', {})]):
            app.show_documents_hub()
            root = app.body.children[0]
            child, parent = object(), object()
            adapter = SimpleNamespace(parent=parent, content_controller=lambda destination: child)
            with (patch.object(app.native_host, 'adapter', adapter),
                  patch('mobile.ios_toolbar.vertical_edge', return_value=2),
                  patch('mobile.ios_toolbar.supplemental_fits', return_value=False) as capacity):
                actions = root._ios_toolbar_buttons()
            capacity.assert_called_once_with(child, 4)
            self.assertEqual([button.accessible_name for button in actions],
                             ['Unlock LocalCrypt', 'Document actions'])
            self.assertEqual([label for label, _ in root._destination_action_menu.actions],
                             ['Open document', 'New document', 'Search documents'])
