"""Shared progress policy, publication ordering and real encrypted persistence."""

import json
import base64
from io import BytesIO
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from features.rclone import session
from services.documents.credential_state import CredentialState, DesktopCredentialCipher
from services.documents.history_controls import clear_saved_positions
from services.documents.locations import use_shared_local
from services.documents.progress import ProgressMode, ProgressStatus, document_identity, open_progress
from services.documents.progress import prepare_local_progress_move
from services.documents.state_migration import migrate


TEST_STAGE = TestStage.REGRESSION


class UnifiedProgressCoreTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.local = self.root / 'LocalFiles'
        self.nested = self.local / 'nested'
        self.nested.mkdir(parents=True)
        self.book = self.nested / 'book.epub'
        self.book.write_bytes(b'synthetic book')
        self.context = self.root / 'reader.session'
        self.addCleanup(session.forget, self.context)

    def local_progress(self, provider=None, path=None, **options):
        return open_progress(provider, path or self.book, self.root, kind='epub', **options)

    def unlock(self, password):
        session.remember(self.context, {'Drive': {'type': 'memory'}},
                         state_password=password, state_identity='a' * 64)
        return SimpleNamespace(private=True, context=self.context, remote='Drive')

    def private_progress(self, provider, path='private-title.epub', **options):
        return open_progress(provider, path, self.root, kind='epub', **options)

    def test_nested_readonly_file_has_one_local_checkpoint_and_survives_new_process(self):
        home, local = LocalFiles(self.local), LocalFiles(self.nested)
        local.read_only = True
        writer = self.local_progress(home, 'nested/book.epub')
        self.assertIs(writer.mode, ProgressMode.LOCAL)
        self.assertEqual(writer.load(), {})
        self.assertIs(writer.load_status, ProgressStatus.ABSENT)
        self.assertTrue(writer.can_import_legacy)
        self.assertIs(writer.save({'page': 7}), ProgressStatus.SAVED)
        same = self.local_progress(local, 'book.epub')
        self.assertEqual(writer.identity, same.identity)
        self.assertEqual(same.load(), {'page': 7})
        self.assertEqual(self.fresh_process_position(), [{'page': 7}, 'restored'])
        self.assertEqual(len(list((self.root / 'ReaderPositions').rglob('*.json'))), 1)

    def fresh_process_position(self, page=None):
        script = '''
import json, sys
from pathlib import Path
from services.documents.progress import open_progress
root = Path(sys.argv[1])
state = open_progress(None, root / 'LocalFiles/nested/book.epub', root, kind='epub')
loaded = state.load()
if len(sys.argv) > 2:
    assert state.save({'page': int(sys.argv[2])}).value == 'saved'
print(json.dumps([loaded, state.load_status.value]))
'''
        python_root = Path(__file__).resolve().parents[2]
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(python_root), os.environ.get('PYTHONPATH', ''))))
        command = [sys.executable, '-c', script, str(self.root)]
        if page is not None:
            command.append(str(page))
        result = subprocess.run(command,
                                env=env, check=True, capture_output=True, text=True, timeout=20)
        return json.loads(result.stdout)

    def test_newer_process_checkpoint_takes_precedence_over_older_pending_memory(self):
        first = self.local_progress()
        first.save({'page': 1})
        old = first.observe({'page': 17})
        self.assertEqual(self.fresh_process_position(page=4), [{'page': 1}, 'restored'])
        self.assertEqual(self.local_progress().load(), {'page': 4})
        self.assertIs(first.flush(old), ProgressStatus.STALE)
        self.assertEqual(self.local_progress().load(), {'page': 4})

    def test_identity_isolates_sibling_files_and_copies(self):
        sibling = self.local / self.book.name
        copy = self.nested / 'copy.epub'
        for path in (sibling, copy):
            shutil.copyfile(self.book, path)
        original = self.local_progress()
        original.save({'page': 9})
        for path in (sibling, copy):
            state = self.local_progress(path=path)
            self.assertNotEqual(state.identity, original.identity)
            self.assertEqual(state.load(), {})
            self.assertIs(state.load_status, ProgressStatus.ABSENT)

    def test_registered_ios_documents_identity_survives_container_relocation(self):
        app = SimpleNamespace(private_root=self.root / 'old' / 'Private')
        documents = self.root / 'old' / 'Documents'
        book = documents / 'Local' / 'nested' / self.book.name
        book.parent.mkdir(parents=True)
        shutil.copyfile(self.book, book)
        app.private_root.mkdir()
        use_shared_local(app.private_root, documents)
        state = open_progress(LocalFiles(documents / 'Local'), 'nested/book.epub',
                              app.private_root, app=app, kind='epub')
        state.save({'page': 5})

        (self.root / 'old').rename(self.root / 'new')
        app.private_root = self.root / 'new' / 'Private'
        use_shared_local(app.private_root, self.root / 'new' / 'Documents')
        old_reference = '/private/var/mobile/Containers/Data/Application/old-uuid/Documents/Local/nested/book.epub'
        reopened = open_progress(None, old_reference, app.private_root, app=app, kind='epub')
        self.assertEqual(reopened.identity, state.identity)
        self.assertEqual(reopened.load(), {'page': 5})
        unrelated = str(book)
        self.assertNotEqual(document_identity(None, unrelated, app=app), state.identity)

    def test_registered_external_root_id_survives_path_change(self):
        other = self.root / 'external'
        self.local.rename(other)
        first = document_identity(None, other / 'nested/book.epub', managed_roots={'disk-a': other})
        relocated = self.root / 'mount'
        other.rename(relocated)
        second = document_identity(LocalFiles(relocated / 'nested'), 'book.epub',
                                   managed_roots={'disk-a': relocated})
        self.assertEqual(first, second)
        self.assertNotEqual(first, document_identity(None, relocated / 'nested/book.epub',
                                                    managed_roots={'disk-b': relocated}))

    def test_external_video_rename_follows_the_verified_file_but_copies_are_independent(self):
        source = self.root / 'original.mp4'
        source.write_bytes(b'synthetic video samples')
        provider = LocalFiles(self.root)

        def progress(path):
            return open_progress(provider, path.name, self.root, kind='video',
                                 revision='a' * 64, follow_local_rename=True)

        original = progress(source)
        original.save({'position': 731})
        renamed = source.with_name('renamed.mp4')
        source.rename(renamed)
        copy = source.with_name('copy.mp4')
        shutil.copy2(renamed, copy)
        self.assertEqual(progress(renamed).load(), {'position': 731})
        self.assertEqual(progress(copy).load(), {})

    def test_latest_visible_observation_wins_even_before_it_is_written(self):
        first, second = self.local_progress(), self.local_progress()
        first.load()
        second.load()
        older = first.observe({'page': 17})
        newer = second.observe({'page': 4})
        self.assertEqual(self.local_progress().load(), {'page': 4})
        self.assertIs(first.flush(older), ProgressStatus.STALE)
        self.assertIs(second.flush(newer), ProgressStatus.SAVED)
        self.assertEqual(self.local_progress().load(), {'page': 4})

    def test_coalescing_keeps_interleaved_positions_and_distinct_bookmark_fields(self):
        writer = self.local_progress()
        writer.observe({'page': 7})
        writer.observe_bookmarks({'bookmarks': [2]})
        latest = writer.observe_bookmarks({'epub_bookmarks': [[3, 12]]})
        self.assertIs(writer.flush(latest), ProgressStatus.SAVED)
        self.assertEqual(self.local_progress().load(),
                         {'page': 7, 'bookmarks': [2], 'epub_bookmarks': [[3, 12]]})
        writer.observe_bookmarks({'bookmarks': []})
        latest = writer.observe({'page': 8})
        self.assertIs(writer.flush(latest), ProgressStatus.SAVED)
        self.assertEqual(self.local_progress().load(),
                         {'page': 8, 'bookmarks': [], 'epub_bookmarks': [[3, 12]]})

    def test_clear_retires_observations_and_preserves_bookmarks_and_recent(self):
        writer = self.local_progress()
        writer.save({'page': 3, 'bookmarks': [2]})
        pending = writer.observe({'page': 8})
        recent = self.root / 'recent-documents.json'
        recent.write_text('[]')
        clear_saved_positions(self.root, mobile=True)
        self.assertIs(writer.flush(pending), ProgressStatus.FENCED)
        self.assertIsNone(writer.observe({'page': 13}))
        self.assertFalse(list((self.root / 'ReaderPositions').rglob('*.json')))
        self.assertEqual(recent.read_text(), '[]')
        new = self.local_progress()
        self.assertEqual(new.load(), {'bookmarks': [2]})
        self.assertIs(new.load_status, ProgressStatus.ABSENT)
        self.assertFalse(new.can_import_legacy)
        self.assertIs(new.save({'page': 4}), ProgressStatus.SAVED)
        bookmark = writer.observe_bookmarks({'bookmarks': [2, 4]})
        self.assertIs(writer.flush(bookmark), ProgressStatus.SAVED)
        self.assertEqual(new.load(), {'page': 4, 'bookmarks': [2, 4]})

    def test_managed_folder_move_transfers_only_same_file_progress_and_bookmarks(self):
        from commonUtils.persistence.publication import mutation_lock

        app = SimpleNamespace(private_root=self.root)
        provider = LocalFiles(self.local)
        old_path, target = 'nested/book.epub', 'renamed/book.epub'
        old = self.local_progress(provider, old_path, revision=provider.entry(old_path)['revision'])
        old.save({'page': 7, 'bookmarks': [2]})
        pending = old.observe({'page': 8})
        with mutation_lock:
            relocate = prepare_local_progress_move(app, provider, 'nested', provider, 'renamed',
                                                   cancelled=lambda: False)
            provider.rename('nested', 'renamed')
            relocate()
        self.assertIs(old.flush(pending), ProgressStatus.FENCED)
        reopened = self.local_progress(provider, target, revision=provider.entry(target)['revision'])
        self.assertEqual(reopened.load(), {'page': 7, 'bookmarks': [2]})
        self.nested.mkdir()
        shutil.copyfile(self.local / target, self.book)
        copy = self.local_progress(provider, old_path, revision=provider.entry(old_path)['revision'])
        self.assertEqual(copy.load(), {})

    def test_revision_change_and_corrupt_or_unknown_checkpoint_are_distinct(self):
        state = self.local_progress(revision=(1, 2))
        state.save({'page': 3})
        changed = self.local_progress(revision=(3, 4))
        self.assertEqual(changed.load(), {})
        self.assertIs(changed.load_status, ProgressStatus.INCOMPATIBLE)
        path, = (self.root / 'ReaderPositions').rglob('*.json')
        record = json.loads(path.read_bytes())
        for damaged in (b'bad json', json.dumps(dict(record, version=99)).encode()):
            with self.subTest(damaged=damaged[:20]):
                path.write_bytes(damaged)
                opened = self.local_progress(revision=(1, 2))
                self.assertEqual(opened.load(), {})
                self.assertIs(opened.load_status, ProgressStatus.ERROR)
                self.assertIs(opened.save({'page': 0}), ProgressStatus.WRITE_FAILED)
                self.assertEqual(path.read_bytes(), damaged)
                opened.retire()

    def test_interrupted_atomic_publish_preserves_durable_state_and_latest_retry(self):
        state = self.local_progress()
        state.save({'page': 3})
        path, = (self.root / 'ReaderPositions').rglob('*.json')
        original = path.read_bytes()
        observed = state.observe({'page': 9})
        with patch('commonUtils.persistence.atomic.os.replace', side_effect=OSError('disk full')):
            self.assertIs(state.flush(observed), ProgressStatus.WRITE_FAILED)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.local_progress().load(), {'page': 9})
        self.assertIs(state.flush(), ProgressStatus.SAVED)
        self.assertEqual(self.local_progress().load(), {'page': 9})
        self.assertEqual(set(path.parent.iterdir()), {path})

    def test_saved_mobile_uses_shared_session_memory_and_revocation_fences_cache(self):
        client = SimpleNamespace(
            generation=1, connection_identity=lambda remote: 'remote-identity',
            package_records=[dict(saved=True, document_cache_id='not-a-zip-grant',
                                  identities={'Drive': 'remote-identity'})],
        )
        app = SimpleNamespace(cloud_client=client, private_root=self.root)
        provider = SimpleNamespace(client=client, remote='Drive', private=True, identity='remote-identity')
        first = self.private_progress(provider, app=app)
        self.assertIs(first.mode, ProgressMode.SESSION_MEMORY)
        self.assertEqual(first.load(), {})
        self.assertIs(first.load_status, ProgressStatus.SESSION_ONLY)
        self.assertIs(first.save({'page': 4}), ProgressStatus.SESSION_ONLY)
        second = self.private_progress(provider, app=app)
        self.assertEqual(second.load(), {'page': 4})
        second.observe_bookmarks({'bookmarks': [2]})
        second.observe({'page': 5})
        token = second.observe_bookmarks({'epub_bookmarks': [[1, 20]]})
        self.assertIs(second.flush(token), ProgressStatus.SESSION_ONLY)
        self.assertEqual(first.load(), {'page': 5, 'bookmarks': [2], 'epub_bookmarks': [[1, 20]]})
        self.assertIs(first.save({'bookmarks': []}), ProgressStatus.SESSION_ONLY)
        self.assertEqual(second.load(), {'page': 5, 'bookmarks': [], 'epub_bookmarks': [[1, 20]]})
        self.assertFalse((self.root / 'ReaderPositions').exists())
        self.assertFalse((self.root / 'ReaderKeys').exists())
        client.generation += 1
        self.assertEqual(second.load(), {})
        self.assertIs(second.load_status, ProgressStatus.FENCED)
        reopened = self.private_progress(provider, app=app)
        self.assertEqual(reopened.load(), {})
        self.assertIs(reopened.load_status, ProgressStatus.SESSION_ONLY)

    def test_mobile_progress_uses_the_admitted_alias_credential(self):
        for field in ('identities', 'crypt_identities'):
            with self.subTest(field=field):
                client = SimpleNamespace(generation=1, package_records=[
                    dict(saved=False, document_cache_id='first-zip', **{field: {'Drive': 'same-settings'}}),
                    dict(saved=True, **{field: {'Drive @ Saved': 'same-settings'}}),
                    dict(saved=False, document_cache_id='second-zip', **{field: {'Drive @ Second': 'same-settings'}}),
                ])
                app = SimpleNamespace(cloud_client=client, private_root=self.root)

                def provider(alias):
                    return SimpleNamespace(client=client, remote=alias, private=True, identity='same-settings')

                saved = self.private_progress(provider('Drive @ Saved'), app=app)
                self.assertIs(saved.mode, ProgressMode.SESSION_MEMORY)
                for alias, grant in (('Drive', 'first-zip'), ('Drive @ Second', 'second-zip')):
                    state = CredentialState(provider(alias), 'book.epub', self.root, kind='epub', app=app)
                    self.assertEqual(state.cipher.identity, grant)
                missing = self.private_progress(provider('Drive @ Missing'), app=app)
                self.assertIs(missing.mode, ProgressMode.SESSION_MEMORY)
                client.package_records.append(dict(saved=True, remotes=['Drive']))
                ambiguous = self.private_progress(provider('Drive'), app=app)
                self.assertIs(ambiguous.mode, ProgressMode.SESSION_MEMORY)

    def test_offline_download_and_remote_original_are_distinct(self):
        client = SimpleNamespace(generation=1, connection_identity=lambda remote: 'connection')
        app = SimpleNamespace(cloud_client=client, private_root=self.root)
        copies = SimpleNamespace(client=client,
                                 document_capabilities=SimpleNamespace(credential_bound=True),
                                 record=lambda key: dict(remote='Drive', identity='connection'))
        key = 'a' * 32
        download = SimpleNamespace(copies=copies, key=key, client=client,
                                   remote='Drive', private=True, identity='connection')
        remote = SimpleNamespace(client=client, remote='Drive', remote_storage=True, identity='connection')
        self.assertEqual(document_identity(copies, key, app=app),
                         document_identity(download, 'book.epub', app=app))
        self.assertNotEqual(document_identity(remote, key, app=app),
                            document_identity(download, 'book.epub', app=app))

    def test_unavailable_offline_copy_lookup_cannot_grant_persistence(self):
        def missing(_):
            raise FileNotFoundError('Synthetic record removed')

        client = SimpleNamespace(generation=1)
        app = SimpleNamespace(cloud_client=client, private_root=self.root)
        copies = SimpleNamespace(client=client, record=missing,
                                 document_capabilities=SimpleNamespace(private=True, credential_bound=True))
        identity = document_identity(copies, 'a' * 32, app=app)
        self.assertEqual(identity[0], 'protected')
        self.assertEqual(identity[2], 'offline-copy-unavailable')
        state = self.private_progress(copies, 'a' * 32, app=app)
        self.assertIs(state.mode, ProgressMode.SESSION_MEMORY)
        self.assertFalse((self.root / 'ReaderKeys').exists())

    def test_mobile_session_only_zip_checkpoint_follows_the_original_remote_name(self):
        import pyzipper

        def request(action, *, id, data):
            self.assertEqual(id, 'actual-zip-grant')
            data = base64.b64decode(data)
            if action == 'document_lists_seal':
                with BytesIO() as buffer:
                    with pyzipper.AESZipFile(buffer, 'w', encryption=pyzipper.WZ_AES) as archive:
                        archive.setpassword(b'fixture-zip-password')
                        archive.writestr('entries.json', data)
                    return base64.b64encode(buffer.getvalue()).decode()
            self.assertEqual(action, 'document_lists_open')
            with pyzipper.AESZipFile(BytesIO(data)) as archive:
                archive.setpassword(b'fixture-zip-password')
                return base64.b64encode(archive.read('entries.json')).decode()

        client = SimpleNamespace(generation=1, connection_identity=lambda remote: 'connection', request=request)
        app = SimpleNamespace(cloud_client=client, private_root=self.root)

        def provider(alias):
            client.package_records = [dict(saved=False, document_cache_id='actual-zip-grant',
                                           aliases={'Drive': alias}, identities={alias: 'connection'})]
            return SimpleNamespace(client=client, remote=alias, remote_storage=True, identity='connection')

        old = provider('Drive @ First')
        legacy = CredentialState(old, 'book.epub', self.root, kind='epub', app=app)
        legacy.save({'page': 3})
        first = self.private_progress(old, 'book.epub', app=app)
        self.assertIs(first.mode, ProgressMode.ENCRYPTED)
        self.assertEqual(first.load(), {'page': 3})
        self.assertIs(first.save({'page': 9}), ProgressStatus.SAVED)
        client.generation += 1
        second = self.private_progress(provider('Drive @ Second'), 'book.epub', app=app)
        self.assertEqual(first.identity, second.identity)
        self.assertEqual(second.load(), {'page': 9})

    def test_encrypted_v2_uses_real_aes_migrates_and_clear_preserves_bookmarks(self):
        import pyzipper

        provider = self.unlock('old-password')
        state = self.private_progress(provider)
        self.assertIs(state.mode, ProgressMode.ENCRYPTED)
        self.assertIs(state.save({'page': 7, 'bookmarks': [3], 'locator': 'private-anchor'}),
                      ProgressStatus.SAVED)
        path, = (self.root / 'ReaderPositions').glob('*.zip')
        original = path.read_bytes()
        self.assertNotIn(b'private-title', original)
        self.assertNotIn(b'private-anchor', original)
        self.assertFalse(list((self.root / 'ReaderPositions').rglob('*.json')))
        with pyzipper.AESZipFile(path) as archive:
            archive.setpassword(b'wrong-password')
            with self.assertRaises(RuntimeError):
                archive.read('state.json')
            archive.setpassword(b'old-password')
            record = json.loads(archive.read('state.json'))
        self.assertEqual(record['version'], 2)
        self.assertEqual(record['state']['locator'], 'private-anchor')
        self.assertEqual(record['identity'], path.stem)
        self.assertEqual(self.private_progress(provider).load()['page'], 7)

        replacement = self.unlock('new-password')
        locked = self.private_progress(replacement)
        self.assertEqual(locked.load(), {})
        self.assertIs(locked.load_status, ProgressStatus.LOCKED)
        self.assertIs(locked.save({'page': 0}), ProgressStatus.LOCKED)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(migrate(self.root, 'old-password'), {'migrated': 4, 'preserved': 0})
        locked.retire()
        self.assertEqual(self.private_progress(replacement).load()['page'], 7)

        # Clear succeeds with no key and the bookmark remains independently protected.
        retired = self.private_progress(replacement)
        pending = retired.observe({'page': 13})
        session.forget(self.context)
        clear_saved_positions(self.root)
        self.assertIs(retired.flush(pending), ProgressStatus.FENCED)
        self.assertFalse(path.exists())
        reopened = self.private_progress(self.unlock('new-password'))
        self.assertEqual(reopened.load(), {'bookmarks': [3]})

    def test_version_one_encrypted_position_imports_in_place(self):
        provider = self.unlock('old-password')
        legacy = CredentialState(provider, 'private-title.epub', self.root,
                                 kind='epub', revision=(1, b'copy record'))
        legacy.save({'page': 6, 'bookmarks': [4]})
        state = self.private_progress(provider, revision=(1, b'copy record'))
        self.assertEqual(state.load(), {'page': 6, 'bookmarks': [4]})
        self.assertIs(state.save({'page': 7}), ProgressStatus.SAVED)
        self.assertEqual(legacy.load(), {'page': 7, 'bookmarks': [4]})
        self.assertEqual(len(list((self.root / 'ReaderPositions').glob('*.zip'))), 1)

    def test_revocation_during_encryption_preserves_prior_checkpoint(self):
        provider = self.unlock('old-password')
        state = self.private_progress(provider)
        state.save({'page': 2})
        path, = (self.root / 'ReaderPositions').glob('*.zip')
        original = path.read_bytes()
        transform = DesktopCredentialCipher.transform

        def revoked_during_encryption(cipher, data, decode=False):
            transformed = transform(cipher, data, decode)
            if not decode:
                session.forget(self.context)
            return transformed

        observed = state.observe({'page': 99})
        with patch.object(DesktopCredentialCipher, 'transform', revoked_during_encryption):
            self.assertIs(state.flush(observed), ProgressStatus.FENCED)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.private_progress(self.unlock('old-password')).load(), {'page': 2})
