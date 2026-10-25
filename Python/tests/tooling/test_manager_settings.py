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

    def test_tracked_version_edit_is_explicit_and_preserves_bundle_identity(self):
        settings.set_app_version(self.root, '0.2.3')
        self.assertEqual(settings.app_version(self.root), '0.2.3')
        self.assertIn('bundle = "io.github.ispaure"', (self.root / 'pyproject.toml').read_text())
        with self.assertRaises(ValueError):
            settings.set_app_version(self.root, 'execute something')
