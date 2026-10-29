"""Recent provider files require durable credentials and keep no content or secrets."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock

from mobile.document_sources import file_source, source_icons, reopen_file
from mobile.recent_documents import RecentDocuments
from mobile.workspace import Session


class DocumentSourceTests(TestCase):
    def test_video_history_uses_saved_or_encrypted_credential_history(self):
        from services.documents.mobile_storage import remember_video
        for saved in (False, True):
            with self.subTest(saved=saved), TemporaryDirectory() as directory:
                app = self.app(saved=saved)
                app.recent_documents = RecentDocuments(Path(directory))
                app.credential_document_lists = Mock()
                copies = SimpleNamespace(remote_storage=True, remote='Drive', client=app.cloud_client)
                provider = SimpleNamespace(document_readers=lambda: copies)
                content = SimpleNamespace(provider=provider, path='Movie.mkv', restricted=not saved)
                remember_video(app, content)
                self.assertEqual(bool(app.recent_documents.items), saved)
                call = app.credential_document_lists.remember.call_args
                self.assertEqual(call.args[0].kind, 'video')
                self.assertFalse(call.kwargs['opened'])
                self.assertEqual(call.args[1]['key'], 'Movie.mkv')

    def test_local_video_appears_in_recent_history(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from services.documents.mobile_storage import remember_video
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = SimpleNamespace(recent_documents=RecentDocuments(root))
            remember_video(app, SimpleNamespace(provider=LocalFiles(root), path='Movie.avi', restricted=False))
            entry = app.recent_documents.sessions()[0]
            self.assertEqual((entry.title, entry.kind), ('Movie.avi', 'video'))
            self.assertEqual(entry.source, dict(type='local', path=str(root / 'Movie.avi')))

    def app(self, *, saved=False, retained=False):
        client = SimpleNamespace(package_records=[dict(remotes=['Drive'], saved=saved,
                                 identities={'Drive': 'a' * 64})],
                                 connection_identity=lambda remote: 'a' * 64)
        cache = SimpleNamespace(matching=lambda remote, identity: [('package', {})] if retained else [])
        return SimpleNamespace(cloud_client=client, retained_packages=lambda: cache)

    def test_plaintext_history_excludes_session_credentials_even_with_retained_zip(self):
        for saved, retained, expected in ((False, False, False), (True, False, True), (False, True, False)):
            app = self.app(saved=saved, retained=retained)
            copies = SimpleNamespace(encrypted=True, remote_storage=True, remote='Drive', client=app.cloud_client)
            source = file_source(app, copies, 'Notes.md')
            self.assertEqual(source is not None, expected)
            if source:
                self.assertEqual(source['identity'], 'a' * 64)
                self.assertEqual(source['type'], 'remote')

    def test_saved_remote_name_cannot_authorize_another_identity_in_plaintext_history(self):
        app = self.app(saved=True)
        copies = SimpleNamespace(encrypted=True, remote_storage=True, remote='Drive', client=app.cloud_client)
        app.cloud_client.package_records[0]['identities']['Drive'] = 'b' * 64
        self.assertIsNone(file_source(app, copies, 'Sensitive.md'))
        self.assertEqual(file_source(app, copies, 'Sensitive.md', session_only=True)['identity'], 'a' * 64)

    def test_stale_online_history_badge_uses_loaded_remote_name(self):
        app = self.app(saved=True)
        app.cloud_client.package_records[0]['identities']['Drive'] = 'b' * 64
        session = Session('', 'file-reference', 'a' * 64, 'pdf', title='Report.pdf')
        session.source = dict(type='remote', remote='Drive', identity='a' * 64, key='Report.pdf')
        self.assertEqual(source_icons(app, session)[-1], ('storage_unlocked', 'Connection unlocked'))

    def test_reference_roundtrip_ten_item_bound_and_reopen_metadata(self):
        with TemporaryDirectory() as directory:
            history = RecentDocuments(Path(directory))
            for index in range(12):
                session = Session('live', 'provider-session', str(index), 'pdf', title=f'File {index}.pdf', transient=True)
                history.remember_file(session, dict(type='local', path=f'/files/{index}.pdf'))
            restored = RecentDocuments(Path(directory))
            self.assertFalse(restored.error)
            self.assertEqual(len(restored.sessions()), 10)
            self.assertEqual(restored.sessions()[0].title, 'File 11.pdf')
            self.assertEqual(restored.sessions()[0].source, dict(type='local', path='/files/11.pdf'))
            self.assertNotIn('provider-session', restored.path.read_text())
            self.assertNotIn('password', restored.path.read_text())

    def test_source_icons_distinguish_local_cloud_and_locked_crypt(self):
        app = self.app(saved=True)
        app.cloud_client.connection_identity = Mock(side_effect=AssertionError('Badge must use credential snapshot'))
        app.cloud_client.request = Mock(side_effect=AssertionError('Badge must not wait on native I/O'))
        local = Session('local', 'managed-text', 'b' * 32, 'text')
        self.assertEqual(source_icons(app, local), [('storage_local', 'Local file')])
        session = Session('', 'file-reference', 'c' * 64, 'markdown')
        session.source = dict(type='remote', remote='Drive', identity='a' * 64, key='Notes.md')
        self.assertEqual([icon[0] for icon in source_icons(app, session)], ['storage_remote', 'storage_unlocked'])
        session.source['type'] = 'crypt'
        self.assertEqual([icon[0] for icon in source_icons(app, session)], ['storage_local', 'storage_crypt'])
        app.cloud_client.package_records[0]['crypt_identities'] = {'Drive': 'a' * 64}
        self.assertEqual(source_icons(app, session)[-1][0], 'storage_unlocked')
        app.cloud_client.package_records = []
        self.assertEqual(source_icons(app, session)[-1][0], 'storage_crypt')
        app.cloud_client.request.assert_not_called()
        app.cloud_client.connection_identity.assert_not_called()


class ReopenSourceTests(IsolatedAsyncioTestCase):
    async def test_downloaded_video_uses_decrypted_name_instead_of_opaque_cache_key(self):
        from unittest.mock import patch
        client = SimpleNamespace()
        copies = SimpleNamespace(client=client, record=lambda key: dict(identity='a' * 64))
        app = SimpleNamespace(cloud_client=client, show_cloud=Mock(), crypt_copies=copies,
                              require_remote_credentials_async=AsyncMock(return_value=True))
        provider = SimpleNamespace(name='Movie.mkv', close=Mock())
        source = dict(type='download', remote='Drive', identity='a' * 64, key='opaque-cache-id')
        with patch('features.rclone.localcrypt.mobile.resources.DownloadedCryptFile', return_value=provider), patch(
                'features.video.mobile.player.open_video', new_callable=AsyncMock, return_value=True) as open_video:
            self.assertTrue(await reopen_file(app, source, kind='video'))
            open_video.assert_awaited_once_with(app, provider, 'Movie.mkv')
            provider.close.assert_called_once()

    async def test_local_video_reopens_with_native_player(self):
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'Movie.avi'
            path.write_bytes(b'fixture')
            app = SimpleNamespace(require_document_feature=Mock(return_value=True), require_feature=Mock(return_value=True))
            with patch('features.video.mobile.player.open_video', new_callable=AsyncMock, return_value=True) as open_video:
                self.assertTrue(await reopen_file(app, dict(type='local', path=str(path))))
            self.assertEqual(open_video.await_args.args[1].root, path.parent)
            self.assertEqual(open_video.await_args.args[2], path.name)

    async def test_remote_video_rechecks_credentials_and_releases_initial_resource(self):
        from unittest.mock import patch
        app = SimpleNamespace(show_cloud=Mock(), require_remote_credentials_async=AsyncMock(return_value=True),
                              open_crypt=AsyncMock())
        service, resource = Mock(), Mock()
        service.remotes.open.return_value = resource
        with patch('features.rclone.mobile.service.native_service', return_value=service), patch(
                'features.video.mobile.player.open_video', new_callable=AsyncMock, return_value=True) as open_video:
            self.assertTrue(await reopen_file(app, dict(type='remote', remote='Drive', identity='a' * 64, key='Movie.mkv')))
            open_video.assert_awaited_once_with(app, resource, 'Movie.mkv')
            resource.close.assert_called_once()
            app.open_crypt.assert_not_awaited()

    async def test_ios_top_level_text_reopens_after_container_relocation(self):
        from services.documents.locations import use_shared_local, _shared_local_roots
        with TemporaryDirectory() as directory:
            private = Path(directory) / 'private'
            documents = Path(directory) / 'Documents'
            documents.mkdir()
            path = documents / 'Welcome to Local.txt'
            path.write_text('Welcome')
            use_shared_local(private, documents)
            self.addCleanup(_shared_local_roots.pop, private, None)
            app = SimpleNamespace(private_root=private, require_document_feature=Mock(return_value=True), show_cloud=Mock(), open_crypt=AsyncMock(return_value=True))
            old = '/var/mobile/Containers/Data/Application/OLD-CONTAINER/Documents/Welcome to Local.txt'
            from mobile.document_sources import local_reference_available
            self.assertTrue(local_reference_available(app, dict(type='local', path=old)))
            self.assertTrue(await reopen_file(app, dict(type='local', path=old)))
            copies = app.open_crypt.await_args.kwargs['copies']
            self.assertEqual(copies.provider.root, documents)
            self.assertEqual(copies.open(path.name).text, 'Welcome')

    async def test_missing_unrelated_path_is_not_retargeted_to_ios_documents(self):
        from services.documents.locations import use_shared_local, _shared_local_roots
        from mobile.document_sources import local_document_path
        with TemporaryDirectory() as directory:
            private = Path(directory) / 'private'
            documents = Path(directory) / 'Documents'
            documents.mkdir()
            (documents / 'notes.txt').write_text('Different file')
            use_shared_local(private, documents)
            self.addCleanup(_shared_local_roots.pop, private, None)
            app = SimpleNamespace(private_root=private)
            path = Path(directory) / 'missing' / 'notes.txt'
            self.assertEqual(local_document_path(app, path), path)

    async def test_locked_remote_waits_for_matching_credentials_before_opening(self):
        app = SimpleNamespace(show_cloud=Mock(), require_remote_credentials_async=AsyncMock(return_value=False),
                              open_crypt=AsyncMock())
        source = dict(type='remote', remote='Drive', identity='a' * 64, key='Notes.md')
        self.assertFalse(await reopen_file(app, source))
        app.open_crypt.assert_not_awaited()
        self.assertNotIn('identity', app.require_remote_credentials_async.await_args.kwargs)

    async def test_cloud_history_uses_current_connection_for_all_formats(self):
        from unittest.mock import patch
        from features.rclone.mobile.credential_state import NativeCredentialState
        state = NativeCredentialState()
        state.package_records = [dict(remotes=['Drive'], aliases={'Drive': 'Drive'},
                                      identities={'Drive': 'b' * 64})]
        async def require(remote, *, identity=None, resume=None):
            return remote == 'Drive' and identity in (None, 'b' * 64)
        app = SimpleNamespace(show_cloud=Mock(), cloud_client=SimpleNamespace(resolve_remote=state.resolve_remote),
                              require_remote_credentials_async=AsyncMock(side_effect=require),
                              open_crypt=AsyncMock(return_value=True))
        copies = object()
        resource = Mock()
        resource.readers.return_value = copies
        service = Mock()
        service.remotes.open.return_value = resource
        for filename in ('Notes.md', 'Notes.txt', 'Report.pdf', 'Book.epub', 'Comic.cbz'):
            with self.subTest(filename=filename), patch('features.rclone.mobile.service.native_service', return_value=service):
                source = dict(type='remote', remote='Drive @ Old package', identity='a' * 64, key=filename)
                self.assertTrue(await reopen_file(app, source))
                app.open_crypt.assert_awaited_with(copies=copies, key=filename)
                self.assertEqual(service.remotes.open.call_args.args[0].remote, 'Drive')
                self.assertIsNone(service.remotes.open.call_args.args[0].identity)

    async def test_local_text_reopens_with_original_provider_for_source_saves(self):
        with TemporaryDirectory() as directory:
            app = SimpleNamespace(require_document_feature=Mock(return_value=True), show_cloud=Mock(), open_crypt=AsyncMock(return_value=True))
            path = Path(directory) / 'notes.md'
            path.write_text('# Original')
            self.assertTrue(await reopen_file(app, dict(type='local', path=str(path))))
            values = app.open_crypt.await_args.kwargs
            self.assertEqual(values['copies'].provider.root, path.parent)
            self.assertEqual(values['key'], path.name)

    async def test_local_pdf_reopens_from_original_path(self):
        with TemporaryDirectory() as directory:
            app = SimpleNamespace(require_document_feature=Mock(return_value=True), open_download=AsyncMock(return_value=True))
            path = Path(directory) / 'report.pdf'
            path.write_bytes(b'%PDF-1.4')
            self.assertTrue(await reopen_file(app, dict(type='local', path=str(path))))
            app.open_download.assert_awaited_once_with(path=path, destination=None)
