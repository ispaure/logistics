"""Tracked test input scopes invalidate affected evidence, not unrelated edits."""
from dataclasses import replace
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from build_manager import Phase
from Scripts.test_evidence import key_for


class InputIdentityTests(unittest.TestCase):
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

    def test_native_or_external_phases_never_receive_portable_test_keys(self):
        phase = Phase('android-native', ('python', 'test.py'), '.', effect='test')
        self.assertEqual(key_for(phase), '')
        self.assertEqual(key_for(replace(phase, id='commonutils', effect='deploy')), '')

    def test_real_execution_probe_reuses_same_inputs_then_runs_changed_source(self):
        import json
        import os
        import sys
        from build_manager import Plan, Executor
        from Scripts.test_evidence import with_reuse
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
            plan = with_reuse(Plan('Fixture', 'reuse test', {}, (phase,), str(root/'workspace')))
            runner = Executor(evidence_directory=root/'cache')
            first = runner.run(plan, root/'first')
            second = runner.run(plan, root/'second')
            self.assertEqual(first['status'], 'passed', first)
            self.assertEqual(second['status'], 'passed')
            self.assertTrue(second['phases'][0]['reused'])
            self.assertEqual(count.read_text(), 'x')
            source.write_text('value = 2\n')
            third = runner.run(plan, root/'third')
            self.assertEqual(third['status'], 'passed')
            self.assertNotIn('reused', third['phases'][0])
            self.assertEqual(count.read_text(), 'xx')
