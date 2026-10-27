"""Source applicability must fail closed for application, shared and mode changes."""
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from Scripts.continuation_inputs import assess, inventory, verify_current


class ContinuationInputsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '--quiet')
        self.write('Python/app.py', 'APP = 1')
        self.write('Scripts/guest_manager.py', 'ORCHESTRATION = 1')
        self.write('build-manager-dependency.json', 'pin1')
        self.before = self.commit()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE, text=True).strip()

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def commit(self):
        self.git('add', '.')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--quiet', '-m', 'fixture')
        return self.git('rev-parse', 'HEAD')

    def test_only_explicit_orchestration_changes_match_without_authorizing_reuse(self):
        self.write('Scripts/guest_manager.py', 'ORCHESTRATION = 2')
        self.write('build-manager-dependency.json', 'pin2')
        self.write('docs/development/example.md', '# Documentation')
        report = assess(self.root, self.before, self.commit())
        self.assertTrue(report['application_inputs_equal'])
        self.assertFalse(report['authorizes_reuse'])
        self.assertNotEqual(report['previous_manager_pin'], report['current_manager_pin'])
        self.assertEqual(report['changed_application_paths'], [])
        self.assertIn('platform and toolchain identity', report['remaining_checks'])

    def test_application_harness_shared_and_unknown_script_changes_invalidate(self):
        for name in ('Python/app.py', 'mobile_build/native_tests/harness.py',
                     'Python/commonUtils/settings.py', 'Scripts/unknown.py'):
            with self.subTest(name=name):
                self.write(name, 'CHANGED = True')
                report = assess(self.root, self.before, self.commit())
                self.assertFalse(report['application_inputs_equal'])
                self.assertIn(name, report['changed_application_paths'])

    def test_mode_changes_and_inexact_revision_cannot_claim_equality(self):
        self.git('update-index', '--chmod=+x', 'Python/app.py')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--quiet', '-m', 'mode')
        self.assertFalse(assess(self.root, self.before, self.git('rev-parse', 'HEAD'))['application_inputs_equal'])
        for revision in ('HEAD', '--help', '0' * 39):
            with self.assertRaises(ValueError):
                inventory(self.root, revision)


    def test_desktop_fixture_changes_require_fresh_validation_without_changing_native_inputs(self):
        name='Python/tests/ide/test_ide_drag.py'
        self.write(name,'# changed fixture')
        report=assess(self.root,self.before,self.commit())
        self.assertTrue(report['application_inputs_equal'])
        self.assertEqual(report['changed_desktop_fixtures'],[name])
        self.assertIn('fresh validation for every changed desktop fixture',report['remaining_checks'])
        self.assertFalse(report['authorizes_reuse'])

    def test_current_equivalence_is_bound_to_clean_checkout_and_review(self):
        self.write('Scripts/guest_manager.py', 'ORCHESTRATION = 2')
        current = self.commit()
        report = verify_current(self.root, self.before, current)
        self.assertTrue(report['current_checkout_verified'])
        self.assertFalse(report['authorizes_reuse'])
        self.assertEqual(report, verify_current(self.root, self.before, current,
                                               expect_identity=report['identity']))
        with self.assertRaisesRegex(ValueError, 'review changed'):
            verify_current(self.root, self.before, current, expect_identity='0'*64)
        with self.assertRaisesRegex(ValueError, 'current checkout'):
            verify_current(self.root, self.before, self.before)
        self.write('Python/app.py', 'DIRTY = True')
        with self.assertRaisesRegex(ValueError, 'current checkout'):
            verify_current(self.root, self.before, current)

    def test_changed_committed_application_inputs_block_continuation(self):
        self.write('Python/app.py', 'APP = 2')
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            verify_current(self.root, self.before, self.commit())

    def test_untracked_source_cannot_be_certified(self):
        self.write('Python/untracked.py', 'APP = 2')
        with self.assertRaisesRegex(ValueError, 'current checkout'):
            verify_current(self.root, self.before, self.before)
