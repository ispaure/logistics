"""Mixed saved/session package metadata drives both platforms' shared Workspaces."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
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
        self.assertIn('Personal.zip (saved)', app.loaded_package_label())
        self.assertIn('Legacy.zip (session only)', app.loaded_package_label())

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
