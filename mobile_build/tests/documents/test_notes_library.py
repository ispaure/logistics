"""Location actions, bounded remote access and Notes Library document ownership."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import base64
import json
import os
import unittest
import shutil
from unittest.mock import patch
import mobile_build.tests.documents.test_obsidian as test_obsidian
from commonUtils.runtime.resources.local import LocalFiles
from mobile.notes_actions import RemoteNotes, offer_notes
from features.text_editor.notes import NotesLibrary
import toga
from toga.style import Pack


class Client:
    generation = 1
    def __init__(self, root):
        self.files, self.calls = LocalFiles(root), []
    def cancel(self):pass
    def connection_identity(self, remote):return 'identity'
    def entries(self, remote, path=''):
        self.calls.append(('list', path))
        return self.files.list(path)
    def request(self, action, **kw):
        self.calls.append((action, kw.get('path')))
        row = self.files.entry(kw['path'])
        revision = json.dumps(row['revision'])
        if action == 'remote_stat':return dict(size=row['size'], revision=revision)
        if action == 'remote_range':
            if kw['expected'] != revision:raise ValueError('Changed')
            data = (self.files.root / kw['path']).read_bytes()
            return dict(data=base64.b64encode(data[kw['offset']:kw['offset'] + kw['count']]).decode())
        raise AssertionError(action)


class NotesLibraryTests(unittest.TestCase):
    setUp = test_obsidian.ObsidianTests.setUp
    tearDown = test_obsidian.ObsidianTests.tearDown
    run_async = test_obsidian.ObsidianTests.run_async

    def test_documents_discovers_libraries_two_folders_down_without_reading_notes(self):
        from mobile.notes_discovery import find_libraries
        (self.root / 'One/Two/.obsidian').mkdir(parents=True)
        (self.root / 'One/Two/TooDeep/.obsidian').mkdir(parents=True)
        (self.root / '.hidden/.obsidian').mkdir(parents=True)
        provider = LocalFiles(self.root)
        with patch.object(provider, 'open', side_effect=AssertionError('Discovery must not read documents')), \
                patch.object(provider, 'list', wraps=provider.list) as listing:
            found = find_libraries(provider)
        self.assertIn('Vault', found)
        self.assertIn('One/Two', found)
        self.assertNotIn('One/Two/TooDeep', found)
        self.assertNotIn('.hidden', found)
        self.assertFalse(any('.obsidian' in call.args[0] for call in listing.call_args_list))


    def test_favourite_reopens_note_inside_its_library(self):
        from mobile.obsidian import open_vault
        from mobile.favourites import reference, catalog, reopen
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            await owner.open_note('Vault/Home.md')
            source, title, opener, cipher = reference(self.app)
            self.assertIsNone(cipher)
            catalog(self.app).remember(source, title, opener, favourite=True)
            row = catalog(self.app).entries()[0]
            owner.close()
            self.assertTrue(await reopen(self.app, row))
            restored = self.app.vault_browser
            self.assertEqual(restored.path, 'Home.md')
            self.assertEqual(restored.provider.root, self.vault.resolve())
            restored.close()
        self.run_async(exercise())

    def test_system_back_restores_browsing_after_each_document_kind(self):
        from mobile.obsidian import open_vault
        from features.notebooks.notebook import Notebook
        (self.vault / 'Code.json').write_text('{}')
        (self.vault / 'Drawing.rmdoc').write_bytes(Notebook.new('Drawing').to_bytes())
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            for path in ('Vault/Home.md', 'Vault/Code.json', 'Vault/Drawing.rmdoc'):
                owner.sidebar.show_sidebar()
                self.assertTrue(await owner.open_note(path))
                self.assertFalse(owner.sidebar.sidebar_open)
                self.assertEqual(owner.back_action(), owner.return_to_browsing)
                owner.back_action()()
                self.assertEqual(owner.sidebar.side, 'files')
                self.assertIsNone(owner._document_return_side)
                self.assertEqual(owner.back_action(), owner.sidebar.show_detail)
                owner.back_action()()
            owner.close()
        self.run_async(exercise())

    def test_json_and_view_scripts_use_embedded_code_input_and_preserve_source_bytes(self):
        from dataclasses import replace
        from unittest.mock import AsyncMock
        from mobile.obsidian import open_vault
        from commonUtils.ui.native.code_input import CodeInput
        folder = self.vault / '_Resources/dataview'
        folder.mkdir(parents=True)
        path = folder / 'items.json'
        path.write_bytes(b'\xef\xbb\xbf{\r\n  "name": "Original"\r\n}\r\n')
        (folder / 'show.js').write_text('dv.paragraph("Script source");')
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.load_folder('Vault/_Resources/dataview')
            self.assertEqual({row['name'] for row in owner.folders['Vault/_Resources/dataview']}, {'items.json', 'show.js'})
            self.assertTrue(await owner.open_note('Vault/_Resources/dataview/items.json'))
            editor = owner.embedded
            self.assertIsInstance(editor.source, CodeInput)
            self.assertIn(editor.view, owner.article.children)
            editor.source.value = '{\n  "name": "Edited in library"\n}\n'
            editor.changed(editor.source.value)
            self.assertTrue(await editor.save())
            self.assertEqual(path.read_bytes(), b'\xef\xbb\xbf{\r\n  "name": "Edited in library"\r\n}\r\n')
            editor.source.value = '{"draft":true}'
            editor.changed(editor.source.value)
            path.write_text('{"external":true}')
            self.assertFalse(await editor.save())
            self.assertTrue(editor.dirty)
            self.assertEqual(editor.text, '{"draft":true}')
            self.assertEqual(path.read_text(), '{"external":true}')
            with patch.object(owner, 'host', replace(owner.host, confirm=AsyncMock(return_value='cancel'))):
                self.assertFalse(await owner.open_note('Vault/Home.md'))
            self.assertIs(owner.embedded, editor)
            with patch.object(owner, 'host', replace(owner.host, confirm=AsyncMock(return_value='discard'))):
                self.assertTrue(await owner.open_note('Vault/Home.md'))
            self.assertTrue(await owner.open_note('_Resources/dataview/show.js', resolve_link=True))
            self.assertEqual(owner.embedded.text, 'dv.paragraph("Script source");')
            self.assertEqual(owner.embedded.kind, 'text')
            owner.dispose()
            self.assertEqual(editor.text, '')
        self.run_async(exercise())

    def test_data_view_heading_jump_waits_for_generated_content(self):
        from unittest.mock import AsyncMock
        from mobile.obsidian import open_vault
        (self.vault / 'Home.md').write_text('```dataviewjs\ndv.header(2, "Generated target");\n```\n')
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            with patch.object(owner, 'scroll_fragment') as scroll, \
                    patch('features.text_editor.mobile.dataview.execute_views', new=AsyncMock(return_value='## Generated target\n')):
                self.assertTrue(await owner.open_note('Vault/Home.md', fragment='generated-target'))
                owner.page_loaded()
                scroll.assert_not_called()
                self.assertEqual(owner.pending_fragment, 'generated-target')
                await owner.data_view_task
                owner.page_loaded()
                scroll.assert_called_once_with('generated-target')
                self.assertEqual(owner.pending_fragment, '')
        self.run_async(exercise())

    def test_data_view_output_does_not_change_authored_source_and_stale_output_is_discarded(self):
        from unittest.mock import AsyncMock
        from mobile.obsidian import open_vault
        source = '# Dashboard\n\n```dataviewjs\nawait dv.view("views/inventory");\n```\n'
        (self.vault / 'Home.md').write_text(source)
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            with patch.object(owner.web, 'set_content') as publish:
                await owner.open_note('Vault/Home.md')
                initial = publish.call_args.args[1]
                self.assertIn('Loading data view', initial)
                self.assertIn('worker-src blob:', initial)
                plan = owner.data_view_plan
                owner.data_view_plan = None
                with patch('features.text_editor.mobile.dataview.execute_views',
                           new=AsyncMock(return_value='# Dashboard\n\n| Name |\n| --- |\n| Mobile result |\n')):
                    await owner.render_data_views(plan, owner.base, owner.path)
                self.assertIn('Mobile result', publish.call_args.args[1])
                self.assertNotIn('worker-src blob:', publish.call_args.args[1])
                self.assertEqual((self.vault / 'Home.md').read_text(), source)
                entered, release = asyncio.Event(), asyncio.Event()
                async def slow(*args, **kwargs):
                    entered.set()
                    await release.wait()
                    return 'Stale result'
                with patch('features.text_editor.mobile.dataview.execute_views', side_effect=slow):
                    pending = asyncio.create_task(owner.render_data_views(plan, owner.base, owner.path))
                    await entered.wait()
                    await owner.open_note('Vault/Projects/Plan.MD')
                    calls = publish.call_count
                    release.set()
                    await pending
                    self.assertEqual(publish.call_count, calls)
                    self.assertNotIn('Stale result', publish.call_args.args[1])
        self.run_async(exercise())

    def test_direct_links_probe_only_the_target_without_listing_siblings(self):
        library = NotesLibrary(self.provider, 'Vault')
        with patch.object(self.provider, 'list', side_effect=AssertionError('Listed unrelated notes')):
            self.assertEqual(library.link('Vault/Home.md', 'Projects/Plan.MD#heading'),
                             ('Vault/Projects/Plan.MD', 'heading'))
            self.assertEqual(library.link('Vault/Projects/Plan.MD', 'Home'), ('Vault/Home.md', ''))
            self.assertEqual(library.link('Vault/Projects/Plan.MD', '../Home.md'), ('Vault/Home.md', ''))
            with self.assertRaisesRegex(ValueError, 'not found'):
                library.link('Vault/Home.md', './missing.md')
            (self.vault / 'Linked.md').symlink_to(self.vault / 'Home.md')
            with self.assertRaisesRegex(ValueError, 'Linked storage'):
                library.link('Vault/Home.md', 'Linked.md')

    def test_global_link_lookup_reuses_names_and_detects_external_changes(self):
        (self.vault / 'Projects/Tech.md').write_text('# Tech')
        library = NotesLibrary(self.provider, 'Vault')
        with patch.object(self.provider, 'list', wraps=self.provider.list) as listing:
            self.assertEqual(library.link('Vault/Home.md', 'Tech'), ('Vault/Projects/Tech.md', ''))
            self.assertEqual(listing.call_count, 2)
            listing.reset_mock()
            self.assertEqual(library.link('Vault/Home.md', 'Tech'), ('Vault/Projects/Tech.md', ''))
            listing.assert_not_called()
            (self.vault / 'New').mkdir()
            (self.vault / 'New/Tech.md').write_text('# Another Tech')
            with self.assertRaisesRegex(ValueError, 'Several notes'):
                library.link('Vault/Home.md', 'Tech')
            self.assertEqual({call.args[0] for call in listing.call_args_list}, {'Vault', 'Vault/New'})
            (self.vault / 'Projects/Tech.md').unlink()
            self.assertEqual(library.link('Vault/Home.md', 'Tech'), ('Vault/New/Tech.md', ''))
            (self.vault / 'New/Tech.md').rename(self.vault / 'New/Renamed.md')
            with self.assertRaisesRegex(ValueError, 'not found'):
                library.link('Vault/Home.md', 'Tech')

    def test_close_retires_cached_names_and_a_late_scan_cannot_repopulate_them(self):
        from commonUtils.runtime.operations import OperationCancelled
        library = NotesLibrary(self.provider, 'Vault')
        library._link_listing('Vault', lambda: False)
        self.assertTrue(library._link_folders)
        library.close()
        self.assertEqual(library._link_folders, {})
        with self.assertRaises(OperationCancelled):
            library._link_listing('Vault', lambda: False)
        library = NotesLibrary(self.provider, 'Vault')
        original = self.provider.list
        def retire_during_listing(*args, **kwargs):
            rows = original(*args, **kwargs)
            library.close()
            return rows
        with patch.object(self.provider, 'list', side_effect=retire_during_listing):
            with self.assertRaises(OperationCancelled):
                library._link_listing('Vault', lambda: False)
        self.assertEqual(library._link_folders, {})


    def test_close_and_page_history_are_separate_controls(self):
        from mobile.obsidian import open_vault
        from commonUtils.runtime.resources.local import LocalFiles

        async def exercise():
            for width in (390, 900):
                with self.subTest(width=width):
                    self.app.show_documents_hub()
                    owner = await open_vault(self.app, LocalFiles(self.root), 'Vault', 'documents')
                    owner.reflow(width)
                    panel = self.app.body
                    key = owner.session.id
                    self.assertIs(owner.view._reader_close_button, owner.close_button)
                    self.assertEqual(owner.close_button.control_icon, 'close')
                    self.assertEqual(owner.view._native_reader_buttons(), [owner.links_button])
                    self.assertEqual(owner.secondary.children[:2], [owner.back_button, owner.forward_button])
                    self.assertEqual(owner.menu.control_icon, 'notes_files')
                    self.assertFalse(owner.back_button.enabled)
                    self.assertFalse(owner.forward_button.enabled)
                    await owner.open_note('Vault/Home.md')
                    owner.follow_link(owner.web, owner.base + '?target=Projects%2FPlan.MD')
                    for _ in range(100):
                        if owner.path == 'Vault/Projects/Plan.MD':
                            break
                        await asyncio.sleep(.01)
                    self.assertTrue(owner.back_button.enabled)
                    self.assertFalse(owner.forward_button.enabled)
                    owner.back_button.on_press()  # Native taps do not await returned coroutines.
                    for _ in range(100):
                        if owner.path == 'Vault/Home.md':
                            break
                        await asyncio.sleep(.01)
                    self.assertEqual(owner.path, 'Vault/Home.md')
                    self.assertEqual(owner.view._document_path(), str(self.root / owner.path))
                    self.assertFalse(owner.back_button.enabled)
                    self.assertTrue(owner.forward_button.enabled)
                    self.assertIs(self.app.body, panel)
                    owner.forward_button.on_press()
                    for _ in range(100):
                        if owner.path == 'Vault/Projects/Plan.MD':
                            break
                        await asyncio.sleep(.01)
                    self.assertEqual(owner.path, 'Vault/Projects/Plan.MD')
                    self.assertEqual(owner.view._document_path(), str(self.root / owner.path))
                    owner.sidebar.show_sidebar()
                    owner.close_button.on_press()
                    self.assertNotIn(key, self.app.workspace.sessions)
                    self.assertTrue(owner.cancelled.is_set())
                    self.assertIsNone(owner.path)
                    self.assertIsNot(self.app.body, panel)

        self.run_async(exercise())

    @unittest.skipUnless(os.environ.get('LOGISTICS_MOBILE_BRIDGE'), 'Host native bridge required')
    def test_native_localcrypt_and_crypt_remote_actions_read_and_lock(self):
        from io import BytesIO
        from pathlib import Path
        from uuid import uuid4
        from features.rclone.mobile.cloud import CloudClient
        from features.rclone.localcrypt.mobile.resources import encrypted_storage
        fixture = json.loads(Path('mobile_build/native_tests/tests/logisticsmobile/localcrypt_fixture.json').read_text())
        self.app.show_cloud(present=False)
        async def exercise():
            restore = getattr(self.app, 'cloud_restore_task', None)
            if restore is not None:
                await restore
            client = self.app.cloud_client = CloudClient(library=os.environ['LOGISTICS_MOBILE_BRIDGE'])
            client.request('import', package=fixture['package'], password='synthetic-resume-password',
                           package_name='Synthetic.zip', session_only=True)
            try:
                provider = encrypted_storage(self.app.private_root, client, 'Secret')
                provider.mkdir('.obsidian')
                provider.create_file('.obsidian/config.ini', BytesIO(b'[Fixture]'))
                provider.mkdir('Nested')
                provider.create_file('Home.md', BytesIO(b'# Private home'))
                provider.create_file('Nested/Next.md', BytesIO(b'# Private nested note'))
                # Real cipher names must match across different parent paths.
                with patch.object(provider, 'list', side_effect=AssertionError('Decoded unrelated filenames')):
                    self.assertEqual(NotesLibrary(provider).link('Home.md', 'Next'), ('Nested/Next.md', ''))
                client.request('mirror_sync', remote='Secret', path='', identity=client.connection_identity('Secret'),
                               local_path=str(provider.root.resolve()), run=uuid4().hex, push=True)
                for kind, source, value in [('crypt', 'Local', 'Secret'), ('remote', 'Cloud', ('Secret', ''))]:
                    with self.subTest(kind=kind):
                        status = toga.Label('')
                        button = toga.Button('Open as Notes Library')
                        box = toga.Box(children=[status])
                        self.app.show_view(box, destination='files', route='encrypted-notes-action')
                        entry = dict(source=source, kind=kind, value=value, name='Secret')
                        await offer_notes(self.app, entry, box, button, status)
                        if kind == 'remote':
                            self.assertNotIn(button, box.children)
                            continue
                        self.assertIn(button, box.children, status.text)
                        await button.on_press()
                        owner = self.app.vault_browser
                        self.assertIsNotNone(owner)
                        self.assertTrue(await owner.open_note('Home.md'), owner.notice.text)
                        await owner.toggle_folder('Nested')
                        self.assertTrue(await owner.open_note('Nested/Next.md'), owner.notice.text)
                        owner.back_button.on_press()
                        for _ in range(100):
                            if owner.path == 'Home.md':
                                break
                            await asyncio.sleep(.01)
                        self.assertEqual(owner.path, 'Home.md')
                client.clear()
                self.assertFalse(await owner.open_note('Home.md'))
                self.app.clear_private_catalog()
                self.assertIsNone(owner.path)
            finally:
                client.clear()
        self.run_async(exercise())

    def test_documents_discovers_local_library_without_workspace_prompt(self):
        from services.documents.locations import collection_path
        folder = collection_path(self.app.private_root) / 'Notes'
        shutil.copytree(self.vault, folder)
        self.app.show_cloud(present=False)
        async def exercise():
            restore = getattr(self.app, 'cloud_restore_task', None)
            if restore is not None:await restore
            entry = dict(source='Local', kind='local', value='Notes', name='Notes', copies=[])
            self.app.show_picker_folder(entry)
            self.assertFalse(any(getattr(child, 'text', '') == 'Open as Notes Library'
                                 for child, _ in self.app.folder_action_controls))
            self.app.show_documents_hub()
            await self.app._notes_discovery_task
            button = next(child for child in self.app.document_notes_list.children[1].children
                          if getattr(child, 'text', '') == 'Notes · Local')
            self.assertIsNotNone(button.parent)
            await button.on_press()
            owner = self.app.vault_browser
            self.assertEqual(self.app.native_host.state.destination, 'documents')
            self.assertEqual(owner.session.provider, 'notes-library')
            self.assertIn(owner.session.id, self.app.workspace.sessions)
            self.assertIsNotNone(owner.search)
            await owner.open_note('Notes/Home.md')
            await owner.open_note('Notes/Projects/Plan.MD')
            await owner.navigate_history(-1)
            self.assertEqual(owner.path, 'Notes/Home.md')
            owner.show_page_search()
            owner.page_search.query.value = 'Home'
            self.assertTrue(owner.page_search.visible)
            key = owner.session.id
            self.app.show_documents_hub()
            self.app.session_opener(key)()
            self.assertEqual(self.app.native_host.state.destination, 'documents')
            self.app.close_session(key)
            self.assertNotIn(key, self.app.workspace.sessions)
            self.assertTrue(owner.page_search.closed)
            self.assertEqual(owner.page_search.query.value, '')
        self.run_async(exercise())

    def test_remote_action_has_no_search_and_never_lists_unopened_children(self):
        self.app.show_cloud(present=False)
        async def exercise():
            restore = getattr(self.app, 'cloud_restore_task', None)
            if restore is not None:await restore
            client = self.app.cloud_client = Client(self.vault)
            status = toga.Label('');button = toga.Button('Open as Notes Library');box = toga.Box(children=[status], style=Pack())
            self.app.show_view(box, destination='files', route='notes-action')
            entry = dict(source='Remote', kind='remote', value=('remote', ''), name='Remote')
            await offer_notes(self.app, entry, box, button, status)
            self.assertNotIn(button, box.children)
            self.assertEqual(client.calls, [])
        self.run_async(exercise())

    def test_missing_or_file_marker_does_not_offer_and_stale_probe_cannot_present(self):
        self.app.show_cloud(present=False)
        async def exercise():
            restore = getattr(self.app, 'cloud_restore_task', None)
            if restore is not None:await restore
            client = self.app.cloud_client = Client(self.vault)
            status = toga.Label('');button = toga.Button('Open as Notes Library');box = toga.Box(children=[status])
            self.app.show_view(box, destination='files', route='notes-action')
            entry = dict(source='Remote', kind='remote', value=('remote', ''), name='Remote')
            with patch.object(client, 'entries', return_value=[dict(path='.obsidian', directory=False)]):
                await offer_notes(self.app, entry, box, button, status)
            self.assertNotIn(button, box.children)
            original = client.entries
            def stale(remote, path):
                client.generation += 1
                return original(remote, path)
            with patch.object(client, 'entries', side_effect=stale):
                await offer_notes(self.app, entry, box, button, status)
            self.assertNotIn(button, box.children)
        self.run_async(exercise())

    def test_shared_bounds_and_links_are_enforced_for_remote(self):
        client = Client(self.vault)
        with self.assertRaisesRegex(ValueError, 'local copy'):
            NotesLibrary(RemoteNotes(client, 'remote'))
        self.assertEqual(client.calls, [])

    def test_expanded_private_html_is_refused_without_replacing_note(self):
        from types import SimpleNamespace
        from mobile.obsidian import VaultBrowser
        class PrivateFiles(LocalFiles):
            private = True
        self.app.cloud_client = SimpleNamespace(generation=1, cancel=lambda: None)
        owner = VaultBrowser(self.app, PrivateFiles(self.root), 'Vault', 'documents')
        self.app.vault_browser = owner
        async def exercise():
            self.assertTrue(await owner.open_note('Vault/Home.md'))
            history = list(owner.history)
            with patch('mobile.obsidian.markdown_preview', return_value='x' * (2 * 1024 * 1024 + 1)):
                self.assertFalse(await owner.open_note('Vault/Projects/Plan.MD'))
            self.assertEqual(owner.path, 'Vault/Home.md')
            self.assertEqual(owner.history, history)
        self.run_async(exercise())
