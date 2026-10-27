"""Shared plans retain discovery, platform coverage and gate order."""
from pathlib import Path
import unittest

from Scripts.validation_plans import desktop_checks, inventory


class ValidationPlanTests(unittest.TestCase):
    def test_desktop_plan_preserves_existing_commands_and_budgets(self):
        posix = desktop_checks('Darwin', Path('reports'))
        windows = desktop_checks('Windows', Path('reports'))
        self.assertEqual([p[0] for p in posix], ['commonutils', 'logistics', 'compression-parity', 'manager-contracts'])
        self.assertEqual([p[2] for p in posix], [600, 900, 600, 600])
        self.assertEqual([row[:2] for row in windows[1:]], [row[:2] for row in posix])
        self.assertEqual([row[2] for row in windows[1:]], [1800,1800,600,600])
        self.assertEqual(windows[0], ('windows-native-ui', ['Python/tests/native_ui_smoke.py'], 60))
        self.assertIn('--isolate-modules', posix[0][1])
        self.assertIn('--isolate-modules', posix[1][1])

    def test_compression_retries_get_fresh_attempts_and_preserve_previous_evidence(self):
        import importlib.util
        from tempfile import TemporaryDirectory
        path = Path(__file__).parents[1] / 'parity_workspace.py'
        spec = importlib.util.spec_from_file_location('parity_workspace_fixture', path)
        helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            first = helper.comparison_workspace(root)
            (first / 'comparison.json').write_text('previous evidence')
            (first / 'before').mkdir()
            second = helper.comparison_workspace(root)
            self.assertNotEqual(first, second)
            self.assertEqual(first.parent, root)
            self.assertEqual(second.parent, root)
            self.assertFalse(any(second.iterdir()))
            self.assertEqual((first / 'comparison.json').read_text(), 'previous evidence')

    def test_inventory_matches_actual_recursive_test_discovery(self):
        root = Path(__file__).resolve().parents[3]
        rows = {r['name']: r for r in inventory(root)['suites']}
        for suite, owner in [('desktop', 'Python/tests'), ('mobile-host', 'mobile_build/tests')]:
            expected = sorted(str(p.relative_to(root)).replace('\\', '/') for p in (root / owner).rglob('test*.py'))
            self.assertEqual(rows[suite]['test_files'], expected)
            self.assertEqual(rows[suite]['file_count'], len(expected))
        self.assertEqual(rows['native-ios']['devices'], ['iphone', 'duo', 'ipad'])
        self.assertTrue(rows['native-ios']['required'])
        self.assertEqual(rows['native-ios']['case_ids'], rows['native-android']['case_ids'])
        self.assertIn('native_rotation_safe_areas', rows['native-ios']['case_ids'])
        self.assertGreater(len(rows['runtime']['case_ids']), 40)
        self.assertFalse(rows['investigations']['required'])

    def test_package_manager_preparation_is_bounded_and_does_not_ignore_errors(self):
        root = Path(__file__).resolve().parents[3]
        for workflow in ('mobile-runtime.yml',):
            lines = (root / '.github/workflows' / workflow).read_text().splitlines()
            apt = [line.strip() for line in lines if 'sudo apt-get' in line]
            self.assertEqual(len(apt), 2)
            self.assertTrue(all(line.startswith('timeout --kill-after=10s ') for line in apt))
            self.assertTrue(all('|| true' not in line for line in apt))

    def test_fedora_is_the_only_declared_linux_distribution(self):
        root = Path(__file__).resolve().parents[3]
        rows = {row['name']: row for row in inventory(root)['suites']}
        for name in ('shared-host', 'static', 'desktop', 'mobile-host', 'release-tooling', 'manager', 'bridge'):
            self.assertIn('fedora', rows[name]['platforms'])
            self.assertNotIn('ubuntu', rows[name]['platforms'])
        workflow = (root / '.github/workflows/archive-platform-checks.yml').read_text()
        desktop = workflow.split('  desktop:\n', 1)[1].split('  fedora43:\n', 1)[0]
        self.assertNotIn('ubuntu-latest', desktop)
        self.assertIn("inputs.target != 'linux'", desktop)
        self.assertIn("inputs.target == 'linux'", workflow.split('  fedora43:\n', 1)[1])
        fedora = (root / 'Python/tests/platform/fedora43.sh').read_text()
        self.assertIn('Python/tests/run_platform_checks.py --install', fedora)
        self.assertIn('unittest discover -s .github/scripts', fedora)
