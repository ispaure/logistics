"""GitHub mobile scheduling and shell gates, exercised with disposable fixtures."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import itertools
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[3]


def jobs(path):
    """Extract job blocks for contract checks; actionlint validates full YAML."""
    text = path.read_text().split('\njobs:\n', 1)[1]
    matches = list(re.finditer(r'^  ([\w-]+):\s*$', text, re.M))
    return {match[1]: text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)]
            for index, match in enumerate(matches)}


def script(job, step):
    block = job.split('      - name: ' + step + '\n', 1)[1].split('\n      - ', 1)[0]
    lines = block.split('        run: |\n', 1)[1].splitlines()
    return '\n'.join(line[10:] for line in lines if line.startswith('          '))


class ParallelIOSWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = jobs(REPO / '.github/workflows/mobile-build.yml')

    def test_parallel_devices_depend_only_on_one_ios_build(self):
        workflow = self.workflow
        self.assertIn('    needs: [environment, ios-build]\n', workflow['ios-ui'])
        self.assertIn('    needs: environment\n', workflow['ios-build'])
        self.assertIn('    needs: environment\n', workflow['android'])
        self.assertIn('fail-fast: false', workflow['ios-ui'])
        self.assertNotIn('max-parallel: 1', workflow['ios-ui'])
        self.assertIn('        device: [iphone, duo, ipad]\n', workflow['ios-ui'])
        self.assertNotIn('include_ipad', (REPO / '.github/workflows/mobile-build.yml').read_text())
        self.assertIn('briefcase build iOS --test --no-input', workflow['ios-build'])
        self.assertNotIn('briefcase build', workflow['ios-ui'])
        self.assertIn('name: logistics-ios-test-project', workflow['ios-build'])
        self.assertIn('name: logistics-ios-test-project', workflow['ios-ui'])
        self.assertIn('name: logistics-native-ios-${{ matrix.device }}', workflow['ios-ui'])
        self.assertIn('if: always()', workflow['ios-ui'])
        release = jobs(REPO / '.github/workflows/release.yml')
        self.assertIn('needs: [evidence, validate, mobile-build, mobile-runtime]', release['package'])
        self.assertIn('needs: package', release['publish'])
        self.assertIn('needs: [ios-build, ios-ui, android]', workflow['native-gate'])
        self.assertIn('if: always()', workflow['native-gate'])
        self.assertNotIn('continue-on-error', ''.join(workflow.values()))

    def test_release_package_accepts_only_fresh_success_or_verified_skips(self):
        package = jobs(REPO / '.github/workflows/release.yml')['package']
        expression = package.split('    if: >-\n', 1)[1].split('    runs-on:', 1)[0].strip()
        expression = expression.replace('&&', ' and ').replace('||', ' or ').replace('!cancelled()', 'not cancelled()')
        expression = compile(' '.join(expression.splitlines()), '<actual GitHub package condition>', 'eval')
        class Needs(dict):
            __getattr__ = dict.__getitem__
        states = ('success', 'failure', 'cancelled', 'skipped')
        for evidence_status, cancelled in itertools.product(states, (False, True)):
            for results in itertools.product(states, repeat=3):
                for proofs in itertools.product((False, True), repeat=3):
                    names = ('validate', 'mobile-build', 'mobile-runtime')
                    outputs = {name: 'true' if proof else 'false' for name, proof in zip(names, proofs)}
                    needs = Needs({name: SimpleNamespace(result=result) for name, result in zip(names, results)})
                    needs['evidence'] = SimpleNamespace(result=evidence_status, outputs=Needs(outputs))
                    expected = (not cancelled and evidence_status == 'success' and all(
                        result == 'success' or (result == 'skipped' and proof)
                        for result, proof in zip(results, proofs)))
                    actual = eval(expression, {'__builtins__': {}},
                                  dict(needs=needs, always=lambda: True, cancelled=lambda: cancelled))
                    self.assertEqual(actual, expected, (evidence_status, cancelled, results, proofs))

    @unittest.skipUnless(shutil.which('bash'), 'Workflow shell needs bash')
    def test_gate_rejects_each_failed_cancelled_or_required_skipped_result(self):
        gate = script(self.workflow['native-gate'], 'Reject failed, cancelled or required skipped checks')
        for target in ('ios', 'android', 'both', 'invalid'):
            for results in itertools.product(('success', 'failure', 'cancelled', 'skipped'), repeat=3):
                build, ios, android = results
                expected = ((target == 'both' and results == ('success',) * 3)
                            or (target == 'ios' and results == ('success', 'success', 'skipped'))
                            or (target == 'android' and results == ('skipped', 'skipped', 'success')))
                with self.subTest(target=target, results=results):
                    result = subprocess.run(['bash', '-e', '-c', gate], env=dict(os.environ,
                        TARGET=target, IOS_BUILD_RESULT=build, IOS_RESULT=ios, ANDROID_RESULT=android),
                        capture_output=True)
                    self.assertEqual(result.returncode == 0, expected)

    @unittest.skipUnless(shutil.which('tar') and os.name != 'nt', 'Unix archive permissions')
    def test_shared_archive_preserves_binary_and_separates_device_reports(self):
        archive = next(line.strip() for line in self.workflow['ios-build'].splitlines()
                       if line.strip().startswith('tar -czf'))
        restore = next(line.strip().removeprefix('run: ') for line in self.workflow['ios-ui'].splitlines()
                       if line.strip().startswith('run: tar -xzf'))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / 'producer'
            build.mkdir()
            app = Path('build/logisticsmobile/ios/xcode/build/Debug-iphonesimulator/Logistics Mobile.app')
            binary = build / app / 'Logistics Mobile'
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'synthetic shared native binary')
            binary.chmod(0o755)
            (binary.parent / 'binary-link').symlink_to('Logistics Mobile')
            (build / 'payload').mkdir()
            (build / 'payload/source.json').write_text('{"source": "fixture"}')
            runtime = root / 'runtime'
            runtime.mkdir()
            env = dict(os.environ, RUNNER_TEMP=str(runtime))
            subprocess.run(['bash', '-e', '-c', archive], cwd=build, env=env, check=True)
            (runtime / 'ios-test-project').mkdir()
            shutil.move(runtime / 'Logistics-ios-test-project.tar.gz', runtime / 'ios-test-project')
            for device in ('iphone', 'duo', 'ipad'):
                consumer = root / device
                consumer.mkdir()
                subprocess.run(['bash', '-e', '-c', restore], cwd=consumer, env=env, check=True)
                restored = consumer / app / 'Logistics Mobile'
                self.assertEqual(restored.read_bytes(), binary.read_bytes())
                self.assertEqual(restored.stat().st_mode, binary.stat().st_mode)
                self.assertTrue((restored.parent / 'binary-link').is_symlink())
                self.assertEqual((consumer / 'payload/source.json').read_text(), '{"source": "fixture"}')
                (consumer / 'logs').mkdir()
                (consumer / 'logs/ios-native-ui.json').write_text(device)
            self.assertEqual([(root / name / 'logs/ios-native-ui.json').read_text()
                              for name in ('iphone', 'duo', 'ipad')], ['iphone', 'duo', 'ipad'])

    @unittest.skipUnless(shutil.which('bash'), 'Workflow shell needs bash')
    def test_each_device_invokes_its_required_suite_and_propagates_failure(self):
        run = script(self.workflow['ios-ui'], 'Exercise panels, rotation and safe areas')
        self.assertIn('"$selector" --owned', run)
        self.assertIn('      - name: Remove the owned native validation simulator\n        if: always()\n',
                      self.workflow['ios-ui'])
        self.assertIn('run: python validation/ui_tools.py ios-cleanup', self.workflow['ios-ui'])
        fixture = '''import json, os, sys
from pathlib import Path
assert Path(os.environ['BRIEFCASE_HOME']).is_dir(), 'Briefcase home must exist on a fresh runner'
if sys.argv[1] != 'run':
    print('synthetic-device-' + sys.argv[1])
else:
    Path('invocation.json').write_text(json.dumps(sys.argv[1:]))
    sys.exit(int(Path('exit-code').read_text()))
'''
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'validation').mkdir()
            (root / 'validation/ui_tools.py').write_text(fixture)
            command = ('python() { ' + shlex.quote(sys.executable) + ' "$@"; }\n'
                       'defaults() { printf "%s\\n" "$*" > keyboard-setting.txt; }\n' + run)
            for device, selector, flags in (
                    ('iphone', 'ios-device', []), ('duo', 'ios-duo', ['--require-duo']),
                    ('ipad', 'ios-ipad', ['--require-independent-windows'])):
                for code in (0, 1, 143):
                    with self.subTest(device=device, code=code):
                        (root / 'exit-code').write_text(str(code))
                        result = subprocess.run(['bash', '-e', '-c', command], cwd=root,
                            env=dict(os.environ, IOS_DEVICE=device,
                                     BRIEFCASE_HOME=str(root / 'fresh-homes' / f'{device}-{code}')),
                            capture_output=True)
                        self.assertEqual(result.returncode, code)
                        self.assertEqual((root / 'keyboard-setting.txt').read_text(),
                            'write com.apple.iphonesimulator ConnectHardwareKeyboard -bool false\n')
                        self.assertEqual(json.loads((root / 'invocation.json').read_text()),
                            ['run', 'ios', '--device', 'synthetic-device-' + selector, '--no-update', *flags])
