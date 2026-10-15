"""ZIP retention, saved-package migration and password-only session unlock."""
import base64
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.credential_packages import CredentialPackages


class CacheClient:
    generation = 0
    package_name = 'Personal.zip'
    loaded = True
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
    def import_package(self, access, reference, password, **kwargs):
        with access.open(reference) as (name, stream):
            assert stream.read() == b'synthetic ZIP bytes'
        if password != 'correct': raise ValueError('Incorrect ZIP password')
        self.generation += 1
        self.loaded = True
        return ['Secret']


class CredentialPackageTests(unittest.TestCase):
    def test_retained_zip_reopens_after_restart_without_storing_password(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            vault = SimpleNamespace(root=root, unlock=lambda **kw: dict(key='fixture'))
            cache = CredentialPackages(vault, CacheClient())
            key = cache.remember(SimpleNamespace(name='Personal.zip', data=b'synthetic ZIP bytes'), {'Secret': 'a' * 64})
            self.assertNotIn(b'synthetic ZIP bytes', cache.path(key).read_bytes())
            restored = CredentialPackages(vault, CacheClient())
            self.assertEqual(restored.matching('Secret', 'b' * 64), [])
            self.assertEqual(restored.matching('Secret')[0][0], key)
            with restored.open(key) as (name, stream):
                self.assertEqual(name, 'Personal.zip')
                self.assertEqual(stream.read(), b'synthetic ZIP bytes')
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
                cache.remember(SimpleNamespace(name='Personal.zip', data=b'synthetic ZIP bytes'), {'Secret': 'a' * 64})
                app.cloud_remote.items = []
                app.cloud_client.loaded = False
                resumed = Mock()
                with patch.object(app, 'retained_packages', return_value=cache):
                    self.assertFalse(app.require_remote_credentials('Secret', identity='a' * 64, resume=resumed))
                    self.assertEqual(app.routes.screens['files'][-1][0], 'unlock-credential')
                    app.credential_unlock_password.value = 'wrong'
                    app.loop.run_until_complete(app.credential_unlock_button.on_press())
                    resumed.assert_not_called()
                    self.assertEqual(app.credential_unlock_password.value, '')
                    app.credential_unlock_password.value = 'correct'
                    app.loop.run_until_complete(app.credential_unlock_button.on_press())
                    resumed.assert_called_once_with()
                    self.assertIn('Secret', [row.value for row in app.cloud_remote.items])
            finally:
                app.main_window.close()
                app.loop.close()
                LogisticsMobile.storage_root = None
