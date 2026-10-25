"""Project integration contracts; controlled providers never publish or upload."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from Scripts.build_project import LogisticsProject
from mobile_build.deployment import firebase_deploy, manager_settings, testflight_deploy, testflight_external


class ManagerAdapterTests(unittest.TestCase):
    def test_prepared_report_keeps_embedded_identity_after_profile_changes(self):
        with TemporaryDirectory() as directory:
            report = Path(directory) / 'prepared.json'
            original = dict(version='1.2.3', build=42, source={'commit': 'a'}, destination='Synthetic group')
            with patch.dict(os.environ, {'LOGISTICS_MANAGER_ARTIFACT_REPORT': str(report)}):
                manager_settings.record_prepared_artifact(original)
            self.assertEqual(json.loads(report.read_text()), original)

    def test_build_preview_does_not_reserve_and_explicit_values_cannot_repeat(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / 'private'
            private.mkdir()
            with patch.object(firebase_deploy, 'ROOT', root), patch.object(firebase_deploy, 'PRIVATE', private):
                preview = firebase_deploy.next_build()
                self.assertFalse((private / 'build.json').exists())
                selected = preview + 5
                self.assertEqual(firebase_deploy.reserve_build(str(selected)), selected)
                with self.assertRaises(ValueError):
                    firebase_deploy.reserve_build(str(selected))
            with patch.object(testflight_deploy, 'ROOT', root):
                preview = int(testflight_deploy.next_build(root))
                self.assertFalse((root / '.tools/build-manager/ios-build.json').exists())
                self.assertEqual(testflight_deploy.reserve_build(str(preview + 5)), str(preview + 5))
                with self.assertRaises(ValueError):
                    testflight_deploy.reserve_build(str(preview + 5))

    def test_authentication_uses_credential_reference_and_environment_precedence(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / 'synthetic.p8'
            key.touch()
            auth = root / 'credentials.json'
            auth.write_text(json.dumps(dict(key_path=str(key), key_id='ABCDEFGHIJ',
                issuer_id='00000000-0000-0000-0000-000000000001')))
            manager_settings.save_profile(root / 'profile.json', {'auth.testflight_reference': str(auth)},
                                          allowed={'auth.testflight_reference'})
            with patch.object(testflight_external, 'ROOT', root), patch.object(testflight_external, 'AUTH', root / '.testflight-auth.json'), \
                    patch.dict(os.environ, {'LOGISTICS_MANAGER_PROFILE': str(root / 'profile.json'), 'ASC_KEY_ID': '0123456789'}):
                value = testflight_external.credentials()
                self.assertEqual(value['key_id'], '0123456789')
                self.assertEqual(value['key_path'], str(key))
                key.unlink()
                with self.assertRaisesRegex(ValueError, 'missing'):
                    testflight_external.credentials()

    def test_github_plan_separates_published_ref_and_expected_commit(self):
        root = Path(__file__).resolve().parents[3]
        project = LogisticsProject(root)
        source = dict(dirty=False, logistics_commit='a' * 40)
        plan = project.github_plan('Test', 'ios', source, root / 'test-results/fixture', {}, 'alpha', '')
        self.assertEqual(len(plan.phases), 2)
        for phase in plan.phases:
            self.assertEqual(phase.argv[phase.argv.index('--ref') + 1], 'alpha')
            self.assertEqual(phase.argv[phase.argv.index('--commit') + 1], 'a' * 40)
        self.assertEqual(plan.effect, 'publish')
        with self.assertRaises(ValueError):
            project.github_plan('Test', 'ios', dict(source, dirty=True), root, {}, 'working-tree', '')
