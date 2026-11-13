"""Exercise choose/password/load, retries and bounded picker access."""

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from commonUtils.runtime.resources.documents import LocalDocuments
from mobile.app import LogisticsMobile
from features.rclone.mobile.credentials_ui import SelectedCredentialZIP


class AutomaticCredentialImportTests(unittest.TestCase):
    def setUp(self):
        from mobile_build.tests.transfers.test_credential_packages import CacheClient
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        LogisticsMobile.storage_root = self.root
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(close_loop, self.app.loop)
        self.addCleanup(self.app.main_window.close)

        class Client(CacheClient):
            def __init__(self):
                self.calls = []
                self.package_records = []
            def import_package(self, access, reference, password, *, remember=True):
                from zipfile import ZipFile
                from io import BytesIO
                self.calls.append((password, remember))
                with ZipFile(BytesIO(access.data)) as archive:
                    encrypted = any(item.flag_bits & 1 for item in archive.infolist())
                if encrypted and password != 'correct':
                    raise ValueError('Incorrect ZIP password')
                self.package_name = access.name
                self.generation += 1
                self.package_records = [dict(package_name=access.name, remotes=['Secret'], saved=remember)]
                return ['Secret']
        self.client = Client()
        self.app.cloud_client = self.client
        self.app.show_cloud_connections()
        self.enterContext(patch.object(self.app, 'retained_packages', return_value=None))
        self.dialog = self.enterContext(patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=False)))

    def archive(self, *, encrypted):
        from io import BytesIO
        from zipfile import ZipFile
        from mobile_build.tests.transfers.test_credential_packages import PACKAGE
        source = self.root / 'Personal.zip'
        if encrypted:
            source.write_bytes(PACKAGE)
        else:
            content = BytesIO()
            with ZipFile(content, 'w') as archive:
                archive.writestr('Secret.txt', 'type = local\n')
            source.write_bytes(content.getvalue())
        return LocalDocuments(), source

    def choose(self, *, encrypted):
        selected = self.archive(encrypted=encrypted)
        with patch('mobile.pickers.pick_document', new=AsyncMock(return_value=selected)) as picker:
            self.app.loop.run_until_complete(self.app.cloud_import_entry.on_press())
        return picker

    def test_plain_zip_imports_without_password_or_extra_import_tap(self):
        self.choose(encrypted=False)
        self.assertEqual(self.client.calls, [('', False)])
        self.assertEqual(self.app.routes.screens['settings'][-1][0], 'connections')
        self.assertIsNone(self.app.cloud_pending_zip)
        self.assertEqual(self.app.cloud_password.value, '')
        self.assertIn('Personal.zip added', self.app.cloud_connections_status.text)
        self.assertEqual(self.dialog.await_count, 1)

    def test_encrypted_zip_opens_password_panel_and_retries_same_file(self):
        owner = self.app.cloud_controller()
        state = owner.credential_workflow.state
        show_password = owner._show_cloud_import_password

        def advance(package):
            epoch = state.import_epoch
            self.assertIs(state.cloud_pending_zip, package)
            result = show_password(package)
            self.assertIs(state.cloud_pending_zip, package)
            self.assertEqual(state.import_epoch, epoch)
            return result

        with patch.object(owner, '_show_cloud_import_password', side_effect=advance) as password_route:
            picker = self.choose(encrypted=True)
        password_route.assert_called_once()
        self.assertEqual(self.client.calls, [])
        self.dialog.assert_not_awaited()
        self.assertEqual(self.app.routes.screens['settings'][-1][0], 'import-credentials-password')
        selected = self.app.cloud_pending_zip
        self.app.cloud_password.value = 'wrong'
        self.app.loop.run_until_complete(self.app.cloud_import.on_press())
        self.assertIs(self.app.cloud_pending_zip, selected)
        self.assertEqual(self.app.cloud_password.value, '')
        self.assertIn('Check the password', ' '.join(self.app.cloud_import_message.text.split()))
        self.app.cloud_password.value = 'correct'
        self.app.loop.run_until_complete(self.app.cloud_import.on_press())
        self.assertEqual(self.client.calls, [('wrong', False), ('correct', False)])
        self.assertEqual(self.dialog.await_count, 1)
        self.assertEqual(picker.await_count, 1)
        self.assertEqual(self.app.routes.screens['settings'][-1][0], 'connections')
        self.assertIsNone(self.app.cloud_pending_zip)

    def test_persistent_choice_is_explicit_and_passed_to_import(self):
        self.dialog.return_value = True
        self.choose(encrypted=False)
        self.assertEqual(self.client.calls, [('', True)])
        self.assertTrue(self.client.package_records[0]['saved'])
        self.assertEqual(self.dialog.await_count, 1)

    def test_persistent_password_retry_after_vault_attachment_advances_generation(self):
        self.dialog.return_value = True
        self.choose(encrypted=True)
        selected = self.app.cloud_pending_zip
        load = self.client.import_package
        generation = self.client.generation

        def load_after_vault_attachment(*args, remember):
            if not self.client.calls and remember:
                self.client.generation += 1
            return load(*args, remember=remember)

        with patch.object(self.client, 'import_package', side_effect=load_after_vault_attachment):
            self.app.cloud_password.value = 'wrong'
            self.app.loop.run_until_complete(self.app.cloud_import.on_press())
            self.assertEqual(self.client.generation, generation + 1)
            self.assertIs(self.app.cloud_pending_zip, selected)
            self.assertEqual(self.app.cloud_password.value, '')
            self.assertTrue(self.app.cloud_import.enabled)
            self.assertIn('Check the password', ' '.join(self.app.cloud_import_message.text.split()))
            self.app.cloud_password.value = 'correct'
            self.app.loop.run_until_complete(self.app.cloud_import.on_press())
        self.assertEqual(self.client.calls, [('wrong', True), ('correct', True)])
        self.assertEqual(self.dialog.await_count, 1)
        self.assertEqual(self.app.routes.screens['settings'][-1][0], 'connections')

    def test_empty_password_does_not_prompt_for_storage_or_load(self):
        self.choose(encrypted=True)
        self.app.loop.run_until_complete(self.app.cloud_import.on_press())
        self.dialog.assert_not_awaited()
        self.assertEqual(self.client.calls, [])
        self.assertIn('Enter the ZIP password', self.app.cloud_import_message.text)

    def test_back_from_password_clears_secret_and_pending_archive(self):
        self.choose(encrypted=True)
        self.app.cloud_password.value = 'never-publish'
        self.assertTrue(self.app.routes.back())
        self.assertEqual(self.app.cloud_password.value, '')
        self.assertIsNone(self.app.cloud_pending_zip)
        self.assertFalse(self.app.cloud_import.enabled)
        self.assertIs(self.app.cloud_import_message.parent, self.app.cloud_import_view.content)
        self.assertEqual(self.client.calls, [])

    def test_cancel_storage_choice_never_loads_credentials(self):
        self.dialog.return_value = None
        self.choose(encrypted=False)
        self.assertEqual(self.client.calls, [])
        self.assertIsNone(self.app.cloud_pending_zip)
        self.assertEqual(self.app.routes.screens['settings'][-1][0], 'connections')

    def test_cancel_picker_returns_to_packages_without_password_form(self):
        with patch('mobile.pickers.pick_document', new=AsyncMock(return_value=None)):
            self.app.loop.run_until_complete(self.app.begin_cloud_import())
        self.assertEqual(self.app.routes.screens['settings'][-1][0], 'connections')
        self.assertEqual(self.client.calls, [])
        self.assertIsNone(self.app.cloud_pending_zip)

    def test_navigation_during_picker_cannot_open_password_panel_or_import(self):
        source = self.root / 'unused.zip'
        async def choose_then_leave(*args):
            self.app.show_home()
            return LocalDocuments(), source
        with patch('mobile.pickers.pick_document', new=choose_then_leave):
            self.app.loop.run_until_complete(self.app.begin_cloud_import())
        self.assertEqual(self.app.native_host.state.destination, 'home')
        self.assertEqual(self.client.calls, [])
        self.assertIsNone(self.app.cloud_pending_zip)

    def test_invalid_file_reports_error_without_password_or_storage_prompt(self):
        source = self.root / 'invalid.zip'
        source.write_bytes(b'not a zip')
        with patch('mobile.pickers.pick_document', new=AsyncMock(return_value=(LocalDocuments(), source))):
            self.app.loop.run_until_complete(self.app.begin_cloud_import())
        self.assertIn('valid credential ZIP', self.app.cloud_import_message.text.replace('\n', ' '))
        self.assertEqual(self.app.routes.screens['settings'][-1][0], 'import-credentials')
        self.assertIsNone(self.app.cloud_pending_zip)
        self.assertEqual(self.client.calls, [])
        self.dialog.assert_not_awaited()

    def test_retiring_plain_route_during_preparation_refuses_native_commit(self):
        from features.rclone.mobile.credentials import NativeCredentials
        prepare = NativeCredentials.prepare
        started, release = Event(), Event()
        stages = []

        def prepare_then_wait(backend, request, password):
            stage = prepare(backend, request, password)
            stages.append(stage)
            stage.close = Mock(wraps=stage.close)
            started.set()
            if not release.wait(5):
                stage.close()
                raise TimeoutError('Credential preparation fixture did not release')
            return stage

        async def exercise():
            task = self.app.cloud_import_entry.on_press()
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                self.assertTrue(self.app.cloud_busy)
                self.trim_import('import-credentials')
                self.assertIsNone(self.app.cloud_pending_zip)
                self.assertEqual(self.app.cloud_password.value, '')
                self.assertTrue(self.app.cloud_busy)
                message = self.app.cloud_import_message.text
            finally:
                release.set()
                await task
            self.assertFalse(self.app.cloud_busy)
            self.assertEqual(self.client.calls, [])
            self.assertEqual(self.app.cloud_import_message.text, message)
            stages[0].close.assert_called_once()

        with patch('mobile.pickers.pick_document', new=AsyncMock(return_value=self.archive(encrypted=False))), \
                patch.object(NativeCredentials, 'prepare', prepare_then_wait):
            self.app.loop.run_until_complete(exercise())

    def test_retiring_password_route_at_process_lock_refuses_native_commit(self):
        self.choose(encrypted=True)
        entered, release = Event(), Event()

        @contextmanager
        def publication(*, blocking):
            self.assertFalse(blocking)
            entered.set()
            if not release.wait(5):
                raise TimeoutError('Credential lock fixture did not release')
            yield

        async def exercise():
            self.app.cloud_password.value = 'correct'
            task = self.app.cloud_import.on_press()
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                self.trim_import('import-credentials-password')
                self.assertEqual(self.app.routes.screens['settings'][-1][0], 'import-credentials')
                self.assertIsNone(self.app.cloud_pending_zip)
                self.assertEqual(self.app.cloud_password.value, '')
                self.assertTrue(self.app.cloud_busy)
                message = self.app.cloud_import_message.text
            finally:
                release.set()
                await task
            self.assertFalse(self.app.cloud_busy)
            self.assertEqual(self.client.calls, [])
            self.assertEqual(self.app.cloud_import_message.text, message)

        self.client.credential_state = SimpleNamespace(publication=publication)
        self.app.loop.run_until_complete(exercise())

    def test_retiring_persistent_import_during_vault_attachment_stops_zip_submission(self):
        from features.rclone.mobile.cloud import CloudClient
        from features.rclone.mobile.credential_state import NativeCredentialState

        client = CloudClient.__new__(CloudClient)
        client.credential_state = NativeCredentialState()
        client.package_name = ''
        client.vault_attached = False
        client.request = Mock(side_effect=AssertionError('Retired ZIP reached native submission'))
        self.app.cloud_client = client
        self.dialog.return_value = True
        self.choose(encrypted=True)
        client.vault = SimpleNamespace(set_label=Mock())
        started, release = Event(), Event()

        def attach_vault(*, create):
            self.assertTrue(create)
            started.set()
            if not release.wait(5):
                raise TimeoutError('Vault fixture did not release')
            client.credential_state.generation += 1
            client.vault_attached = True
            return []

        async def exercise():
            self.app.cloud_password.value = 'correct'
            task = self.app.cloud_import.on_press()
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                self.trim_import('import-credentials-password')
                self.assertIsNone(self.app.cloud_pending_zip)
                self.assertEqual(self.app.cloud_password.value, '')
                self.assertTrue(self.app.cloud_busy)
            finally:
                release.set()
                await task
            self.assertFalse(self.app.cloud_busy)
            self.assertTrue(client.vault_attached)
            client.request.assert_not_called()
            client.vault.set_label.assert_not_called()

        try:
            with patch.object(client, 'restore', side_effect=attach_vault):
                self.app.loop.run_until_complete(exercise())
        finally:
            self.app.cloud_client = self.client

    def test_retired_view_ignores_success_or_failure_after_native_commit(self):
        owner = self.app.cloud_controller()
        for error in (None, OSError('late metadata failure')):
            with self.subTest(error=error):
                started, release = Event(), Event()
                generation = self.client.generation

                def crypt_remotes():
                    started.set()
                    if not release.wait(5):
                        raise TimeoutError('Credential metadata fixture did not release')
                    if error:
                        raise error
                    return ['Late crypt']

                async def exercise():
                    task = self.app.cloud_import_entry.on_press()
                    try:
                        self.assertTrue(await asyncio.to_thread(started.wait, 2))
                        self.assertEqual(self.client.generation, generation + 1)
                        self.trim_import('import-credentials')
                        self.app.show_home()
                        self.app.cloud_status.value = 'Current remote status'
                        self.app.cloud_connections_status.text = 'Current connections status'
                        owner.cloud_crypt_remotes = {'Current crypt'}
                        message = self.app.cloud_import_message.text
                    finally:
                        release.set()
                        await task
                    self.assertEqual(self.app.native_host.state.destination, 'home')
                    self.assertFalse(self.app.cloud_busy)
                    self.assertIsNone(self.app.cloud_pending_zip)
                    self.assertEqual(self.app.cloud_status.value, 'Current remote status')
                    self.assertEqual(self.app.cloud_connections_status.text, 'Current connections status')
                    self.assertEqual(self.app.cloud_import_message.text, message)
                    self.assertEqual(owner.cloud_crypt_remotes, {'Current crypt'})

                self.app.show_cloud_connections()
                picker = AsyncMock(return_value=self.archive(encrypted=False))
                with patch('mobile.pickers.pick_document', new=picker), \
                        patch.object(self.client, 'crypt_remotes', side_effect=crypt_remotes), \
                        patch.object(owner.credential_workflow, 'remember_loaded_packages') as remember:
                    self.app.loop.run_until_complete(exercise())
                remember.assert_not_called()

    def test_route_host_uninstall_retires_picker_and_ignores_its_late_error(self):
        app = self.app

        async def exercise():
            started, release = asyncio.Event(), asyncio.Event()

            async def picker(host):
                self.assertIs(host, app)
                started.set()
                await release.wait()
                raise OSError('late picker failure')

            with patch('mobile.pickers.pick_document', new=picker):
                task = app.cloud_import_entry.on_press()
                try:
                    await asyncio.wait_for(started.wait(), 2)
                    app.routes.uninstall()
                    self.assertTrue(app.cloud_busy)
                    self.assertIsNone(app.cloud_pending_zip)
                    message = app.cloud_import_message.text
                finally:
                    release.set()
                    await task
            self.assertFalse(app.cloud_busy)
            self.assertEqual(self.client.calls, [])
            self.assertEqual(app.cloud_import_message.text, message)
            self.dialog.assert_not_awaited()

        app.loop.run_until_complete(exercise())

    def test_retired_import_cannot_replace_the_folder_hub_cache(self):
        folder = self.app.folder_controller()
        started, release = Event(), Event()

        def discover(*, roots):
            roots['Late folder'] = ('Secret', 'late-identity')
            started.set()
            if not release.wait(5):
                raise TimeoutError('Folder discovery fixture did not release')
            return {'Late folder': 'Secret'}

        async def exercise():
            task = self.app.cloud_import_entry.on_press()
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                self.assertEqual(self.client.calls, [('', False)])
                self.trim_import('import-credentials')
                folder.hub_crypt_locations = [('Current folder', 'Other')]
                folder.hub_crypt_roots = {'Current folder': ('Other', 'current-identity')}
                folder.folder_hub_error = 'Current discovery status'
            finally:
                release.set()
                await task
            self.assertEqual(folder.hub_crypt_locations, [('Current folder', 'Other')])
            self.assertEqual(folder.hub_crypt_roots, {'Current folder': ('Other', 'current-identity')})
            self.assertEqual(folder.folder_hub_error, 'Current discovery status')

        picker = AsyncMock(return_value=self.archive(encrypted=False))
        with patch.object(folder, 'existing_crypt_locations', side_effect=discover), \
                patch('mobile.pickers.pick_document', new=picker):
            self.app.loop.run_until_complete(exercise())

    def trim_import(self, route):
        routes = self.app.routes
        index = next(index for index, screen in enumerate(routes.screens['settings']) if screen[0] == route)
        routes.trim('settings', index)
        routes.render('settings')


