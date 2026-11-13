"""Tracked test input scopes invalidate affected evidence, not unrelated edits."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from dataclasses import replace
import hashlib
import os
from unittest.mock import patch
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from build_manager import Phase
from commonUtils.runtime.streams import CHUNK_SIZE
from logistics_build.test_evidence import inputs, key_for


class InputIdentityTests(unittest.TestCase):
    def test_streamed_inputs_match_legacy_composite_digest(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            sources = {
                'z.bin': b'\xff' * CHUNK_SIZE + b'\x00' * CHUNK_SIZE + b'tail',
                'a.bin': b'',
            }
            for name, content in sources.items():
                (root / name).write_bytes(content)
            subprocess.run(['git', '-C', str(root), 'add', '--', *sources], check=True)
            expected = hashlib.sha256()
            for name in sorted(sources):
                expected.update(name.encode() + b'\0')
                expected.update(hashlib.sha256(sources[name]).digest())

            with patch.object(Path, 'read_bytes', side_effect=AssertionError('Use bounded reads')):
                self.assertEqual(inputs(root, list(sources)), expected.hexdigest())

    def test_changed_runtime_new_tests_toolchain_and_command_invalidate_but_output_paths_do_not(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            source = root / 'Python/commonUtils/runtime.py'
            source.parent.mkdir(parents=True)
            source.write_text('value = 1\n')
            subprocess.run(['git', '-C', str(root), 'add', 'Python'], check=True)
            phase = Phase('commonutils', ('python', 'Python/tests/run_regressions.py', 'Python/commonUtils/tests',
                '--junit', '/run-one/result.xml'), str(root), effect='test')
            runtime = dict(python='same', os='same')
            original = key_for(phase, runtime=runtime)
            mac = replace(phase, environment={'BUILD_MANAGER_TEST_PLATFORM': 'macos', 'BUILD_MANAGER_TEST_WORKERS': '4'})
            ios = replace(mac, environment=dict(mac.environment, BUILD_MANAGER_TEST_PLATFORM='ios', BUILD_MANAGER_RESERVED_TEST_WORKERS='4'))
            self.assertEqual(key_for(mac, runtime=runtime), key_for(ios, runtime=runtime))
            self.assertNotEqual(key_for(mac, runtime=runtime), key_for(replace(mac,
                environment=dict(mac.environment, BUILD_MANAGER_TEST_WORKERS='8')), runtime=runtime))
            partitioned = replace(phase, argv=(*phase.argv, '--stage', 'regression', '--stage', 'extended'))
            remaining_key = key_for(partitioned, runtime=runtime)
            self.assertTrue(remaining_key)
            self.assertNotEqual(remaining_key, original)
            smoke = replace(phase, id='commonutils.smoke', argv=(*phase.argv, '--profile', 'smoke', '--mode', 'fast'))
            self.assertEqual(key_for(smoke, runtime=runtime), '')
            other = root / 'unrelated.txt'
            other.write_text('does not affect shared library')
            self.assertEqual(key_for(phase, runtime=runtime), original)
            moved = replace(phase, argv=(*phase.argv[:-1], '/run-two/result.xml'))
            self.assertEqual(key_for(moved, runtime=runtime), original)
            self.assertNotEqual(key_for(phase, runtime=dict(runtime, os='different')), original)
            source.write_text('value = 2\n')
            self.assertNotEqual(key_for(phase, runtime=runtime), original)
            source.write_text('value = 1\n')
            (source.parent / 'test_new.py').write_text('new test\n')
            self.assertNotEqual(key_for(phase, runtime=runtime), original)

    def test_tracked_removal_runs_fresh_instead_of_reusing_or_blocking_planning(self):
        import sys
        from build_manager import Plan
        from logistics_build.test_evidence import with_reuse
        with TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            source = root / 'Python/commonUtils/runtime.py'
            source.parent.mkdir(parents=True)
            source.write_text('value = 1\n')
            subprocess.run(['git', '-C', str(root), 'add', 'Python'], check=True)
            source.unlink()
            phase = Phase('commonutils', (sys.executable, '-c', 'pass'), str(root), effect='test')
            self.assertEqual(key_for(phase, runtime={}), '')
            with patch.dict(os.environ, {'LOGISTICS_REUSE_TEST_RESULTS': 'on', 'GITHUB_REF': ''}):
                plan = with_reuse(Plan('Fixture', 'removed source', {}, (phase,), str(root/'workspace')))
            self.assertEqual(plan.phases[0].argv, phase.argv)
            self.assertEqual(plan.phases[0].reuse_key, '')
            self.assertEqual(plan.phases[0].reuse_probe, ())

    def test_native_or_external_phases_never_receive_portable_test_keys(self):
        phase = Phase('android-native', ('python', 'test.py'), '.', effect='test')
        self.assertEqual(key_for(phase), '')
        self.assertEqual(key_for(replace(phase, id='commonutils', effect='deploy')), '')

    @patch.dict(os.environ, {'LOGISTICS_REUSE_TEST_RESULTS': 'on', 'GITHUB_REF': ''})
    def test_real_execution_probe_reuses_same_inputs_then_runs_changed_source(self):
        import json
        import os
        import sys
        from build_manager import Plan, Executor
        from logistics_build.test_evidence import with_reuse
        from dataclasses import replace
        actual = Path(__file__).resolve().parents[3]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            source = root / 'Python/commonUtils/runtime.py'
            source.parent.mkdir(parents=True)
            source.write_text('value = 1\n')
            subprocess.run(['git', '-C', str(root), 'add', 'Python'], check=True)
            artifact, count = root / 'report.xml', root / 'calls'
            code = ("from pathlib import Path;"
                    f"p=Path({str(count)!r});p.write_text(p.read_text()+'x' if p.exists() else 'x');"
                    f"Path({str(artifact)!r}).write_text('<testsuite><testcase name=\"passed\"/></testsuite>')")
            phase = Phase('commonutils', (sys.executable, '-c', code), str(root), effect='test',
                environment={'PYTHONPATH':os.pathsep.join((str(actual),str(actual/'Python')))},
                artifacts=(str(artifact),), artifact_types={str(artifact):'junit'})
            smoke = Phase('commonutils.smoke', (sys.executable, '-c', 'print("fresh smoke")'), str(root))
            phase = replace(phase, dependencies=(smoke.id,))
            plan = with_reuse(Plan('Fixture', 'reuse test', {}, (smoke, phase), str(root/'workspace')))
            runner = Executor(evidence_directory=root/'cache')
            first = runner.run(plan, root/'first')
            second = runner.run(plan, root/'second')
            self.assertEqual(first['status'], 'passed', first)
            self.assertEqual(second['status'], 'passed')
            self.assertNotIn('reused', second['phases'][0])
            self.assertTrue(second['phases'][1]['reused'])
            self.assertEqual(count.read_text(), 'x')
            failed_smoke = replace(smoke, argv=(sys.executable, '-c', 'raise SystemExit(1)'))
            blocked = runner.run(replace(plan, phases=(failed_smoke, plan.phases[1])), root/'blocked')
            self.assertEqual(blocked['status'], 'failed')
            self.assertEqual([row['status'] for row in blocked['phases']], ['failed', 'skipped'])
            self.assertEqual(count.read_text(), 'x')
            source.write_text('value = 2\n')
            third = runner.run(plan, root/'third')
            self.assertEqual(third['status'], 'passed')
            self.assertNotIn('reused', third['phases'][1])
            self.assertEqual(count.read_text(), 'xx')


class SnapshotInputIdentityTests(unittest.TestCase):
    def test_materialized_submodule_inputs_are_complete_and_match_active_checkout(self):
        from logistics_build.build_snapshots import materialize
        from tests.tooling.test_build_snapshots import SnapshotTests
        fixture = SnapshotTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        # Match real registered checkouts, then let materialize clone the shared
        # dependency independently into its isolated snapshot.
        (fixture.root / '.gitmodules').write_text(
            '[submodule "Python/commonUtils"]\n'
            '    path = Python/commonUtils\n'
            '    url = https://example.invalid/commonUtils.git\n')
        fixture.git(fixture.root, 'config', 'submodule.Python/commonUtils.active', 'true')
        fixture.commit(fixture.root)
        snapshot = fixture.directory / 'snapshot'
        materialize(fixture.root, snapshot)
        scopes = ['Python/commonUtils']
        original = inputs(fixture.root, scopes)
        self.assertEqual(inputs(snapshot, scopes), original)
        shared = snapshot / 'Python/commonUtils'
        (shared / 'library.py').write_text('VERSION = 2\n')
        self.assertNotEqual(inputs(snapshot, scopes), original)
        (shared / 'library.py').write_text('VERSION = 1\n')
        self.assertEqual(inputs(snapshot, scopes), original)
        (shared / 'new_test.py').write_text('new test\n')
        self.assertNotEqual(inputs(snapshot, scopes), original)
        (shared / 'new_test.py').unlink()
        (shared / '.gitignore').write_text('ignored.txt\n')
        baseline = inputs(snapshot, scopes)
        (shared / 'ignored.txt').write_text('private fixture\n')
        self.assertEqual(inputs(snapshot, scopes), baseline)
        (shared / 'library.py').unlink()
        with self.assertRaisesRegex(ValueError, 'Test input is missing'):
            inputs(snapshot, scopes)

    def test_uninitialized_or_linked_submodule_cannot_prove_inputs(self):
        import shutil
        from tests.tooling.test_build_snapshots import SnapshotTests
        fixture = SnapshotTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.shared.rename(fixture.directory / 'retained-git-fixture')
        fixture.shared.mkdir()
        with self.assertRaisesRegex(ValueError, 'submodule is not initialized'):
            inputs(fixture.root, ['Python/commonUtils'])
        fixture.shared.rmdir()
        fixture.shared.symlink_to(fixture.directory, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            inputs(fixture.root, ['Python/commonUtils'])


class ReuseSwitchTests(unittest.TestCase):
    def test_off_preserves_all_work_but_removes_keys_and_propagates_guest_policy(self):
        from dataclasses import replace
        from unittest.mock import patch
        from build_manager import Plan
        from logistics_build.test_evidence import with_reuse
        with TemporaryDirectory() as folder:
            phase = Phase('commonutils', ('python', 'tests.py'), folder, effect='test',
                          reuse_key='a' * 64, reuse_probe=('python', 'probe.py'))
            native = Phase('android-native', ('python', 'native.py'), folder, effect='test')
            plan = Plan('Fixture', 'Validation', {'run_overrides': {'testing.reuse_verified_results': 'off'}},
                        (phase, native), str(Path(folder) / 'workspace'))
            with patch('logistics_build.test_evidence.key_for', side_effect=AssertionError('Off must not inspect or certify cache keys')):
                fresh = with_reuse(plan)
            self.assertEqual([p.argv for p in fresh.phases], [p.argv for p in plan.phases])
            self.assertTrue(all(not p.reuse_key and not p.reuse_probe for p in fresh.phases))
            self.assertTrue(all(p.environment['LOGISTICS_REUSE_TEST_RESULTS'] == 'off' for p in fresh.phases))
            # The same flag reaches a separate guest process, without changing its suite list.
            guest_plan = replace(plan, source={}, phases=fresh.phases)
            self.assertTrue(all(not p.reuse_key for p in with_reuse(guest_plan).phases))

    @patch.dict(os.environ, {'LOGISTICS_REUSE_TEST_RESULTS': 'on', 'GITHUB_REF': ''})
    def test_fresh_local_leaves_github_publication_reuse_enabled(self):
        from build_manager import Plan
        from logistics_build.manager_journeys import run_values
        from logistics_build.test_evidence import with_reuse
        with TemporaryDirectory() as folder:
            local = Phase('macos', ('python', 'tests.py'), folder, effect='test')
            github = Phase('release', ('python', 'release.py'), folder, provider='github', effect='publish')
            source = {'run_overrides': run_values({'testing.reuse_verified_results': 'local-off'})}
            plan = Plan('Fixture', 'Validate and deliver', source, (local, github), str(Path(folder) / 'workspace'))
            checked_local, checked_github = with_reuse(plan).phases
            self.assertEqual(checked_local.environment['LOGISTICS_REUSE_TEST_RESULTS'], 'off')
            self.assertEqual(checked_github, github)
