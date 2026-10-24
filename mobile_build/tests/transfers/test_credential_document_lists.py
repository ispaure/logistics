"""Credential-list lifecycle and UI integration; AES/password checks live in Go tests."""
import base64
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from mobile.app import LogisticsMobile
from mobile.workspace import Session
from features.rclone.mobile.document_lists import forget_cache
from features.rclone.mobile.credential_packages import CredentialPackages


class ListBridge:
    """Opaque token transport to test lifecycle independently of native encryption."""
    def __init__(self):
        self.package_records = []
        self.payloads = {}
        self.generation = 0

    def cancel(self):
        pass

    def clear(self):
        self.package_records = []
        self.generation += 1

    def unlock(self, key='a' * 64, identity='b' * 64, remote='Drive'):
        self.package_records.append(dict(document_cache_id=key, saved=False, package_name='Personal.zip',
            remotes=[remote], identities={remote: identity}, crypt_identities={}))

    def request(self, action, **values):
        if action == 'crypt_path':
            return dict(identity='b' * 64)
        if not any(record['document_cache_id'] == values['id'] for record in self.package_records):
            raise ValueError('Locked')
        data = base64.b64decode(values['data'])
        if action == 'document_lists_seal':
            token = b'opaque-test-ciphertext-' + str(len(self.payloads)).encode()
            self.payloads[token] = data
            return base64.b64encode(token).decode()
        if action == 'document_lists_open':
            if data not in self.payloads:
                raise ValueError('Authentication failed')
            return base64.b64encode(self.payloads[data]).decode()
        raise ValueError('Unexpected test action')


class CredentialDocumentListTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        LogisticsMobile.storage_root = self.root
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        self.app.show_cloud(present=False)
        self.client = ListBridge()
        self.app.cloud_client = self.client
        self.cache = self.app.credential_document_lists

    def test_clear_recent_preserves_encrypted_open_references(self):
        self.client.unlock()
        self.remember()
        key = next(iter(self.cache.states))
        opened = list(self.cache.states[key]['open'])
        self.assertTrue(self.app.recent_documents.private_items)
        self.cache.clear_recent()
        self.assertEqual(self.cache.states[key]['recent'], [])
        self.assertEqual(self.cache.states[key]['open'], opened)
        self.cache.states.clear()
        self.cache.refresh()
        self.assertEqual(self.cache.states[key]['recent'], [])
        self.assertEqual(self.cache.states[key]['open'], opened)
        self.assertEqual(self.app.recent_documents.private_items, [])

    def test_clear_recent_retires_a_pending_encrypted_history_write(self):
        self.client.unlock()
        async def exercise():
            self.remember()
            self.assertTrue(self.cache._queued_writes)
            self.cache.clear_recent()
            self.assertEqual(self.cache._queued_writes, {})
            await asyncio.sleep(.1)
            if self.cache._write_tasks:
                await asyncio.gather(*self.cache._write_tasks)
        self.app.loop.run_until_complete(exercise())
        self.cache.states.clear()
        self.cache.refresh()
        self.assertEqual(self.app.recent_documents.private_items, [])
        self.assertTrue(next(iter(self.cache.states.values()))['open'])

    def source(self, index=0, identity='b' * 64, remote='Drive'):
        return dict(type='remote', remote=remote, identity=identity, key=f'Sensitive/folder/file-{index}.md')

    def remember(self, index=0, **kwargs):
        source = self.source(index, **kwargs)
        session = Session('live', 'provider-session', 'memory-only', 'markdown', title=f'Sensitive title {index}.md', transient=True)
        self.cache.remember(session, source)
        return session

    def test_async_remembers_coalesce_and_only_ciphertext_reaches_disk(self):
        self.client.unlock()
        async def exercise():
            for index in range(20):
                self.remember(index)
            await asyncio.sleep(.1)
            await asyncio.gather(*self.cache._write_tasks)
        with patch.object(self.client, 'request', wraps=self.client.request) as request:
            self.app.loop.run_until_complete(exercise())
        seals = [call for call in request.call_args_list if call.args[0] == 'document_lists_seal']
        self.assertEqual(len(seals), 1)
        for path in self.root.rglob('*'):
            if path.is_file():
                self.assertNotIn(b'Sensitive title', path.read_bytes())
                self.assertNotIn(b'Sensitive/folder', path.read_bytes())

    def test_forget_retires_a_queued_write_before_it_can_recreate_ciphertext(self):
        self.client.unlock()
        async def exercise():
            self.remember()
            forget_cache(self.cache.root)
            await asyncio.sleep(.1)
            await asyncio.gather(*self.cache._write_tasks)
        self.app.loop.run_until_complete(exercise())
        self.assertFalse(list(self.cache.root.rglob('*.zip')))

    def test_credential_replacement_retires_a_queued_encrypted_snapshot(self):
        self.client.unlock()
        async def exercise():
            self.remember()
            self.client.clear()
            self.cache.forget_memory()
            await asyncio.sleep(.1)
            await asyncio.gather(*self.cache._write_tasks)
        self.app.loop.run_until_complete(exercise())
        self.assertFalse(list(self.cache.root.rglob('*.zip')))

    def test_lists_stay_out_of_plaintext_and_restore_only_after_unlock(self):
        self.client.unlock()
        session = self.remember()
        path = self.cache.path('a' * 64)
        self.assertTrue(path.exists())
        for item in (path, self.app.workspace.path, self.app.recent_documents.path):
            if item.exists():
                self.assertNotIn(b'Sensitive', item.read_bytes())
        self.assertEqual(self.app.recent_items()[0][0].title, session.title)
        self.client.package_records = []
        self.cache.refresh()
        self.assertEqual(self.app.recent_items(), [])
        self.assertFalse(any(item.provider == 'credential-reference' for item in self.app.workspace.sessions.values()))
        self.client.unlock()
        self.cache.refresh()
        restored = next(item for item in self.app.workspace.sessions.values() if item.provider == 'credential-reference')
        self.assertEqual(restored.title, session.title)
        self.assertTrue(self.app.session_visible(restored))
        self.assertEqual(self.app.recent_items(excluding=[restored.identity]), [])
        self.app.build_documents_hub()
        self.app.workspace.save()
        self.assertNotIn('Sensitive', self.app.workspace.path.read_text())
        self.assertTrue(self.app.close_session(restored.id))
        self.assertEqual(self.cache.states['a' * 64]['open'], [])
        self.assertEqual(len(self.cache.states['a' * 64]['recent']), 1)

    def test_recent_bound_and_credential_deletion_across_window_files(self):
        self.client.unlock()
        for index in range(12):
            self.remember(index)
        self.assertEqual(len(self.app.recent_items()), 10)
        self.assertEqual(len(self.cache.states['a' * 64]['recent']), 10)
        other_window = self.cache.path('a' * 64).with_name('c' * 64 + '.zip')
        other_window.write_bytes(b'encrypted-other-window')
        self.client.unlock(key='d' * 64, identity='e' * 64, remote='Other')
        self.remember(20, identity='e' * 64, remote='Other')
        forget_cache(self.cache.root, 'a' * 64)
        self.assertFalse(other_window.exists())
        self.assertFalse(self.cache.path('a' * 64).exists())
        self.assertTrue(self.cache.path('d' * 64).exists())
        self.assertNotIn('a' * 64, self.cache.states)
        self.assertTrue(all(item.source['remote'] == 'Other' for item in self.app.recent_documents.sessions()))

    def test_newest_entries_merge_across_credentials_and_ordinary_history(self):
        self.client.unlock()
        self.remember(1)
        self.client.unlock(key='d' * 64, identity='e' * 64, remote='Other')
        self.remember(2, identity='e' * 64, remote='Other')
        self.assertEqual(self.app.recent_documents.sessions()[0].title, 'Sensitive title 2.md')
        ordinary = Session('local', 'managed-text', 'f' * 32, 'text')
        self.app.recent_documents.remember(ordinary)
        self.assertEqual(self.app.recent_documents.sessions()[0].provider, 'managed-text')
        self.remember(3)
        self.assertEqual(self.app.recent_documents.sessions()[0].title, 'Sensitive title 3.md')

    def test_forget_credentials_removes_encrypted_lists(self):
        self.client.unlock()
        self.remember()
        vault = SimpleNamespace(root=self.root / 'Packages', forget=lambda: None)
        packages = CredentialPackages(vault, self.client, document_cache_root=self.cache.root)
        packages.forget()
        self.assertEqual(list(self.cache.root.iterdir()), [])
        self.assertEqual(self.app.recent_documents.private_items, [])

    def test_forget_credentials_action_wipes_cache_and_restored_entries(self):
        self.client.unlock()
        self.remember()
        path = self.cache.path('a' * 64)
        self.app.loop.run_until_complete(self.app.clear_cloud())
        self.assertFalse(path.exists())
        self.assertEqual(self.app.recent_items(), [])
        self.assertIn('document lists forgotten', self.app.cloud_status.value)

    def test_corrupt_cache_is_preserved_and_not_overwritten(self):
        self.client.unlock()
        path = self.cache.path('a' * 64)
        path.parent.mkdir(parents=True)
        path.write_bytes(b'corrupt-or-wrong-password')
        self.remember()
        self.assertEqual(path.read_bytes(), b'corrupt-or-wrong-password')
        self.assertIn('a' * 64, self.cache.failed)
        self.assertEqual(self.app.recent_items(), [])

    def test_migrates_old_retained_references_after_encrypting(self):
        source = self.source()
        session = Session('live', 'provider-session', 'memory-only', 'markdown', title='Sensitive.md', transient=True)
        self.app.recent_documents.remember_file(session, source)
        self.assertIn('Sensitive', self.app.recent_documents.path.read_text())
        self.client.unlock()
        self.cache.refresh()
        self.assertNotIn('Sensitive', self.app.recent_documents.path.read_text())
        self.assertTrue(self.cache.path('a' * 64).exists())
        self.assertEqual(self.app.recent_items()[0][0].title, 'Sensitive.md')

    def test_swapped_authenticated_cache_with_unrelated_connection_is_rejected(self):
        self.client.unlock()
        self.remember()
        self.cache.forget_memory()
        self.client.package_records[0]['identities'] = {'Drive': 'f' * 64}
        self.cache.refresh()
        self.assertIn('a' * 64, self.cache.failed)
        self.assertFalse(self.app.recent_items())

    def test_cache_is_bound_to_exact_credential_even_when_accounts_match(self):
        self.client.unlock()
        self.remember()
        first = self.cache.path('a' * 64).read_bytes()
        self.client.unlock(key='d' * 64)
        second = self.cache.path('d' * 64)
        second.parent.mkdir(parents=True)
        second.write_bytes(first)
        self.cache.refresh()
        self.assertIn('d' * 64, self.cache.failed)
        self.assertNotIn('d' * 64, self.cache.states)

    def test_live_reader_replaces_restored_entry_and_explicit_close_updates_cache(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from features.text_editor.resources import LocalTextCopies
        self.client.unlock()
        folder = self.root / 'SyntheticEncryptedProvider'
        folder.mkdir()
        (folder / 'note.md').write_text('# In-memory provider fixture')
        provider = LocalFiles(folder)
        provider.remote, provider.identity, provider.storage_namespace = 'Drive', 'b' * 64, 'b' * 64
        copies = LocalTextCopies(provider)
        copies.encrypted = True  # Exercise the credential boundary with a local fixture reader.
        source = dict(type='crypt', remote='Drive', identity='b' * 64, namespace='b' * 64, key='note.md')
        previous = Session('old', 'provider-session', 'old-reader', 'markdown', title='note.md', transient=True)
        self.cache.remember(previous, source)
        self.cache.refresh()
        restored = next(item for item in self.app.workspace.sessions.values() if item.provider == 'credential-reference')
        self.app.workspace.active = restored.id
        self.assertTrue(self.app.loop.run_until_complete(self.app.open_crypt(copies=copies, key='note.md')))
        self.assertNotIn(restored.id, self.app.workspace.sessions)
        live = self.app.private_sessions.active
        self.assertEqual(live.session.cache_id, 'a' * 64)
        self.assertEqual(len(self.cache.states['a' * 64]['open']), 1)
        self.assertFalse(any(item.provider == 'credential-reference' for item in self.app.workspace.sessions.values()))
        self.assertTrue(self.app.private_sessions.close(live.session.id))
        self.assertEqual(self.cache.states['a' * 64]['open'], [])
        self.assertEqual(len(self.cache.states['a' * 64]['recent']), 1)

    def test_open_restored_entry_loads_on_demand_and_removes_placeholder(self):
        self.client.unlock()
        self.remember()
        self.cache.forget_memory()
        self.cache.refresh()
        session = next(item for item in self.app.workspace.sessions.values() if item.provider == 'credential-reference')
        with patch('mobile.document_sources.reopen_file', new_callable=AsyncMock, return_value=True) as reopen:
            self.app.loop.run_until_complete(self.cache.open(session))
            reopen.assert_awaited_once_with(self.app, session.cache_source)
        self.assertNotIn(session.id, self.app.workspace.sessions)
