"""Shared plans retain discovery, platform coverage and gate order."""
from pathlib import Path
import unittest

from Scripts.validation_plans import desktop_checks, inventory


class ValidationPlanTests(unittest.TestCase):
    def test_desktop_plan_preserves_existing_commands_and_budgets(self):
        posix = desktop_checks('Darwin', Path('reports'))
        windows = desktop_checks('Windows', Path('reports'))
        self.assertEqual([p[0] for p in posix], ['commonutils', 'logistics', 'compression-parity', 'manager-contracts'])
        self.assertEqual([p[2] for p in posix], [600, 900, 600, 120])
        self.assertEqual([row[:2] for row in windows[1:]], [row[:2] for row in posix])
        self.assertEqual([row[2] for row in windows[1:]], [1800,1800,600,120])
        self.assertEqual(windows[0], ('windows-native-ui', ['Python/tests/native_ui_smoke.py'], 60))
        self.assertIn('--isolate-modules', posix[0][1])
        self.assertIn('--isolate-modules', posix[1][1])

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
        for workflow in ('archive-platform-checks.yml', 'mobile-runtime.yml'):
            lines = (root / '.github/workflows' / workflow).read_text().splitlines()
            apt = [line.strip() for line in lines if 'sudo apt-get' in line]
            self.assertEqual(len(apt), 2)
            self.assertTrue(all(line.startswith('timeout --kill-after=10s ') for line in apt))
            self.assertTrue(all('|| true' not in line for line in apt))