class CredentialImportUITests(unittest.TestCase):
    def test_remote_selector_explains_available_crypts_and_selected_kind(self):
        class Client:
            def crypt_remotes(self): return ['Private', 'Books']
            def cancel(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            try:
                app.cloud_client = Client()
                app.show_cloud()
                app.loop.run_until_complete(app._load_crypt_remote_names())
                app.cloud_remote.items = ['Dropbox', 'Private', 'Books']
                self.assertIn('Crypt remotes: Books, Private', app.cloud_remote_help.text.replace('\n', ' '))
                self.assertIn('tap the name', app.cloud_remote_heading.text)
                app.cloud_remote.value = 'Private'
                self.assertIn('Crypt remote selected: Private', app.cloud_remote_help.text.replace('\n', ' '))
                self.assertIn('decrypted filenames', app.cloud_remote_help.text.replace('\n', ' '))
                self.assertFalse(hasattr(app, 'cloud_download'))
                self.assertFalse(hasattr(app, 'crypt_download'))
                app.cloud_crypt_remotes = set()
                app.cloud_remote.value = 'Dropbox'
                self.assertIn('No crypt remote', app.cloud_remote_help.text)
            finally:
                app.main_window.close()
                close_loop(app.loop)

    def test_zip_is_selected_before_password_and_failed_load_can_retry_without_picker(self):
        class Client:
            generation = 1
            def __init__(self): self.calls = []
            def import_package(self, access, reference, password, *, remember=True):
                with access.open(reference) as (name, stream):
                    self.calls.append((name, stream.read(), password, remember))
                if password != 'correct': raise ValueError('Incorrect ZIP password')
                self.package_name = name
                self.generation += 1
                return ['Example']
            def cancel(self): pass
            def clear(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            try:
                app.cloud_client = Client()
                app.show_cloud()
                self.assertEqual(app.cloud_import.text, 'Unlock')
                self.assertFalse(app.cloud_import.enabled)
                with patch('mobile.pickers.pick_document', new=AsyncMock()) as no_picker:
                    app.loop.run_until_complete(app.import_cloud_package(app.cloud_password))
                    no_picker.assert_not_awaited()
                source = Path(directory) / 'example.zip'
                source.write_bytes(b'encrypted fixture bytes')
                picker = AsyncMock(return_value=(LocalDocuments(), source))
                with patch('mobile.pickers.pick_document', new=picker):
                    app.loop.run_until_complete(app.choose_cloud_package())
                    self.assertEqual(app.cloud_client.calls, [])
                    self.assertIn('example.zip', app.cloud_selected_zip.text)
                    self.assertTrue(app.cloud_import.enabled)
                    source.unlink()  # Picker access was consumed and closed.
                    app.cloud_password.value = 'wrong'
                    app.loop.run_until_complete(app.import_cloud_package())
                    self.assertEqual(app.cloud_password.value, '')
                    self.assertTrue(app.cloud_import.enabled)
                    self.assertIn('tap Unlock again', app.cloud_import_message.text.replace('\n', ' '))
                    app.cloud_password.value = 'correct'
                    app.loop.run_until_complete(app.import_cloud_package())
                    self.assertEqual(picker.await_count, 1)
                self.assertEqual(app.cloud_remote.value, 'Example')
                self.assertIsNone(app.cloud_pending_zip)
                self.assertFalse(app.cloud_import.enabled)
                self.assertIn('Browse folder', app.cloud_import_message.text.replace('\n', ' '))
                self.assertEqual(app.cloud_password.value, '')
            finally:
                app.main_window.close()
                close_loop(app.loop)

    def test_cancelling_selection_keeps_loaded_remotes(self):
        class Client:
            def cancel(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            try:
                app.cloud_client = Client()
                app.show_cloud()
                app.cloud_remote.items = ['Existing']
                with patch('mobile.pickers.pick_document', new=AsyncMock(return_value=None)):
                    app.loop.run_until_complete(app.choose_cloud_package())
                self.assertEqual(app.cloud_remote.value, 'Existing')
                self.assertFalse(app.cloud_import.enabled)
            finally:
                app.main_window.close()
                close_loop(app.loop)

    def test_oversized_zip_is_rejected_before_loading(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'oversized.zip'
            source.write_bytes(b'X' * (1024 * 1024 + 1))
            with self.assertRaises(ValueError):
                SelectedCredentialZIP(LocalDocuments(), source)
