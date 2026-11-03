"""Exercise choose/password/load, retries and bounded picker access."""

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

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

    def choose(self, *, encrypted):
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
        with patch('mobile.pickers.pick_document', new=AsyncMock(return_value=(LocalDocuments(), source))) as picker:
            self.app.loop.run_until_complete(self.app.begin_cloud_import())
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
        picker = self.choose(encrypted=True)
        self.assertEqual(self.client.calls, [])
        self.dialog.assert_not_awaited()
        self.assertEqual(self.app.routes.screens['settings'][-1][0], 'import-credentials-password')
        selected = self.app.cloud_pending_zip
        self.app.cloud_password.value = 'wrong'
        self.app.loop.run_until_complete(self.app.cloud_import.on_press())
        self.assertIs(self.app.cloud_pending_zip, selected)
        self.assertEqual(self.app.cloud_password.value, '')
        self.assertIn('Check the password', self.app.cloud_import_message.text)
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
