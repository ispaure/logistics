"""Project settings keep identities guarded and providers consistent with the UI."""
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mobile_build.deployment import manager_settings as settings


class ManagerSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source = Path(__file__).resolve().parents[3] / 'mobile_build'
        for name in ('testflight-distribution.json', 'firebase-distribution.json', 'pyproject.toml'):
            shutil.copyfile(source / name, self.root / name)

    def test_retired_ubuntu_settings_do_not_block_fedora_and_are_removed_on_save(self):
        path = settings.profile_path(self.root)
        legacy = {'vm.linux': 'Retired Ubuntu', 'vm.linux_scope': 'both',
                  'vm.fedora': 'Synthetic Fedora', 'vm.fedora_mode': 'container-on-ubuntu',
                  'vm.fedora_container_host': 'Authorized container host'}
        settings.save_profile(path, legacy, allowed=legacy)
        before = path.read_bytes()
        values, _ = settings.settings(self.root, overrides={'vm.linux_scope': 'ubuntu'})
        self.assertNotIn('vm.linux', values)
        self.assertNotIn('vm.linux_scope', values)
        self.assertEqual(values['vm.fedora'], 'Synthetic Fedora')
        self.assertEqual(values['vm.fedora_container_host'], 'Authorized container host')
        self.assertEqual(path.read_bytes(), before)
        settings.save(self.root, {'vm.fedora': 'Replacement Fedora'})
        saved = settings.load_profile(path)
        self.assertNotIn('vm.linux', saved)
        self.assertNotIn('vm.linux_scope', saved)
        self.assertEqual(saved['vm.fedora'], 'Replacement Fedora')
        with self.assertRaisesRegex(ValueError, 'Unknown settings field'):
            settings.settings(self.root, overrides={'vm.unknown': 'invalid'})

    def test_settings_round_trip_and_environment_source_does_not_change_defaults(self):
        before = (self.root / 'testflight-distribution.json').read_text()
        settings.save(self.root, {'testflight.external_group': 'Synthetic group', 'testflight.poll_interval_seconds': '12'})
        with patch.dict('os.environ', {'LOGISTICS_TESTFLIGHT_GROUP': 'Environment group'}):
            values, sources = settings.settings(self.root)
            self.assertEqual(values['testflight.external_group'], 'Environment group')
            self.assertEqual(sources['testflight.external_group'], 'environment')
        self.assertEqual(values['testflight.poll_interval_seconds'], 12)
        self.assertEqual((self.root / 'testflight-distribution.json').read_text(), before)

    def test_identity_invalid_group_and_invalid_waits_do_not_write_profile(self):
        for change in ({'testflight.app_id': '123'}, {'testflight.external_group': ''},
                       {'testflight.poll_interval_seconds': '0'}, {'firebase.app_id': 'bad'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                settings.save(self.root, change)
        self.assertFalse(settings.profile_path(self.root).exists())

    def test_existing_provider_uses_same_profile_destination_without_upload(self):
        settings.save(self.root, {'firebase.group': 'Synthetic testers'})
        original = json.loads((self.root / 'firebase-distribution.json').read_text())
        self.assertEqual(settings.distribution(self.root, 'firebase', original)['group'], 'Synthetic testers')

    def test_vm_only_profile_preserves_callers_loaded_provider_defaults(self):
        settings.save(self.root, {'vm.fedora': 'Synthetic Fedora'})
        original = dict(group='Provider file group', bundle_id='fixture.bundle')
        self.assertEqual(settings.distribution(self.root, 'firebase', original), original)
        path = settings.profile_path(self.root)
        profile = json.loads(path.read_text())
        profile['values']['firebase.bundle_id'] = 'other.bundle'
        path.write_text(json.dumps(profile))
        with self.assertRaisesRegex(ValueError, 'identity'):
            settings.distribution(self.root, 'firebase', original)

    def test_tracked_version_edit_is_explicit_and_preserves_bundle_identity(self):
        settings.set_app_version(self.root, '0.2.3')
        self.assertEqual(settings.app_version(self.root), '0.2.3')
        self.assertIn('bundle = "io.github.ispaure"', (self.root / 'pyproject.toml').read_text())
        with self.assertRaises(ValueError):
            settings.set_app_version(self.root, 'execute something')

    def test_historical_version_comes_from_selected_commit_not_live_checkout(self):
        import os
        import subprocess
        with TemporaryDirectory(prefix='version-review-') as directory:
            root=Path(directory);mobile=root/'mobile_build';mobile.mkdir()
            config=mobile/'pyproject.toml';config.write_text('[tool.briefcase]\nversion = "1.2.3"\n')
            environment=dict(os.environ,GIT_AUTHOR_NAME='Fixture',GIT_AUTHOR_EMAIL='fixture@example.invalid',
                GIT_COMMITTER_NAME='Fixture',GIT_COMMITTER_EMAIL='fixture@example.invalid')
            def git(*arguments):
                return subprocess.check_output(['git','-C',str(root),*arguments],env=environment,text=True).strip()
            git('init','-q');git('add','.');git('commit','-qm','version fixture');commit=git('rev-parse','HEAD')
            config.write_text('[tool.briefcase]\nversion = "9.9.9"\n')
            self.assertEqual(settings.app_version(mobile), '9.9.9')
            self.assertEqual(settings.app_version(mobile,revision=commit),'1.2.3')

    def test_settings_identify_unused_shared_folder_fields_and_clearable_avd(self):
        from Scripts.build_project import LogisticsProject
        project=LogisticsProject(self.root.parent)
        project.mobile=self.root
        rows=project.settings_view()
        self.assertTrue(rows['vm.shared_host']['read_only'])
        self.assertTrue(rows['vm.shared_guest']['read_only'])
        self.assertIn('not used',rows['vm.shared_host']['origin'])
        self.assertFalse(rows['android.avd']['read_only'])
        self.assertIn('leave empty',rows['android.avd']['label'])
