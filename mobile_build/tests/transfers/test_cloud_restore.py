"""Home/local actions stay usable while cloud-backed reopens await credentials."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock, patch

from features.rclone.mobile.cloud_ui import CloudUI
from features.rclone.mobile.document_lists import CredentialDocumentLists
from mobile.app import LogisticsMobile
from mobile.document_sources import _reopen_file, source_icons
from mobile.workspace import Session
from mobile.startup import finish_startup, restore_cloud_in_background


class CloudRestoreTests(IsolatedAsyncioTestCase):
    async def test_workspace_phase_does_not_initialize_or_wait_for_cloud(self):
        ready = asyncio.Event()
        restore = asyncio.create_task(ready.wait())
        app = SimpleNamespace(show_cloud=Mock(), cloud_restore_task=restore)
        try:
            await asyncio.wait_for(LogisticsMobile._prepare_startup_phase(app, 6), .2)
            app.show_cloud.assert_not_called()
            self.assertFalse(restore.done())
        finally:
            ready.set()
            await restore

    async def test_home_ready_before_background_restore(self):
        ready = asyncio.Event()
        restore = asyncio.create_task(ready.wait())
        screen = SimpleNamespace(progress=SimpleNamespace(value=0), show_step=Mock(),
            reveal_workspace=AsyncMock())
        app = SimpleNamespace(loop=asyncio.get_running_loop(), active_host=True,
            _startup_steps=lambda: iter(()), startup_screen=screen,
            _startup_in_progress=True, resize_workspace=Mock(), start_cloud_restore=Mock(return_value=restore),
            cloud_restore_task=restore)
        app._start_background_cloud = lambda: setattr(app, 'cloud_startup_task',
            asyncio.create_task(restore_cloud_in_background(app)))
        self.assertTrue(await finish_startup(app))
        screen.reveal_workspace.assert_awaited_once_with(app)
        self.assertFalse(app._startup_in_progress)
        self.assertFalse(restore.done())
        await asyncio.sleep(.03)
        app.start_cloud_restore.assert_called_once_with()
        self.assertFalse(app.cloud_startup_task.done())
        ready.set()
        await app.cloud_startup_task

    async def test_retired_host_does_not_start_connections(self):
        app = SimpleNamespace(active_host=False, start_cloud_restore=Mock())
        await restore_cloud_in_background(app)
        app.start_cloud_restore.assert_not_called()

    async def test_background_connection_failure_does_not_fail_home(self):
        app = SimpleNamespace(active_host=True, start_cloud_restore=Mock(side_effect=OSError('private details')))
        with self.assertLogs('mobile.startup', level='ERROR') as logs:
            await restore_cloud_in_background(app)
        self.assertNotIn('private details', '\n'.join(logs.output))

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
                with patch('features.rclone.mobile.service.native_service') as service, \
                        patch('features.rclone.localcrypt.mobile.resources.ManagedCopies', return_value=copies), \
                        patch('features.rclone.mobile.storage_location.collection_path'):
                    service.return_value.remotes.open.return_value.readers.return_value = copies
                    service.return_value.localcrypt.open.return_value = copies.provider
                    opening = asyncio.create_task(_reopen_file(app, source))
                    await asyncio.sleep(0)
                    client.request.assert_not_called()
                    service.assert_not_called()
                    app.open_crypt.assert_not_awaited()
                    ready.set()
                    self.assertTrue(await opening)
                    service.assert_called_once_with(client)
                    if kind == 'remote':
                        location = service.return_value.remotes.open.call_args.args[0]
                        self.assertEqual((location.remote, location.identity), ('Drive', 'identity'))
                    else:
                        location = service.return_value.localcrypt.open.call_args.args[0]
                        self.assertEqual((location.remote, location.namespace, location.create), ('Drive', 'copy', False))
                app.open_crypt.assert_awaited_once_with(copies=copies, key='Notes.md')
                if kind == 'crypt':
                    app.require_remote_credentials_async.assert_not_awaited()

    async def test_changed_crypt_identity_closes_provider_before_reader_setup(self):
        client = SimpleNamespace(request=Mock(return_value={'identity': 'identity'}))
        provider = SimpleNamespace(identity='replacement', close=Mock())
        app = SimpleNamespace(show_cloud=Mock(), active_host=True, navigation_generation=1,
            cloud_client=client, cloud_restore_task=None, private_root=None,
            require_remote_credentials_async=AsyncMock(), open_crypt=AsyncMock())
        source = dict(type='crypt', remote='Drive', identity='identity', key='Notes.md', namespace='copy')
        with patch('features.rclone.mobile.service.native_service') as service, \
                patch('features.rclone.mobile.storage_location.collection_path'), \
                patch('features.rclone.localcrypt.mobile.resources.ManagedCopies') as readers:
            service.return_value.localcrypt.open.return_value = provider
            with self.assertRaisesRegex(ValueError, 'connection changed'):
                await _reopen_file(app, source)
            provider.close.assert_called_once_with()
            readers.assert_not_called()
            app.open_crypt.assert_not_awaited()

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
                              refresh_hub=Mock(), documents_sections=object())
        cache = SimpleNamespace(app=app, views_pending=False, refresh=Mock())
        cache.queue_views = lambda: CredentialDocumentLists.queue_views(cache)
        cache.refresh_views = lambda: CredentialDocumentLists.refresh_views(cache)
        CredentialDocumentLists.credentials_changed(cache)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        cache.refresh.assert_called_once_with()
        self.assertEqual([call.args for call in app.refresh_hub.call_args_list], [('home',), ('documents',)])

    async def test_credential_publication_does_not_construct_unopened_documents(self):
        app = SimpleNamespace(active_host=True, routes=object(), refresh_hub=Mock())
        CredentialDocumentLists.refresh_views(SimpleNamespace(app=app, views_pending=True))
        app.refresh_hub.assert_called_once_with('home')


class SavedConnectionStartupTests(TestCase):
    def test_workspace_preparation_restores_saved_client_and_unlocks_recent_badge(self):
        class Client:
            vault = object()
            generation = 0
            package_name = ''
            package_records = ()

            restore_count = 0

            def restore(self):
                self.restore_count += 1
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
            with patch.object(CloudUI, 'retained_packages', return_value=None), \
                    patch.object(app, 'clear_private_reader') as clear_reader, \
                    patch.object(app, 'clear_private_catalog') as clear_catalog:
                app._start_background_cloud()
                app.loop.run_until_complete(app.cloud_startup_task)
            clear_reader.assert_not_called()
            clear_catalog.assert_not_called()
            self.assertEqual(app.loaded_remote_names(), ['Drive'])
            self.assertEqual(source_icons(app, session)[-1][0], 'storage_unlocked')
            self.assertEqual(app.native_host.state.destination, 'home')
            self.assertFalse(hasattr(app, 'cloud_view'))
            self.assertEqual(app.cloud_client.restore_count, 1)
            app.cancel_cloud()  # Replacement/exit may cancel before a browser exists.
            with patch.object(CloudUI, 'retained_packages', return_value=None):
                app.change_folder_source('rclone')
            self.assertFalse(hasattr(app, 'cloud_view'))
            app.show_cloud(present=False)
            self.assertEqual(app.cloud_remote.value, 'Drive')
            self.assertEqual(app.cloud_client.restore_count, 1)
            self.assertFalse(app.cloud_retained_box.children)
            with patch.object(CloudUI, 'retained_packages', return_value=None):
                app.show_cloud_connections()
            self.assertTrue(app.cloud_retained_box.children)

    def test_opening_connection_ui_during_restore_keeps_one_task_and_busy_controls(self):
        from threading import Event
        started, release = Event(), Event()
        client = SimpleNamespace(vault=object(), generation=0, package_name='', package_records=(),
            crypt_remotes=lambda: [], cancel=lambda: None)
        calls = []
        def restore():
            calls.append(True)
            started.set()
            release.wait(3)
            client.package_name = 'Saved.zip'
            client.package_records = (dict(package_name='Saved.zip', saved=True,
                remotes=['Drive'], identities={'Drive': 'identity'}),)
            client.generation += 1
            return ['Drive']
        client.restore = restore
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.cloud_client = client
                with patch.object(CloudUI, 'retained_packages', return_value=None):
                    task = app.start_cloud_restore()
                    app.loop.run_until_complete(asyncio.sleep(.03))
                    self.assertTrue(started.is_set())
                    self.assertFalse(hasattr(app, 'cloud_view'))
                    app.show_cloud(present=False)
                    self.assertIs(app.cloud_restore_task, task)
                    self.assertTrue(app.cloud_busy)
                    self.assertFalse(app.cloud_remote.enabled)
                    release.set()
                    app.loop.run_until_complete(task)
                self.assertEqual(len(calls), 1)
                self.assertFalse(app.cloud_busy)
                self.assertEqual(app.cloud_remote.value, 'Drive')
            finally:
                release.set()
                pending = getattr(app, 'cloud_restore_task', None)
                if pending is not None and not pending.done():
                    app.loop.run_until_complete(pending)
                app.main_window.close()
                app.loop.close()
                LogisticsMobile.storage_root = None
