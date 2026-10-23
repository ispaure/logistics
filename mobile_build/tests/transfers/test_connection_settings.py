"""Connection settings preserve credentials while separating setup and diagnostics."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import toga
from mobile.app import LogisticsMobile


class ConnectionSettingsTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        LogisticsMobile.storage_root = Path(directory.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        self.app.cloud_client = SimpleNamespace(package_name='', generation=0, package_records=(),
                                                add_smb=Mock(), cancel=lambda: None)

    @staticmethod
    def descendants(widget):
        yield widget
        for child in getattr(widget, 'children', ()):
            yield from ConnectionSettingsTests.descendants(child)

    def test_settings_routes_and_collapsed_controls_keep_their_values(self):
        app = self.app
        app.show_settings()
        workspace = app.settings_navigation.sections['Workspaces']
        buttons = {getattr(w, '_settings_source_text', w.text): w
                   for w in self.descendants(workspace) if isinstance(w, toga.Button)}
        buttons['rclone connections…'].on_press()
        self.assertEqual(app.routes.screens['settings'][-1][0], 'connections')
        self.assertNotIn(app.cloud_password, set(self.descendants(app.cloud_connections_view.content)))
        self.assertNotIn(app.cloud_probe, set(self.descendants(app.cloud_connections_view.content)))
        app.cloud_settings_toggle.on_press()
        self.assertIn(app.cloud_probe, set(self.descendants(app.cloud_connections_view.content)))
        app.cloud_settings_toggle.on_press()
        self.assertNotIn(app.cloud_probe, set(self.descendants(app.cloud_connections_view.content)))
        app.show_cloud_import()
        self.assertEqual(app.routes.screens['settings'][-1][0], 'import-credentials')
        self.assertIn(app.cloud_password, set(self.descendants(app.cloud_import_view.content)))
        buttons['SMB shares…'].on_press()
        self.assertEqual(app.native_host.state.destination, 'settings')
        self.assertEqual(app.routes.screens['settings'][-1][0], 'smb-connection')
        self.assertNotIn(app.smb_port, set(self.descendants(app.smb_view.content)))
        app.smb_advanced_toggle.on_press()
        app.smb_port.value = '1445'
        app.smb_advanced_toggle.on_press()
        app.smb_advanced_toggle.on_press()
        self.assertEqual(app.smb_port.value, '1445')
        self.assertIn(app.smb_port, set(self.descendants(app.smb_view.content)))

    def test_guest_access_clears_password_and_omits_account_credentials(self):
        app = self.app
        app.show_smb_connection()
        app.smb_name.value, app.smb_host.value = 'Guest NAS', 'nas.local'
        app.smb_user.value, app.smb_password.value = 'private-user', 'private-password'
        app.smb_guest.value = True
        self.assertEqual(app.smb_password.value, '')
        self.assertIsNone(app.smb_account.parent)
        app.smb_remember.value = False
        with patch.object(app.cloud_client, 'add_smb', side_effect=ValueError('fixture unavailable')) as add:
            app.loop.run_until_complete(app.connect_smb())
        add.assert_called_once_with('Guest NAS', 'nas.local', 'guest', '', 'WORKGROUP', '445', remember=False)
        self.assertIn('fixture unavailable', ' '.join(app.smb_status.text.split()))
        self.assertEqual(app.routes.screens['settings'][-1][0], 'smb-connection')
        app.smb_guest.value = False
        self.assertIs(app.smb_account.parent, app.smb_signin)
        self.assertEqual(app.smb_user.value, 'private-user')
        self.assertEqual(app.smb_password.value, '')

    def test_narrow_labels_and_busy_controls_follow_the_form(self):
        app = self.app
        app.show_smb_connection()
        with patch.object(app.adaptive, 'content_width', return_value=320):
            app.resize_workspace()
            labels = [w for w in self.descendants(app.smb_view.content) if isinstance(w, toga.Label)]
            self.assertTrue(any('\n' in w.text for w in labels))
        app.set_cloud_busy(True)
        self.assertFalse(app.smb_guest.enabled)
        self.assertFalse(app.smb_connect.enabled)
        self.assertFalse(app.cloud_import_entry.enabled)
        app.set_cloud_busy(False)
        self.assertTrue(app.smb_guest.enabled)
        self.assertTrue(app.smb_connect.enabled)
