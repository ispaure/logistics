"""Mobile browser/Notes renames with real local files and native crypt names."""
from commonUtils.testing.stages import TestStage

import asyncio
from io import BytesIO
import json
import os
from pathlib import Path
import unittest
from threading import Event
from unittest.mock import patch

import mobile_build.tests.documents.test_obsidian as fixtures
from mobile.favourites import catalog, resource_reference
from mobile.obsidian import open_vault
from mobile.workspace import Session

TEST_STAGE = TestStage.REGRESSION


class MobileRenameReferenceTests(unittest.TestCase):
    setUp = fixtures.ObsidianTests.setUp
    tearDown = fixtures.ObsidianTests.tearDown

    def test_cancel_after_notes_rename_commit_retires_worker_and_updates_references(self):
        app = self.app
        source, target = 'Vault/Home.md', 'Vault/Renamed.md'
        store = catalog(app)
        reference, _ = resource_reference(app, self.provider, source)
        store.remember(reference, 'Home.md', dict(kind='notes', root=str(self.vault.resolve())), favourite=True)
        committed, release = Event(), Event()
        async def exercise():
            owner = await open_vault(app, self.provider, 'Vault', 'documents')
            self.assertTrue(await owner.open_note(source))
            move = owner.library.move
            def committed_move(*args, **kwargs):
                result = move(*args, **kwargs)
                committed.set()
                if not release.wait(4):
                    raise RuntimeError('Rename test worker was not released')
                return result
            with patch.object(owner.library, 'move', side_effect=committed_move):
                task = asyncio.create_task(owner.move_entry_to(source, target))
                try:
                    self.assertTrue(await asyncio.to_thread(committed.wait, 3))
                    task.cancel()
                    await asyncio.sleep(0)
                    self.assertTrue(owner.file_command_busy)
                finally:
                    release.set()
                    await asyncio.gather(task, return_exceptions=True)
            self.assertTrue(task.cancelled())
            self.assertFalse(owner.file_command_busy)
            self.assertEqual(owner.path, target)
            self.assertEqual(store.entries()[0]['source'], resource_reference(app, self.provider, target)[0])
        app.loop.run_until_complete(exercise())

    def test_repeated_cancel_before_notes_rename_commit_preserves_source_and_references(self):
        app = self.app
        source, target = 'Vault/Home.md', 'Vault/Renamed.md'
        store = catalog(app)
        reference, _ = resource_reference(app, self.provider, source)
        store.remember(reference, 'Home.md', dict(kind='notes', root=str(self.vault.resolve())), favourite=True)
        started, release = Event(), Event()
        async def exercise():
            owner = await open_vault(app, self.provider, 'Vault', 'documents')
            move = owner.library.move
            def pending_move(*args, **kwargs):
                started.set()
                if not release.wait(4):
                    raise RuntimeError('Rename test worker was not released')
                return move(*args, **kwargs)
            with patch.object(owner.library, 'move', side_effect=pending_move):
                task = asyncio.create_task(owner.move_entry_to(source, target))
                try:
                    self.assertTrue(await asyncio.to_thread(started.wait, 3))
                    for _ in range(2):
                        task.cancel()
                        await asyncio.sleep(0)
                        self.assertTrue(owner.file_command_busy)
                finally:
                    release.set()
                    await asyncio.gather(task, return_exceptions=True)
            self.assertTrue(task.cancelled())
            self.assertFalse(owner.file_command_busy)
            self.assertTrue((self.root / source).exists())
            self.assertFalse((self.root / target).exists())
            self.assertEqual(store.entries()[0]['source'], reference)
        app.loop.run_until_complete(exercise())

    async def exercise(self, provider, *, notes):
        app = self.app
        folder = 'Notes Ω' if notes else 'Browser Ω'
        provider.mkdir(folder)
        path = folder + '/Private name.md'
        provider.create_file(path, BytesIO(b'# Keep content\n'))
        source, cipher = resource_reference(app, provider, path)
        opener = dict(kind='notes', root=folder if cipher else str((provider.root / folder).resolve()))
        store = catalog(app)
        store.remember(source, 'Private name.md', opener, favourite=True, cipher=cipher)
        session = Session('', 'file-reference', 'fixture', 'markdown', title='Private name.md')
        if cipher:
            app.credential_document_lists.remember(session, source)
        else:
            app.recent_documents.remember_file(session, source)
        if notes:
            owner = await open_vault(app, provider, '', 'documents')
            self.assertIsNotNone(owner)
        else:
            await app.show_files(location=('Local files', ''))
        for before, after in [(path, folder + '/Renamed café.md'), (folder, folder + ' moved')]:
            if notes:
                self.assertTrue(await owner.move_entry_to(before, after), owner.notice.text)
            else:
                app.file_provider, app.file_path = provider, before.rpartition('/')[0]
                row = provider.entry(before)
                app.file_rows = {before: row}
                app.file_selection.items = [before]
                app.file_selection.value = before
                app.file_name.value = after.rpartition('/')[2]
                await app.rename_file()
                self.assertNotIn('failed', app.file_status.value.lower())
            await asyncio.sleep(0)  # Retire queued credential reference updates.
            expected = (folder if '/' in before else after) + '/Renamed café.md'
            with provider.open(expected) as stream:
                self.assertEqual(stream.read(), b'# Keep content\n')
            row = next(row for row in store.entries(ciphers=[cipher] if cipher else [])
                       if row['source'] == resource_reference(app, provider, expected)[0])
            self.assertEqual(row['title'], 'Renamed café.md')
            expected_root = expected.rpartition('/')[0]
            self.assertEqual(row['opener']['root'], expected_root if cipher else str((provider.root / expected_root).resolve()))
            rows = app.recent_documents.private_items if cipher else app.recent_documents.items
            self.assertTrue(any(row.get('source') == resource_reference(app, provider, expected)[0] for row in rows))
            self.assertFalse(any(row.get('source') == source for row in rows))
        # Refusing an existing name must preserve bytes and saved references.
        taken = expected.rpartition('/')[0] + '/Taken.md'
        provider.create_file(taken, BytesIO(b'# Keep destination\n'))
        favourites_before = store.path(cipher).read_bytes()
        recent_before = [dict(row) for row in rows]
        if notes:
            self.assertFalse(await owner.move_entry_to(expected, taken))
        else:
            app.file_provider, app.file_path = provider, expected.rpartition('/')[0]
            app.file_rows = {expected: provider.entry(expected)}
            app.file_selection.items = [expected]
            app.file_selection.value = expected
            app.file_name.value = 'Taken.md'
            await app.rename_file()
            self.assertIn('failed', app.file_status.value.lower())
        await asyncio.sleep(0)
        self.assertEqual(store.path(cipher).read_bytes(), favourites_before)
        self.assertEqual(app.recent_documents.private_items if cipher else app.recent_documents.items, recent_before)
        for path, data in [(expected, b'# Keep content\n'), (taken, b'# Keep destination\n')]:
            with provider.open(path) as stream:
                self.assertEqual(stream.read(), data)
        from mobile.favourites import reopen
        self.assertTrue(await reopen(app, row))
        reopened = app.vault_browser
        self.assertEqual(resource_reference(app, reopened.provider, reopened.path)[0],
                         resource_reference(app, provider, expected)[0])
        if notes:
            owner = reopened
            # The dummy backend cannot supply a private formatted WebView.
            # Exercise the same provider-backed Source editor used on devices.
            self.assertTrue(await owner.open_text(owner.path, remember=False), owner.notice.text)
            owner.embedded.changed('# Edited after both renames\n')
            self.assertTrue(await owner.embedded.save(), owner.notice.text)
            with provider.open(expected) as stream:
                self.assertEqual(stream.read(), b'# Edited after both renames\n')
        if cipher:
            app.credential_document_lists.flush_writes()
            self.assertNotIn(b'Renamed', store.path(cipher).read_bytes())
            for item in app.credential_document_lists.root.rglob('*.zip'):
                self.assertNotIn(b'Renamed', item.read_bytes())
            app.credential_document_lists.states.pop(cipher.identity)
            app.credential_document_lists.refresh()
            self.assertTrue(any(row['source'] == resource_reference(app, provider, expected)[0]
                                for row in app.recent_documents.private_items))
        if notes:
            owner.dispose()

    def test_local_browser_and_notes_rename_closed_references(self):
        async def exercise():
            for notes in (False, True):
                await self.exercise(self.provider, notes=notes)
        self.app.loop.run_until_complete(exercise())

    async def exercise_downloaded(self, client, fixture):
        import base64
        from uuid import uuid4
        from features.rclone.localcrypt.mobile.resources import DownloadedCryptFile
        from mobile.favourites import reopen
        app = self.app
        app.crypt_copies.client = client
        sample = fixture['copies']['note.md']
        key = uuid4().hex
        folder = app.crypt_copies.root / key
        folder.mkdir()
        (folder / 'data').write_bytes(base64.b64decode(sample['ciphertext']))
        (folder / 'record.json').write_text(json.dumps(sample['record']))
        provider = DownloadedCryptFile(app.crypt_copies, key)
        source, cipher = resource_reference(app, provider, provider.name)
        self.assertEqual(source['type'], 'download')
        self.assertEqual(source['key'], key)
        store = catalog(app)
        store.remember(source, 'note.md', dict(kind='markdown'), favourite=True, cipher=cipher)
        session = Session('', 'file-reference', 'fixture', 'markdown', title='note.md')
        app.credential_document_lists.remember(session, source)
        await app.show_files(location=('Local files', ''))
        app.file_provider, app.file_path = provider, ''
        app.file_rows = {'note.md': provider.entry('note.md')}
        app.file_selection.items = ['note.md']
        app.file_selection.value = 'note.md'
        app.file_name.value = 'Renamed downloaded Ω.md'
        await app.rename_file()
        self.assertNotIn('failed', app.file_status.value.lower())
        await asyncio.sleep(0)
        row = next(row for row in store.entries(ciphers=[cipher]) if row['source'] == source)
        self.assertEqual(row['title'], 'Renamed downloaded Ω.md')
        self.assertTrue(any(row['source'] == source and row['title'] == 'Renamed downloaded Ω.md'
                            for row in app.recent_documents.private_items))
        try:
            self.assertTrue(await reopen(app, row))
            owner = app.private_sessions.active
            self.assertEqual(owner.crypt_reader.name, 'Renamed downloaded Ω.md')
            owner.crypt_text.value = '# Edited renamed download\n'
            await owner.save_crypt()
            self.assertEqual(app.crypt_copies.open(key).text, '# Edited renamed download\n')
            self.assertNotIn(b'Edited renamed download', (folder / 'data').read_bytes())
        finally:
            app.clear_private_reader(discard=True)
            provider.close()

    @unittest.skipUnless(os.environ.get('LOGISTICS_MOBILE_BRIDGE'), 'Host native bridge required')
    def test_native_localcrypt_browser_and_notes_rename_encrypted_references(self):
        from features.rclone.mobile.cloud import CloudClient
        from features.rclone.localcrypt.mobile.resources import encrypted_storage
        fixture = json.loads(Path('mobile_build/native_tests/tests/logisticsmobile/localcrypt_fixture.json').read_text())
        self.app.show_cloud(present=False)
        async def exercise():
            restore = getattr(self.app, 'cloud_restore_task', None)
            if restore is not None:
                await restore
            client = self.app.cloud_client = CloudClient(library=os.environ['LOGISTICS_MOBILE_BRIDGE'])
            client.request('import', package=fixture['encrypted_package'], password='synthetic-package-password',
                           package_name='Synthetic.zip', session_only=True)
            provider = encrypted_storage(self.app.private_root, client, 'Secret')
            try:
                for notes in (False, True):
                    await self.exercise(provider, notes=notes)
                await self.exercise_downloaded(client, fixture)
            finally:
                self.app.credential_document_lists.flush_writes()
                provider.close()
                client.clear()
        self.app.loop.run_until_complete(exercise())
