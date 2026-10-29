"""ZIP retention, saved-package migration and password-only session unlock."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import base64
from io import BytesIO
from zipfile import ZipFile
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock, AsyncMock
from mobile.app import LogisticsMobile
from features.rclone.mobile.credential_packages import CredentialPackages
from features.rclone.mobile.credentials_ui import SelectedCredentialZIP
from commonUtils.runtime.resources.documents import LocalDocuments


PACKAGE = (Path(__file__).resolve().parents[2] / 'rclone_bridge/testdata/credentials-aes256.zip').read_bytes()


class CacheClient:
    generation = 0
    package_name = 'Personal.zip'
    loaded = True
    remotes = ('Secret',)
    def request(self, action, **values):
        data = base64.b64decode(values['data'])
        return base64.b64encode(bytes(value ^ 125 for value in data)).decode()
    def connection_identity(self, remote):
        if not self.loaded:
            raise ValueError('Connection locked')
        return 'a' * 64
    def cancel(self): pass
    def crypt_remotes(self): return []
    def restore(self): return ['Secret']
    def lock(self):
        self.loaded = False
        self.package_name = ''
        self.generation += 1
    def import_package(self, access, reference, password, **kwargs):
        with access.open(reference) as (name, stream):
            assert stream.read() == PACKAGE
        if password != 'correct': raise ValueError('Incorrect ZIP password')
        self.generation += 1
        self.loaded = True
        return list(self.remotes)


class CredentialPackageTests(unittest.TestCase):
    def test_forgetting_one_retained_package_preserves_other_package_and_key(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            vault = SimpleNamespace(root=root, unlock=lambda **kw: dict(key='fixture'), forget=Mock())
            client = CacheClient()
            cache = CredentialPackages(vault, client)
            personal = cache.remember(SimpleNamespace(name='Personal.zip', data=PACKAGE), {'Secret': 'a' * 64})
            work = cache.remember(SimpleNamespace(name='Work.zip', data=PACKAGE), {'Team': 'b' * 64})
            other_scene = CredentialPackages(vault, client)
            cache.forget_package('Personal.zip')
            self.assertFalse(cache.path(personal).exists())
            self.assertTrue(cache.path(work).is_file())
            self.assertEqual(set(other_scene.items), {work})
            self.assertEqual(set(CredentialPackages(vault, client).items), {work})
            vault.forget.assert_not_called()
            cache.forget_package('Work.zip')
            vault.forget.assert_called_once()
            self.assertFalse(cache.index.exists())

    def test_unlock_repairs_older_remote_only_crypt_metadata_and_survives_relock(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.show_cloud(present=False)
            app.cloud_client = client = CacheClient()
            client.loaded = False
            client.remotes = ('Secret', 'RemoteOnly')
            client.crypt_remotes = lambda: ['Secret']
            vault = SimpleNamespace(root=root / 'Retained', unlock=lambda **kw: dict(key='fixture'))
            vault.root.mkdir()
            cache = CredentialPackages(vault, client)
            key = cache.remember(SimpleNamespace(name='Personal.zip', data=PACKAGE),
                                 {'Secret': 'a' * 64, 'RemoteOnly': 'b' * 64})
            self.assertNotIn('crypt_remotes', cache.items[key])
            with patch.object(app, 'retained_packages', return_value=cache) as retained, \
                    patch.object(app, 'refresh_hub_crypt_locations', new_callable=AsyncMock):
                app.main_window._impl.dialog_responses['QuestionDialog'] = [False]
                app.show_retained_unlock(key)
                app.credential_unlock_password.value = 'correct'
                app.loop.run_until_complete(app.credential_unlock_button.on_press())
                self.assertEqual(cache.items[key]['crypt_remotes'], ['Secret'])
                self.assertNotIn('correct', cache.index.read_text())
                app.loop.run_until_complete(app.lock_cloud())
                restored = CredentialPackages(vault, client)
                retained.return_value = restored
                with patch.object(client, 'request', side_effect=AssertionError('No bridge I/O for icons')):
                    app.folder_source = 'rclone'
                    app.build_folder_picker()
                    self.assertIn('Secret', app.folder_buttons)
                    self.assertIn('RemoteOnly', app.folder_buttons)
                    self.assertFalse((root / 'LocalCryptFolders').exists())

    def test_crypt_metadata_uses_retained_aliases_without_reclassifying_other_accounts(self):
        with TemporaryDirectory() as directory:
            vault = SimpleNamespace(root=Path(directory), unlock=lambda **kw: dict(key='fixture'))
            cache = CredentialPackages(vault, CacheClient())
            key = cache.remember(SimpleNamespace(name='Personal.zip', data=PACKAGE),
                                 {'Secret': 'a' * 64, 'Regular': 'b' * 64})
            cache.update_crypt_remotes(key, ['Secret @ Personal', 'Regular'],
                aliases={'Secret': 'Secret @ Personal', 'Regular': 'Regular @ Personal'})
            self.assertEqual(CredentialPackages(vault, CacheClient()).items[key]['crypt_remotes'], ['Secret'])

    def test_retained_packages_show_locked_cloud_rows_and_unlock_from_settings(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.show_cloud(present=False)
            app.cloud_client = CacheClient()
            app.cloud_client.loaded = False
            app.cloud_client.remotes = ('Secret', 'RemoteOnly')
            vault = SimpleNamespace(root=root / 'Retained', unlock=lambda **kw: dict(key='fixture'))
            vault.root.mkdir()
            cache = CredentialPackages(vault, app.cloud_client)
            key = cache.remember(SimpleNamespace(name='Personal.zip', data=PACKAGE),
                                 {'Secret': 'a' * 64, 'RemoteOnly': 'a' * 64}, crypt_remotes=['Secret'])
            with patch.object(app, 'retained_packages', return_value=cache):
                self.assertEqual(set(app.folder_choices()), {'All files', 'Received Files', 'Secret', 'RemoteOnly'})
                self.assertTrue(app.folder_choices()['RemoteOnly']['locked'])
                self.assertIn('Personal', app.credential_groups())
                app.show_cloud_connections()
                app.cloud_retained_buttons[key].on_press()
                self.assertEqual(app.routes.screens['settings'][-1][0], 'credential-package')
                app.main_window._impl.dialog_responses['QuestionDialog'] = [False, False]
                app.credential_unlock_password.value = 'wrong'
                app.loop.run_until_complete(app.credential_unlock_button.on_press())
                self.assertEqual(set(app.folder_choices()), {'All files', 'Received Files', 'Secret', 'RemoteOnly'})
                self.assertTrue(app.folder_choices()['RemoteOnly']['locked'])
                self.assertEqual(app.credential_unlock_password.value, '')
                app.credential_unlock_password.value = 'correct'
                app.loop.run_until_complete(app.credential_unlock_button.on_press())
                self.assertEqual(set(app.folder_choices()), {'All files', 'Received Files', 'Secret', 'RemoteOnly'})
                self.assertEqual(app.native_host.state.destination, 'settings')
                job = dict(id='b' * 32, remote='Secret', identity='a' * 64,
                           cipher_identity='c' * 64, crypt=True, prefix='', target='Secret')
                store = app.mirror_store()
                store.jobs[job['id']] = job
                store.target(job).mkdir(parents=True)
                app.loop.run_until_complete(app.lock_cloud())
                choices = app.folder_choices()
                self.assertEqual(set(choices), {'All files', 'Received Files', 'Secret', 'RemoteOnly'})
                self.assertEqual({copy['source'] for copy in choices['Secret']['copies']}, {'LocalCrypt', 'Remote'})
                self.assertIn('Personal', app.credential_groups())
                self.assertTrue(cache.path(key).is_file())

    def test_session_import_retains_encrypted_zip_but_never_saves_decoded_credentials(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.show_cloud(present=False)
                app.cloud_client = CacheClient()
                source = root / 'Personal.zip'
                source.write_bytes(PACKAGE)
                app.cloud_pending_zip = SelectedCredentialZIP(LocalDocuments(), source)
                app.cloud_remember.value = False
                app.cloud_password.value = 'correct'
                vault = SimpleNamespace(root=root / 'Retained', unlock=lambda **kw: dict(key='fixture'))
                vault.root.mkdir()
                cache = CredentialPackages(vault, app.cloud_client)
                with patch.object(app, 'retained_packages', return_value=cache) as retained, \
                        patch.object(cache, 'remember', wraps=cache.remember) as remember, \
                        patch.object(app.preferences, 'save', wraps=app.preferences.save) as save:
                    app.loop.run_until_complete(app.import_cloud_package())
                    save.assert_not_called()
                    self.assertEqual(app.cloud_password.value, '')
                    remember.assert_called_once()
                    self.assertEqual(len(cache.matching('Secret', 'a' * 64)), 1)
                    self.assertIn('Personal', app.credential_groups())
                    app.show_settings()
                    app.settings_navigation.choose('Text')
                    app.text_font_size_choice.value = '23'
                    app.preferences.reload()
                    self.assertNotIn('Personal.zip', app.preferences.path.read_text())
                    self.assertNotIn('Secret', app.preferences.path.read_text())
                    self.assertNotIn('correct', cache.index.read_text())
                    app.session_credential_packages = []
                    restored = CredentialPackages(vault, CacheClient())
                    self.assertEqual(len(restored.matching('Secret', 'a' * 64)), 1)
                    retained.return_value = restored
                    self.assertIn('Personal', app.credential_groups())
            finally:
                app.main_window.close()
                app.loop.close()
                LogisticsMobile.storage_root = None

    def test_unencrypted_zip_is_not_retained_as_session_credentials(self):
        with TemporaryDirectory() as directory:
            vault = SimpleNamespace(root=Path(directory), unlock=Mock())
            cache = CredentialPackages(vault, CacheClient())
            data = BytesIO()
            with ZipFile(data, 'w') as archive:
                archive.writestr('credentials.txt', '[Secret]\npassword=plaintext-sentinel')
            with self.assertRaisesRegex(ValueError, 'password-protected'):
                cache.remember(SimpleNamespace(name='Personal.zip', data=data.getvalue()), {'Secret': 'a' * 64})
            vault.unlock.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_retained_zip_reopens_after_restart_without_storing_password(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            vault = SimpleNamespace(root=root, unlock=lambda **kw: dict(key='fixture'))
            cache = CredentialPackages(vault, CacheClient())
            key = cache.remember(SimpleNamespace(name='Personal.zip', data=PACKAGE), {'Secret': 'a' * 64})
            self.assertNotIn(PACKAGE, cache.path(key).read_bytes())
            restored = CredentialPackages(vault, CacheClient())
            self.assertEqual(restored.matching('Secret', 'b' * 64), [])
            self.assertEqual(restored.matching('Secret')[0][0], key)
            with restored.open(key) as (name, stream):
                self.assertEqual(name, 'Personal.zip')
                self.assertEqual(stream.read(), PACKAGE)
            self.assertNotIn('password', restored.index.read_text())

    def test_legacy_saved_package_name_and_retained_unlock_route(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.show_cloud(present=False)
                app.cloud_client = CacheClient()
                app.loop.run_until_complete(app.restore_cloud())
                app.show_locations()
                self.assertIn('Personal', app.folder_credentials)
                self.assertEqual(app.folder_credential.value, 'All')
                vault = SimpleNamespace(root=app.private_root, unlock=lambda **kw: dict(key='fixture'))
                cache = CredentialPackages(vault, app.cloud_client)
                cache.remember(SimpleNamespace(name='Personal.zip', data=PACKAGE), {'Secret': 'a' * 64})
                app.cloud_remote.items = []
                app.cloud_client.loaded = False
                resumed = Mock()
                with patch.object(app, 'retained_packages', return_value=cache), \
                        patch('features.rclone.mobile.credentials_ui.CredentialWorkflow.choose_credential_storage',
                              new_callable=AsyncMock) as choose, \
                        patch.object(app.cloud_client, 'import_package', wraps=app.cloud_client.import_package) as load:
                    self.assertIn('Personal', app.credential_groups())
                    self.assertFalse(app.require_remote_credentials('Secret', identity='a' * 64, resume=resumed))
                    self.assertEqual(app.routes.screens['files'][-1][0], 'unlock-credential')
                    app.credential_unlock_password.value = 'wrong'
                    app.loop.run_until_complete(app.credential_unlock_button.on_press())
                    resumed.assert_not_called()
                    self.assertEqual(app.credential_unlock_password.value, '')
                    app.credential_unlock_password.value = 'correct'
                    app.loop.run_until_complete(app.credential_unlock_button.on_press())
                    resumed.assert_called_once_with()
                    choose.assert_not_awaited()
                    self.assertFalse(load.call_args.kwargs['remember'])
                    self.assertIn('Secret', [row.value for row in app.cloud_remote.items])
            finally:
                app.main_window.close()
                app.loop.close()
                LogisticsMobile.storage_root = None
