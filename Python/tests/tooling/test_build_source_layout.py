"""Historical source keeps its own builder paths after the current tooling move."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from build_manager import Phase, Plan
from build_manager.profiles import load_profile
from logistics_build.build_project import LogisticsProject
from logistics_build.source_layout import adapt_plan


class BuildSourceLayoutTests(unittest.TestCase):
    def test_plan_binds_settings_and_records_the_historical_command_for_evidence(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = LogisticsProject(root)
            fingerprint = 'a' * 64
            snapshot = project.private / 'snapshots' / fingerprint
            scripts = snapshot / 'Scripts'
            scripts.mkdir(parents=True)
            (snapshot / '.manager-source.json').touch()
            for name in ('build_project', 'test_structure', 'manager_suites', 'test_evidence'):
                (scripts / (name + '.py')).touch()
            workspace = project.private / 'workspaces' / 'macos'
            settings = {'auth.github_reference': 'FIXTURE_GITHUB_TOKEN'}
            source = dict(fingerprint=fingerprint, logistics_commit='b' * 40, commonUtils_commit='c' * 40,
                          effective_settings=dict(values=settings, origins={}))
            phase = Phase('logistics', ('python', '-m', 'logistics_build.manager_suites', 'fixture'), str(snapshot),
                          environment={'LOGISTICS_MANAGER_ACCOUNT_DEFAULTS': 'fixture'})
            base = Plan('Logistics', 'Test', source, (phase,), str(workspace), resource_locks=('existing.lock',))
            with patch.object(project, '_make_plan', return_value=base), patch('logistics_build.build_retention.clean'), \
                    patch('mobile_build.deployment.manager_settings.defaults', return_value=settings), \
                    patch('logistics_build.release_test_evidence.reuse_disabled', return_value=False), \
                    patch('logistics_build.test_evidence.key_for', return_value='d' * 64):
                plan = project.make_plan('Test', 'macos', 'This Mac', revision='fixture')

            final = plan.phases[-1]
            recipe = json.loads(Path(final.reuse_probe[4]).read_text())
            self.assertEqual(final.argv[2], 'Scripts.manager_suites')
            self.assertEqual(tuple(recipe['argv']), final.argv)
            self.assertEqual(final.reuse_probe[2], 'Scripts.test_evidence')
            self.assertEqual(recipe['environment']['LOGISTICS_MANAGER_ACCOUNT_DEFAULTS'], '{}')
            profile = final.environment['LOGISTICS_MANAGER_PROFILE']
            self.assertEqual(recipe['environment']['LOGISTICS_MANAGER_PROFILE'], profile)
            self.assertEqual(load_profile(profile), settings)
            self.assertEqual(plan.secret_environment, (*base.secret_environment, 'FIXTURE_GITHUB_TOKEN'))
            self.assertEqual(plan.resource_locks, (*base.resource_locks, str(snapshot.with_suffix('.lock'))))
            self.assertEqual(plan.source, dict(source, destination='local macos workspace',
                                               plan_preparation_seconds=plan.source['plan_preparation_seconds']))
            self.assertEqual(final.environment['LOGISTICS_STORAGE_OWNER_ROOT'], str(project.root))

    def test_old_snapshot_runs_its_own_builder_without_restoring_current_aliases(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / 'Scripts'
            old.mkdir()
            for name in ('build_project', 'ios_backend', 'test_evidence'):
                (old / (name + '.py')).write_text('# historical fixture\n')
            phase = Phase('build', ('python', '-m', 'logistics_build.ios_backend', 'build'), str(root),
                effect='test', reuse_key='a' * 64,
                reuse_probe=('python', '-m', 'logistics_build.test_evidence', '--probe', 'recipe.json'))
            plan = Plan('Fixture', 'Build', {}, (phase,), str(root / 'work'))
            adapted = adapt_plan(plan)
            self.assertEqual(adapted.phases[0].argv[2], 'Scripts.ios_backend')
            self.assertEqual(adapted.phases[0].reuse_probe[2], 'Scripts.test_evidence')
            self.assertEqual(plan.phases[0].argv[2], 'logistics_build.ios_backend')
            current = root / 'logistics_build'
            current.mkdir()
            (current / 'build_project.py').write_text('# current fixture\n')
            self.assertEqual(adapt_plan(plan).phases, plan.phases)

    def test_missing_historical_operation_stops_instead_of_importing_current_source(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Scripts').mkdir()
            (root / 'Scripts/build_project.py').write_text('# historical fixture\n')
            plan = Plan('Fixture', 'Build', {},
                (Phase('build', ('python', '-m', 'logistics_build.new_operation'), str(root)),), str(root / 'work'))
            with self.assertRaisesRegex(ValueError, 'predates'):
                adapt_plan(plan)
