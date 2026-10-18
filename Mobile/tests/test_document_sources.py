"""Recent provider files require durable credentials and keep no content or secrets."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock

from logisticsmobile.document_sources import file_source, source_icons, reopen_file
from logisticsmobile.recent_documents import RecentDocuments
from logisticsmobile.workspace import Session


class DocumentSourceTests(TestCase):
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
    async def test_locked_remote_waits_for_matching_credentials_before_opening(self):
        app = SimpleNamespace(show_cloud=Mock(), require_remote_credentials_async=AsyncMock(return_value=False),
                              open_crypt=AsyncMock())
        source = dict(type='remote', remote='Drive', identity='a' * 64, key='Notes.md')
        self.assertFalse(await reopen_file(app, source))
        app.open_crypt.assert_not_awaited()
        self.assertEqual(app.require_remote_credentials_async.await_args.kwargs['identity'], 'a' * 64)

    async def test_local_text_reopens_with_original_provider_for_source_saves(self):
        with TemporaryDirectory() as directory:
            app = SimpleNamespace(open_crypt=AsyncMock(return_value=True))
            path = Path(directory) / 'notes.md'
            path.write_text('# Original')
            self.assertTrue(await reopen_file(app, dict(type='local', path=str(path))))
            values = app.open_crypt.await_args.kwargs
            self.assertEqual(values['copies'].provider.root, path.parent)
            self.assertEqual(values['key'], path.name)

    async def test_local_pdf_reopens_from_original_path(self):
        app = SimpleNamespace(open_download=AsyncMock(return_value=True))
        self.assertTrue(await reopen_file(app, dict(type='local', path='/files/report.pdf')))
        app.open_download.assert_awaited_once_with(path=Path('/files/report.pdf'), destination='documents')
