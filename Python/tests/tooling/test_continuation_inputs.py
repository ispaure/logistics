"""Source applicability must fail closed for application, shared and mode changes."""
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from logistics_build.continuation_inputs import assess, inventory, verify_current


class ContinuationInputsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '--quiet')
        self.write('Python/app.py', 'APP = 1')
        self.write('logistics_build/guest_manager.py', 'ORCHESTRATION = 1')
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
        self.write('logistics_build/guest_manager.py', 'ORCHESTRATION = 2')
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
        self.write('logistics_build/guest_manager.py', 'ORCHESTRATION = 2')
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


class NativeApplicabilityTests(unittest.TestCase):
    """Portable rejection contracts; real toolchain acceptance is separate."""
    def setUp(self):
        import hashlib
        import json
        from types import SimpleNamespace
        from unittest.mock import patch
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = dict(logistics_commit='a'*40, commonUtils_commit='b'*40, dirty=False)
        for name, text in (('mobile_build/native_tests/tests/logisticsmobile/__init__.py', "CASES = ['rotation']"),
                           ('Python/mobile/smoke.py', "EXPECTED_TESTS = ['document']")):
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        self.rows, phases = [], []
        self.data = {}
        for name in ('iphone', 'duo', 'ipad', 'ios-runtime'):
            runtime = name.endswith('runtime')
            data = dict(schema=1, success=True, target='ios', source=self.source,
                        suite='logistics-mobile-documents' if runtime else 'logistics-native-ui')
            if runtime:
                data.update(expected_tests=['document'], tests_run=1, failures=0, errors=0, skipped=0)
            else:
                data.update(cases=['rotation'], expected_cases=['rotation'])
            record = dict(report=data, owned_simulator_removed=True, model='selected-model', runtime='selected-runtime')
            step = 'ios.validation.'+name
            phases.append(SimpleNamespace(id=step, argv=('python', '--runtime', '--', 'python', '--model', 'selected-model',
                                                         '--runtime', 'selected-runtime')))
            path = self.root/(name+'.json')
            path.write_text(json.dumps(record))
            self.data[step] = record
            self.rows.append(dict(id=step, status='passed', artifacts=[dict(path=str(path),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())]))
        build = dict(key=dict(source=self.source, toolchain=dict(xcode='original', sdk='original',
                     briefcase='original')), app=str(self.root/'absent.app'), bundle_sha256='c'*64)
        path = self.root/'build.json'
        path.write_text(json.dumps(build))
        self.rows.append(dict(id='ios.validation.ios-build', status='passed', artifacts=[dict(
            path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())]))
        phases.append(SimpleNamespace(id='ios.validation.ios-build', argv=('python',), environment={}))
        plan = SimpleNamespace(identity='reviewed-plan', source=self.source, phases=phases)
        self.patches = [patch('build_manager.history.load_run', return_value=(plan, dict(phases=self.rows))),
                        patch('logistics_build.continuation_inputs.verify_current', return_value=dict(previous_commit='a'*40)),
                        patch('subprocess.check_output', return_value='changed toolchain')]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def check(self):
        from logistics_build.continuation_inputs import verify_native_applicability
        return verify_native_applicability(self.root, self.root, 'reviewed-plan', 'd'*40)

    def change(self, **values):
        import hashlib
        import json
        row = self.rows[0]
        data = self.data[row['id']]
        data.update(values)
        path = Path(row['artifacts'][0]['path'])
        path.write_text(json.dumps(data))
        row['artifacts'][0]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()

    def test_failed_original_native_row_is_not_accepted(self):
        self.rows[0]['status'] = 'failed'
        with self.assertRaisesRegex(ValueError, 'did not pass'):
            self.check()

    def test_missing_cleanup_or_partial_rotation_inventory_is_not_accepted(self):
        self.change(owned_simulator_removed=False)
        with self.assertRaisesRegex(ValueError, 'cleanup is unverified'):
            self.check()
        self.change(owned_simulator_removed=True, report=dict(self.data[self.rows[0]['id']]['report'], cases=[]))
        with self.assertRaisesRegex(ValueError, 'inventory or cleanup'):
            self.check()

    def test_different_native_source_is_not_accepted(self):
        data = dict(self.data[self.rows[0]['id']]['report'], source=dict(self.source, logistics_commit='e'*40))
        self.change(report=data)
        with self.assertRaisesRegex(ValueError, 'source, complete inventory'):
            self.check()

    def test_changed_toolchain_rejects_otherwise_complete_ios_inventories(self):
        with self.assertRaisesRegex(ValueError, 'toolchain changed: ios'):
            self.check()

    def test_other_simulator_cannot_stand_in_for_selected_target(self):
        self.change(model='different-model')
        with self.assertRaisesRegex(ValueError, 'simulator identity differs'):
            self.check()
