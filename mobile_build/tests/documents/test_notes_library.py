"""Location actions, bounded remote access and Notes Library document ownership."""
import base64
import json
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


import unittest


class NotesLibraryTests(unittest.TestCase):
    setUp = test_obsidian.ObsidianTests.setUp
    tearDown = test_obsidian.ObsidianTests.tearDown
    run_async = test_obsidian.ObsidianTests.run_async
    def test_actions_open_local_in_workspaces_and_close_session(self):
        from features.rclone.mobile.storage_location import collection_path
        folder = collection_path(self.app.private_root) / 'Notes'
        shutil.copytree(self.vault, folder)
        self.app.show_cloud(present=False)
        async def exercise():
            restore = getattr(self.app, 'cloud_restore_task', None)
            if restore is not None:await restore
            entry = dict(source='Local', kind='local', value='Notes', name='Notes', copies=[])
            page = self.app.show_picker_folder(entry)
            await self.app._notes_offer_task
            button = next(child for child, _ in self.app.folder_action_controls
                if getattr(child, 'text', '') == 'Open Notes Library')
            self.assertIsNotNone(button.parent)
            await button.on_press()
            owner = self.app.vault_browser
            self.assertEqual(self.app.native_host.state.destination, 'files')
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
            status = toga.Label('');button = toga.Button('Open Notes Library');box = toga.Box(children=[status], style=Pack())
            self.app.show_view(box, destination='files', route='notes-action')
            entry = dict(source='Remote', kind='remote', value=('remote', ''), name='Remote')
            await offer_notes(self.app, entry, box, button, status)
            self.assertIn(button, box.children)
            self.assertEqual(client.calls, [('list', '')])
            await button.on_press()
            owner = self.app.vault_browser
            self.assertIsNone(owner.search)
            self.assertEqual([call for call in client.calls if call[0] == 'list'], [('list', ''), ('list', '')])
            await owner.open_note('Home.md')
            self.assertFalse(any(path.startswith('Projects') for _, path in client.calls))
            await owner.toggle_folder('Projects')
            self.assertIn(('list', 'Projects'), client.calls)
            await owner.open_note('Projects/Plan.MD')
            self.assertEqual(owner.path, 'Projects/Plan.MD')
            client.generation += 1
            self.assertFalse(await owner.open_note('Home.md'))
            self.app.clear_private_catalog()
            self.assertIsNone(owner.path)
        self.run_async(exercise())

    def test_missing_or_file_marker_does_not_offer_and_stale_probe_cannot_present(self):
        self.app.show_cloud(present=False)
        async def exercise():
            restore = getattr(self.app, 'cloud_restore_task', None)
            if restore is not None:await restore
            client = self.app.cloud_client = Client(self.vault)
            status = toga.Label('');button = toga.Button('Open Notes Library');box = toga.Box(children=[status])
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
        library = NotesLibrary(RemoteNotes(Client(self.vault), 'remote'))
        for target in ('../outside.md', '.obsidian/private.md', 'https://example.invalid/note.md', '%2e%2e/outside.md'):
            with self.assertRaises(ValueError):library.link('Home.md', target)
        (self.vault / 'Huge.md').write_bytes(b'x' * (2 * 1024 * 1024 + 1))
        with self.assertRaises(ValueError):library.read('Huge.md')

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
