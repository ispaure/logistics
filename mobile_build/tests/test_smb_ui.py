"""SMB connection entry preserves multiple servers and clears password fields."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mobile.app import LogisticsMobile
from features.rclone.mobile.cloud import CloudClient


class SMBConnectionTests(unittest.TestCase):
    def test_multiple_servers_browse_and_failed_addition(self):
        class Client:
            package_name = 'Network shares'
            generation = 0
            def __init__(self): self.servers = {}; self.visits = []
            def add_smb(self, name, host, user, password, domain, port, *, remember):
                if name in self.servers: raise ValueError('Connection name already exists')
                self.servers[name] = (host, user, password, domain, port, remember)
                return list(self.servers)
            def crypt_remotes(self): return []
            def entries(self, remote, path):
                self.visits.append((remote, path))
                return [dict(path='Shared', directory=True, size=0)] if not path else []
            def cancel(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                client = app.cloud_client = Client()
                app.show_smb_connection()
                self.assertTrue(app.smb_remember.value)
                for name, host, username, password in [('Home Mac', '192.168.1.10', 'marc', 'mac password'),
                                                       ('NAS', '192.168.1.20', 'reader', 'nas password')]:
                    app.show_smb_connection()
                    app.smb_name.value, app.smb_host.value = name, host
                    app.smb_user.value, app.smb_password.value = username, password
                    app.loop.run_until_complete(app.connect_smb())
                    self.assertEqual(app.smb_password.value, '')
                    self.assertEqual(client.servers[name], (host, username, password, 'WORKGROUP', '445', True))
                    self.assertEqual(client.visits[-1], (name, ''))
                    self.assertEqual(app.cloud_open_remote, name)
                self.assertEqual([row.value for row in app.cloud_remote.items], ['Home Mac', 'NAS'])
                app.show_smb_connection()
                app.smb_password.value = 'replacement'
                app.loop.run_until_complete(app.connect_smb())
                self.assertIn('already exists', app.smb_status.text)
                self.assertEqual(app.smb_password.value, '')
                self.assertEqual(client.servers['NAS'][2], 'nas password')
                self.assertFalse(app.cloud_busy)
                self.assertTrue(app.smb_connect.enabled)
            finally:
                app.main_window.close()
                app.loop.close()

    def test_client_uses_vault_and_session_only_does_not_restore_or_write_label(self):
        from unittest.mock import Mock
        client = CloudClient.__new__(CloudClient)
        client.vault = Mock()
        client.vault_attached = True
        client.request = Mock(side_effect=[['Mac', 'NAS'], {'package_name':'Network shares'}])
        names = client.add_smb('NAS', 'nas.local', 'user', 'secret')
        self.assertEqual(names, ['Mac', 'NAS'])
        client.request.assert_any_call('add_smb', remote='NAS', host='nas.local', user='user',
            password='secret', domain='', port='445', session_only=False)
        client.vault.set_label.assert_called_once_with('Network shares')
        client.vault.reset_mock()
        client.request.reset_mock(side_effect=True)
        client.request.side_effect = [['Mac', 'NAS', 'Guest'], {'package_name':'Network shares'}]
        with patch.object(client, 'restore') as restore:
            client.add_smb('Guest', 'guest.local', 'guest', '', remember=False)
            restore.assert_not_called()
        self.assertTrue(client.vault_attached)
        client.vault.set_label.assert_not_called()
