"""Historical source keeps its own builder paths after the current tooling move."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from build_manager import Phase, Plan
from logistics_build.source_layout import adapt_plan


class BuildSourceLayoutTests(unittest.TestCase):
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
