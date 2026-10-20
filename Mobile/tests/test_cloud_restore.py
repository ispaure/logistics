"""Saved connections must be ready before hubs and cloud document reopening."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock, patch

from features.rclone.mobile.cloud_ui import CloudUI
from features.rclone.mobile.document_lists import CredentialDocumentLists
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.document_sources import _reopen_file, source_icons
from logisticsmobile.workspace import Session


class CloudRestoreTests(IsolatedAsyncioTestCase):
    async def test_workspace_phase_waits_for_saved_connections_without_presenting_cloud(self):
        ready = asyncio.Event()
        restore = asyncio.create_task(ready.wait())
        app = SimpleNamespace(show_cloud=Mock(), cloud_restore_task=restore)
        phase = asyncio.create_task(LogisticsMobile._prepare_startup_phase(app, 6))
        await asyncio.sleep(0)
        app.show_cloud.assert_called_once_with(present=False)
        self.assertFalse(phase.done())
        ready.set()
        await phase

    async def test_identity_check_waits_for_restore_before_capturing_credential_generation(self):
        client = SimpleNamespace(generation=0, connection_identity=Mock(return_value='identity'))
        ready = asyncio.Event()
        async def restore():
            await ready.wait()
            client.generation += 1
        app = SimpleNamespace(cloud_client=client, active_host=True, navigation_generation=1,
            cloud_restore_task=asyncio.create_task(restore()), loaded_remote_names=lambda: [],
            require_remote_credentials=Mock(return_value=False))
        opening = asyncio.create_task(CloudUI.require_remote_credentials_async(app, 'Drive', identity='identity'))
        await asyncio.sleep(0)
        client.connection_identity.assert_not_called()
        ready.set()
        self.assertTrue(await opening)
        app.require_remote_credentials.assert_not_called()

    async def test_remote_and_crypt_reopens_continue_after_restore_without_password_prompt(self):
        for kind in ('remote', 'crypt'):
            with self.subTest(kind=kind):
                ready = asyncio.Event()
                client = SimpleNamespace(request=Mock(return_value={'identity': 'identity'}))
                copies = SimpleNamespace(provider=SimpleNamespace(identity='identity'))
                app = SimpleNamespace(show_cloud=Mock(), active_host=True, navigation_generation=1,
                    cloud_client=client, cloud_restore_task=asyncio.create_task(ready.wait()),
                    private_root=None, require_remote_credentials_async=AsyncMock(return_value=True),
                    open_crypt=AsyncMock(return_value=True))
                source = dict(type=kind, remote='Drive', identity='identity', key='Notes.md', namespace='copy')
                with patch('features.rclone.mobile.remote_readers.RemoteReaders', return_value=copies), \
                        patch('features.rclone.localcrypt.mobile.resources.CryptFiles'), \
                        patch('features.rclone.localcrypt.mobile.resources.ManagedCopies', return_value=copies), \
                        patch('features.rclone.mobile.storage_location.collection_path'):
                    opening = asyncio.create_task(_reopen_file(app, source))
                    await asyncio.sleep(0)
                    client.request.assert_not_called()
                    app.open_crypt.assert_not_awaited()
                    ready.set()
                    self.assertTrue(await opening)
                app.open_crypt.assert_awaited_once_with(copies=copies, key='Notes.md')
                if kind == 'crypt':
                    app.require_remote_credentials_async.assert_not_awaited()

    async def test_navigation_away_during_restore_does_not_resume_document_open(self):
        ready = asyncio.Event()
        app = SimpleNamespace(show_cloud=Mock(), active_host=True, navigation_generation=1,
            cloud_restore_task=asyncio.create_task(ready.wait()), open_crypt=AsyncMock())
        opening = asyncio.create_task(_reopen_file(app,
            dict(type='remote', remote='Drive', identity='identity', key='Notes.md')))
        await asyncio.sleep(0)
        app.navigation_generation += 1
        ready.set()
        self.assertFalse(await opening)
        app.open_crypt.assert_not_awaited()

    async def test_saved_credential_publication_refreshes_home_and_documents_badges(self):
        app = SimpleNamespace(active_host=True, loop=asyncio.get_running_loop(), routes=object(),
                              refresh_hub=Mock())
        cache = SimpleNamespace(app=app, views_pending=False, refresh=Mock())
        cache.queue_views = lambda: CredentialDocumentLists.queue_views(cache)
        cache.refresh_views = lambda: CredentialDocumentLists.refresh_views(cache)
        CredentialDocumentLists.credentials_changed(cache)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        cache.refresh.assert_called_once_with()
        self.assertEqual([call.args for call in app.refresh_hub.call_args_list], [('home',), ('documents',)])


class SavedConnectionStartupTests(TestCase):
    def test_workspace_preparation_restores_saved_client_and_unlocks_recent_badge(self):
        class Client:
            vault = object()
            generation = 0
            package_name = ''
            package_records = ()

            def restore(self):
                self.package_name = 'Saved.zip'
                self.package_records = (dict(package_name='Saved.zip', saved=True,
                    remotes=['Drive'], identities={'Drive': 'identity'}),)
                self.generation += 1
                return ['Drive']

            def crypt_remotes(self):
                return []

            def cancel(self):
                pass

        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.cloud_client = Client()
            session = Session('recent', 'file-reference', 'file', 'markdown')
            session.source = dict(type='remote', remote='Drive', identity='identity', key='Notes.md')
            self.assertEqual(source_icons(app, session)[-1][0], 'storage_crypt')
            with patch.object(CloudUI, 'retained_packages', return_value=None):
                app.loop.run_until_complete(app._prepare_startup_phase(6))
            self.assertEqual(app.loaded_remote_names(), ['Drive'])
            self.assertEqual(source_icons(app, session)[-1][0], 'storage_unlocked')
            self.assertEqual(app.native_host.state.destination, 'home')
