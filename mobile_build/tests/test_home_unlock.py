"""Home offers session unlocking without restoring credentials or listing remotes."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
import toga
from mobile.app import LogisticsMobile
from features.rclone.mobile.credential_packages import CredentialPackages
from test_credential_packages import CacheClient, PACKAGE


class HomeUnlockTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        LogisticsMobile.storage_root = root
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        # Backend names below select Home policy; this dummy host has no UIKit.
        self.external = patch('mobile.external_display.sync')
        self.external.start()
        self.addCleanup(self.external.stop)
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        self.app.show_cloud(present=False)
        client = self.app.cloud_client = CacheClient()
        client.loaded = False
        client.package_records = []
        client.restore = Mock(side_effect=AssertionError('Home must not restore credentials'))
        vault = SimpleNamespace(root=root / 'Retained', unlock=lambda **kw: dict(key='fixture'))
        vault.root.mkdir()
        self.cache = CredentialPackages(vault, client)
        self.keys = {name: self.cache.remember(SimpleNamespace(name=name, data=PACKAGE),
                     {'Secret': 'a' * 64}) for name in ('Legacy.zip', 'Personal.zip', 'Work.zip')}
        self.patch = patch.object(self.app, 'retained_packages', return_value=self.cache)
        self.retained = self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_candidates_require_disk_and_unloaded_package_and_filter_legacy(self):
        app = self.app
        for backend in ('toga_android.app', 'toga_iOS.app'):
            with self.subTest(backend=backend), patch.object(type(app._impl), '__module__', backend):
                app.show_legacy_session = False
                self.assertEqual([item['zip'] for _, item in app.home_unlock_candidates()],
                                 ['Personal.zip', 'Work.zip'])
                app.show_legacy_session = True
                self.assertEqual(len(app.home_unlock_candidates()), 3)
        app.cloud_client.package_records = [dict(package_name='Personal.zip', remotes=['Secret'])]
        self.cache.path(self.keys['Work.zip']).unlink()
        with patch.object(type(app._impl), '__module__', 'toga_iOS.app'):
            app.show_legacy_session = False
            self.assertEqual(app.home_unlock_candidates(), [])
            app.show_home()
            self.assertIsInstance(app.home_content.children[0], toga.Label)
            app.show_legacy_session = True
            self.assertEqual([item['zip'] for _, item in app.home_unlock_candidates()], ['Legacy.zip'])

    def test_home_selector_password_retry_and_return_home(self):
        app = self.app
        with patch.object(type(app._impl), '__module__', 'toga_iOS.app'):
            app.show_legacy_session = False
            app.show_home()
            header = app.home_content.children[0]
            self.assertEqual(header.children[0].text, 'Your workspace')
            unlock = header.children[1]
            self.assertEqual(unlock.control_icon, 'storage_crypt')
            self.assertEqual(unlock.accessible_name, 'Unlock credentials')
            self.assertEqual((unlock.style.width, unlock.style.height), (48, 48))
            self.assertEqual(unlock._impl._surface_roles, ('surface', 'text', False))
            header.children[1].on_press()
            self.assertEqual(app.native_host.state.destination, 'home')
            self.assertEqual(app.routes.screens['home'][-1][0], 'unlock-credential')
            selector = next(child for child in app.body.children[0].children if isinstance(child, toga.Selection))
            self.assertEqual([item.value for item in selector.items], ['Personal.zip', 'Work.zip'])
            app.credential_unlock_password.value = 'discard on selection'
            selector.value = 'Work.zip'
            self.assertEqual(app.credential_unlock_password.value, '')
            app.credential_unlock_password.value = 'wrong'
            app.loop.run_until_complete(app.credential_unlock_button.on_press())
            self.assertIn('Unlock failed', app.credential_unlock_status.text)
            self.assertEqual(app.credential_unlock_password.value, '')
            with patch.object(app.cloud_client, 'import_package', wraps=app.cloud_client.import_package) as imported:
                app.credential_unlock_password.value = 'correct'
                app.loop.run_until_complete(app.credential_unlock_button.on_press())
                self.assertEqual(imported.call_args.args[1:3], (self.keys['Work.zip'], 'correct'))
                self.assertEqual(imported.call_args.kwargs, dict(remember=False))
            self.assertEqual(app.credential_unlock_password.value, '')
            self.assertEqual(app.native_host.state.destination, 'home')
            self.assertFalse(app.routes.screens['home'])
            app.cloud_client.restore.assert_not_called()

    def test_unavailable_retention_hides_home_action(self):
        self.retained.side_effect = OSError('Unavailable')
        self.app.show_home()
        self.assertIsInstance(self.app.home_content.children[0], toga.Label)
