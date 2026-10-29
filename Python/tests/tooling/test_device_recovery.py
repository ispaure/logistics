"""Recovery verifies a retained app without changing a failed build history."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from build_manager import Phase, Plan
from commonUtils.runtime.streams import file_sha256
from logistics_build import device_recovery as recovery


class DeviceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.recipe = self.root / 'recipe.json'
        self.source = dict(fingerprint='captured')
        self.recipe.write_text(json.dumps(dict(platform='ios', source=self.source)))
        build = Phase('ios.devices.prepare-device-app', ('python', '-m', 'logistics_build.manager_devices',
            'prepare', '--recipe', str(self.recipe), '--sha256', file_sha256(self.recipe)), str(self.root))
        self.plan = Plan('Logistics', 'Device build', self.source, (build,
            Phase('ready', ('python', '-c', 'pass'), str(self.root)),
            Phase('install', ('python', '-c', 'pass'), str(self.root))), str(self.root / 'workspace'))
        self.report = dict(status='failed', phases=[dict(id=build.id, status='failed'),
            dict(id='ready', status='skipped'), dict(id='install', status='skipped')])
        self.load = patch.object(recovery, 'load_run', return_value=(self.plan, self.report))
        self.load.start()
        self.addCleanup(self.load.stop)
        self.check = patch.object(recovery, 'check_source')
        self.check.start()
        self.addCleanup(self.check.stop)

    def test_plan_binds_recovery_helper_and_keeps_original_source_and_failure(self):
        result = recovery.make_plan(self.root)
        self.assertEqual(result.source, self.source)
        self.assertNotEqual(result.identity, self.plan.identity)
        self.assertIn(file_sha256(Path(recovery.__file__)), result.phases[0].argv)
        self.assertEqual(result.phases[1:], self.plan.phases[1:])
        self.assertEqual(self.report['phases'][0]['status'], 'failed')

    def test_active_and_successful_runs_cannot_be_recovered(self):
        for status in ('running', 'passed', 'awaiting_review', 'unknown'):
            with self.subTest(status=status):
                self.report['status'] = status
                with self.assertRaisesRegex(ValueError, 'stopped'):
                    recovery.make_plan(self.root)

    def test_admitted_or_unknown_install_requires_reconciliation(self):
        for status in ('passed', 'unknown', 'cancelled', 'running'):
            with self.subTest(status=status):
                self.report['phases'][2]['status'] = status
                with self.assertRaisesRegex(ValueError, 'Reconcile'):
                    recovery.make_plan(self.root)

    def test_changed_recipe_is_rejected_before_source_or_artifact_use(self):
        self.recipe.write_text(self.recipe.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'recipe changed'):
            recovery.make_plan(self.root)

    def test_journey_metadata_does_not_replace_captured_inputs(self):
        self.plan.source['platform_plans'] = {}
        self.assertEqual(recovery.make_plan(self.root).source['fingerprint'], 'captured')

    def test_changed_helper_is_rejected_before_verification(self):
        with self.assertRaisesRegex(ValueError, 'helper changed'):
            recovery.verify(self.root, 'wrong')

    def test_different_source_cannot_replace_the_failed_build_source(self):
        self.plan = Plan('Logistics', 'Other source', {'fingerprint': 'other'}, self.plan.phases,
                         str(self.root / 'workspace'))
        self.load.stop()
        with patch.object(recovery, 'load_run', return_value=(self.plan, self.report)):
            with self.assertRaisesRegex(ValueError, 'exact captured'):
                recovery.make_plan(self.root)
