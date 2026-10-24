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
