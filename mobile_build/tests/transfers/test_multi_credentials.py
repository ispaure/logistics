"""Mixed saved/session package metadata drives both platforms' shared Workspaces."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from features.rclone.mobile.credential_state import NativeCredentialState
from mobile.app import LogisticsMobile


class MultiCredentialUITests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        LogisticsMobile.storage_root = Path(self.directory.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        records = [dict(package_name='Personal.zip', saved=True, remotes=['Main'], aliases={'Main':'Main'}),
                   dict(package_name='Legacy.zip', saved=False, remotes=['Legacy-Books'], aliases={'Legacy-Books':'Legacy-Books'})]
        self.client = SimpleNamespace(generation=1, package_name='Legacy.zip', package_records=records, cancel=lambda:None)
        self.app.cloud_client = self.client
        self.app.show_cloud(present=False)

    def test_associations_keep_modes_separate_and_both_groups_visible(self):
        app = self.app
        app.remember_loaded_packages('Legacy.zip', ['Main', 'Legacy-Books'], session_only=True)
        saved = json.loads(app.preferences.values['remote_packages'])
        self.assertEqual(saved, [dict(zip='Personal.zip', remotes=['Main'], session_only=False)])
        self.assertEqual(app.session_credential_packages, [dict(zip='Legacy.zip', remotes=['Legacy-Books'], session_only=True)])
        app.set_loaded_remote_names(['Main', 'Legacy-Books'])
        app.show_locations()
        for backend in ('toga_android.app', 'toga_iOS.app'):
            with self.subTest(backend=backend), patch.object(type(app._impl), '__module__', backend):
                app.change_show_legacy(SimpleNamespace(value=True))
                self.assertEqual(app.credential_groups(), {'All':None, 'Personal':{'Main'}, 'Legacy':{'Legacy-Books'}})
                app.change_show_legacy(SimpleNamespace(value=False))
                self.assertEqual(app.credential_groups(), {'All':None, 'Personal':{'Main'}})
        self.assertIn('Personal.zip (Persistent save)', app.loaded_package_label())
        self.assertIn('Legacy.zip (Session-Only)', app.loaded_package_label())

    def test_saving_another_package_does_not_forget_session_associations(self):
        app = self.app
        app.remember_credential_association('Legacy.zip', ['Legacy-Books'], session_only=True)
        app.remember_credential_association('Work.zip', ['Work'], session_only=True)
        app.remember_credential_association('Personal.zip', ['Main'], session_only=False)
        self.assertEqual({item['zip'] for item in app.session_credential_packages}, {'Legacy.zip','Work.zip'})
        self.assertTrue(all(not item['session_only'] for item in json.loads(app.preferences.values['remote_packages'])))

    def test_aliases_preserve_backing_remote_exclusions(self):
        self.client.package_records = [dict(package_name='Legacy.zip', saved=False,
            remotes=['Dropbox @ Legacy abc', 'Books @ Legacy abc'],
            aliases={'Dropbox':'Dropbox @ Legacy abc','Books':'Books @ Legacy abc'})]
        self.assertEqual(self.app.visible_remote_names(self.client.package_records[0]['remotes']), ['Books @ Legacy abc'])

    def test_loaded_accounts_use_published_identities_after_second_package(self):
        app = self.app
        state = NativeCredentialState()
        state.package_records = (
            dict(package_name='Personal.zip', saved=True, remotes=['Main', 'Dropbox'],
                 aliases={'Main': 'Main', 'Dropbox': 'Dropbox'},
                 identities={'Main': 'a' * 64, 'Dropbox': 'c' * 64}),
            dict(package_name='Session.zip', saved=False, remotes=['SessionRemote', 'Dropbox @ Session abc'],
                 aliases={'SessionRemote': 'SessionRemote', 'Dropbox': 'Dropbox @ Session abc'},
                 identities={'SessionRemote': 'b' * 64, 'Dropbox @ Session abc': 'd' * 64}))
        self.client.package_records = state.package_records
        self.client.resolve_remote = state.resolve_remote
        self.client.connection_identity = Mock(side_effect=OSError('Bridge unavailable'))
        app.set_loaded_remote_names(['Main', 'SessionRemote'])
        with patch.object(app, 'show_cloud_connections') as setup:
            for remote, identity in [('Main', 'a' * 64), ('SessionRemote', 'b' * 64), ('Dropbox', 'd' * 64)]:
                with self.subTest(identity=identity):
                    self.assertTrue(app.require_remote_credentials(remote, identity=identity))
                    self.assertTrue(app.loop.run_until_complete(
                        app.require_remote_credentials_async(remote, identity=identity)))
            app.show_locations()
            entry = next(copy for folder in app.folder_choices().values()
                         for copy in folder.get('copies', ()) if copy.get('remote') == 'Main')
            async def browse(*, preserve_path):
                app.cloud_open_remote = app.cloud_remote.value
                app.cloud_path = app.cloud_location.value
            with patch.object(app, 'browse_cloud', side_effect=browse):
                self.assertTrue(app.loop.run_until_complete(app.open_picker_folder(entry)))
            setup.assert_not_called()
        self.client.connection_identity.assert_not_called()

    def test_loaded_name_does_not_admit_a_different_account(self):
        self.client.package_records[0]['identities'] = {'Main': 'a' * 64}
        self.client.connection_identity = Mock(return_value='a' * 64)
        with patch.object(self.app, 'retained_packages', return_value=None), \
                patch.object(self.app, 'show_cloud_connections') as setup:
            self.assertFalse(self.app.require_remote_credentials('Main', identity='b' * 64))
            self.assertFalse(self.app.loop.run_until_complete(
                self.app.require_remote_credentials_async('Main', identity='b' * 64)))
            self.assertEqual(setup.call_count, 2)


class PackagePrivacyTests(unittest.TestCase):
    def test_remote_gate_uses_owner_and_saved_accounts_do_not_inherit_another_password(self):
        from features.rclone.mobile.session_privacy import ResumePassword, remote_privacy_gate
        state = NativeCredentialState()
        first, second = ResumePassword('first'), ResumePassword('second')
        state.package_privacy = {'First.zip': first, 'Second.zip': second}
        state.session_privacy = first
        state.package_records = (
            dict(package_name='First.zip', saved=False, remotes=['First'], aliases={'First': 'First'},
                 identities={'First': 'a' * 64}, crypt_identities={'First': 'c' * 64}),
            dict(package_name='Second.zip', saved=False, remotes=['Second'], aliases={'Second': 'Second'},
                 identities={'Second': 'b' * 64}, crypt_identities={'Second': 'd' * 64}),
            dict(package_name='Saved.zip', saved=True, remotes=['Saved'], aliases={'Saved': 'Saved'},
                 identities={'Saved': 'e' * 64}, crypt_identities={'Saved': 'f' * 64}))
        client = SimpleNamespace(credential_state=state)
        self.assertIs(remote_privacy_gate(client, 'Second', 'b' * 64), second)
        self.assertIs(remote_privacy_gate(client, 'Second', 'd' * 64, cipher=True), second)
        self.assertIsNone(remote_privacy_gate(client, 'Saved', 'e' * 64))
        with self.assertRaises(ValueError):
            remote_privacy_gate(client, 'Second', 'a' * 64)
        del state.package_privacy['Second.zip']
        with self.assertRaises(ValueError):
            remote_privacy_gate(client, 'Second', 'b' * 64)

    def test_remote_provider_keeps_owning_gate_after_other_packages_change(self):
        from features.rclone.mobile.remote_resources import NativeRemoteResources
        from features.rclone.remote_access import NativeRemoteLocation
        from features.rclone.mobile.remote_readers import RemoteReaders
        from features.rclone.mobile.session_privacy import ResumePassword
        state = NativeCredentialState()
        first, second = ResumePassword('first'), ResumePassword('second')
        state.session_privacy = first
        state.package_privacy = {'Second.zip': second}
        state.package_records = (dict(package_name='Second.zip', saved=False, remotes=['Second'],
            aliases={'Second': 'Second'}, identities={'Second': 'b' * 64}),)
        client = SimpleNamespace(generation=1, credential_state=state,
                                 connection_identity=lambda remote: 'b' * 64)
        provider = NativeRemoteResources(client, NativeRemoteLocation('Second'))
        self.assertIs(provider.privacy_gate, second)
        readers = RemoteReaders(client, 'Second', resource=provider)
        self.assertIs(readers.privacy_gate, second)
        state.package_privacy = {}
        state.session_privacy = None
        self.assertIs(provider.privacy_gate, second)
        self.assertIs(readers.privacy_gate, second)
        provider.close()

    def test_localcrypt_gate_selection_uses_each_copy_mapping(self):
        from features.rclone.mobile.session_privacy import ResumePassword
        from features.rclone.localcrypt.mobile.content import CryptContentProvider
        from features.rclone.localcrypt.mobile.copies import LocalCryptCopies
        state = NativeCredentialState()
        first, second = ResumePassword('first'), ResumePassword('second')
        state.session_privacy = first
        state.package_privacy = {'Second.zip': second}
        state.package_records = (dict(package_name='Second.zip', saved=False, remotes=['Second'],
            aliases={'Second': 'Second'}, crypt_identities={'Second': 'd' * 64}),)
        client = SimpleNamespace(credential_state=state)
        provider = CryptContentProvider()
        provider.client, provider.remote, provider.identity = client, 'Second', 'd' * 64
        self.assertIs(provider.privacy_gate, second)
        copies = object.__new__(LocalCryptCopies)
        copies.client = client
        copies.record = Mock(return_value=dict(remote='Second', identity='d' * 64))
        self.assertIs(copies.privacy_gate_for('copy-key'), second)
        copies.record.assert_called_once_with('copy-key')
