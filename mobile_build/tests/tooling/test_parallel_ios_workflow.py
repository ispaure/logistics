"""GitHub mobile scheduling and shell gates, exercised with disposable fixtures."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import importlib.util
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

    @unittest.skipUnless(shutil.which('bash'), 'Workflow cache setup needs Bash')
    def test_android_cache_setup_resolves_runtime_paths_with_spaces(self):
        command = script(self.workflow['android'], 'Initialize owned Android Go caches')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'runner with spaces'
            runtime.mkdir()
            output = root / 'github-env'
            env = dict(os.environ, RUNNER_TEMP=str(runtime), GITHUB_ENV=str(output))
            subprocess.run(['bash', '-e', '-c', command], env=env, check=True)
            values = dict(line.split('=', 1) for line in output.read_text().splitlines())
            self.assertEqual(values, dict(GOCACHE=str(runtime / 'logistics-android-go-cache'),
                GOMODCACHE=str(runtime / 'logistics-android-go-modules')))

    @unittest.skipUnless(shutil.which('bash'), 'Workflow cache ownership guard needs Bash')
    def test_android_cache_cleanup_rejects_unrelated_cache_before_invoking_go(self):
        command = script(self.workflow['android'], 'Release owned Go caches after compilation')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'runner'
            runtime.mkdir()
            unrelated = root / 'unrelated'
            unrelated.mkdir()
            sentinel = unrelated / 'keep'
            sentinel.write_text('preserve')
            binary = root / 'bin'
            binary.mkdir()
            go = binary / 'go'
            go.write_text('#!/bin/sh\nprintf invoked > "$CALLED"\n')
            go.chmod(0o755)
            called = root / 'called'
            env = dict(os.environ, RUNNER_TEMP=str(runtime), GOCACHE=str(unrelated),
                GOMODCACHE=str(runtime / 'logistics-android-go-modules'), CALLED=str(called),
                PATH=str(binary) + os.pathsep + os.environ.get('PATH', ''))
            result = subprocess.run(['bash', '-e', '-c', command], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(called.exists())
            self.assertEqual(sentinel.read_text(), 'preserve')

    @unittest.skipUnless(shutil.which('bash'), 'Headroom gate needs Bash')
    def test_android_headroom_fails_before_image_install_without_deleting_shared_paths(self):
        command = script(self.workflow['android-ui'],
                         'Check emulator disk headroom before installing the system image')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / 'df'
            binary.write_text('#!/bin/sh\nif [ "$1" = "-Pk" ]; then\n'
                              'printf "Filesystem 1024-blocks Used Available Capacity Mounted\n"\n'
                              'printf "fixture 75000000 0 %s 0%% /\n" "$FREE_KIB"\nfi\n')
            binary.chmod(0o755)
            for available, expected in ((6606028, False), (12582911, False),
                                        (12582912, True), (18000000, True)):
                result = subprocess.run(['bash', '-e', '-c', command], env=dict(os.environ,
                    RUNNER_TEMP=str(root), FREE_KIB=str(available),
                    PATH=str(root) + os.pathsep + os.environ.get('PATH', '')), capture_output=True)
                self.assertEqual(result.returncode == 0, expected)
                if not expected:
                    self.assertIn(b'::error::', result.stdout)
            self.assertNotIn('rm ', command)

    @unittest.skipUnless(shutil.which('tar') and os.name != 'nt', 'Unix archives')
    def test_android_handoff_contains_exact_apk_metadata_without_compiler_caches(self):
        import tarfile
        build = self.workflow['android']
        runtime = self.workflow['android-ui']
        self.assertIn('needs: [environment, android]', runtime)
        self.assertIn('briefcase build android --test --no-input', build)
        self.assertNotIn('briefcase build', runtime)
        self.assertNotIn('setup-go', runtime)
        self.assertIn('--no-update', script(runtime, 'Exercise Android panels, rotation and safe areas'))
        archive = script(build, 'Archive the exact Android test application')
        restore = script(runtime, 'Restore the exact Android test application')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            producer = root / 'producer'
            consumer = root / 'consumer'
            producer.mkdir()
            consumer.mkdir()
            paths = ('build/logisticsmobile/android/gradle/briefcase.toml',
                     'build/logisticsmobile/android/gradle/app/build/outputs/apk/debug/app-debug.apk',
                     'payload/source.json')
            for name in (*paths, 'build/logisticsmobile/android/gradle/.gradle/unrelated-cache'):
                target = producer / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(name)
            env = dict(os.environ, RUNNER_TEMP=str(root), COPYFILE_DISABLE="1")
            subprocess.run(['bash', '-e', '-c', archive], cwd=producer, env=env, check=True)
            output = root / 'Logistics-android-test-project.tar.gz'
            with tarfile.open(output) as bundle:
                self.assertEqual(bundle.getnames(), list(paths))
            (root / 'android-test-project').mkdir()
            shutil.move(output, root / 'android-test-project' / output.name)
            subprocess.run(['bash', '-e', '-c', restore], cwd=consumer, env=env, check=True)
            for name in paths:
                self.assertEqual((consumer / name).read_bytes(), (producer / name).read_bytes())
            self.assertFalse((consumer / 'build/logisticsmobile/android/gradle/.gradle').exists())
            self.assertFalse((root / 'android-test-project' / output.name).exists())

    @unittest.skipUnless(importlib.util.find_spec('briefcase'), 'Pinned Briefcase host dependency')
    def test_minimal_android_handoff_uses_real_briefcase_run_without_building(self):
        from unittest.mock import Mock
        from briefcase.commands.run import RunCommand
        from briefcase.platforms.android.gradle import GradleMixin
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / 'build/logisticsmobile/android/gradle'
            apk = project / 'app/build/outputs/apk/debug/app-debug.apk'
            apk.parent.mkdir(parents=True)
            apk.write_bytes(b'verified fixture APK')
            (project / 'briefcase.toml').write_text('[briefcase]\ntarget_version="0.3.27"\n')
            app = SimpleNamespace(app_name='logisticsmobile', test_mode=True, external_package_path=None)
            owner = SimpleNamespace(apps={app.app_name: app},
                finalize=Mock(return_value={app.app_name: app}),
                bundle_path=lambda app: project, verify_app=Mock(), run_app=Mock(),
                build_command=Mock(side_effect=AssertionError('Handoff must never trigger a build')))
            owner.binary_executable_path = lambda app: GradleMixin.binary_path(owner, app)
            RunCommand.__call__(owner, test_mode=True, no_update=True)
            owner.build_command.assert_not_called()
            owner.run_app.assert_called_once_with(app, passthrough=[])

    @unittest.skipUnless(shutil.which('bash'), 'Bash is required for workflow shell contracts')
    def test_object_diagnostics_are_absent_when_disabled_and_explicit_when_enabled(self):
        prefix = script(self.workflow['ios-ui'], 'Exercise panels, rotation and safe areas').split('mkdir -p', 1)[0]
        names = ('SIMCTL_CHILD_NSZombieEnabled', 'SIMCTL_CHILD_MallocStackLogging')
        command = shlex.quote(sys.executable) + ' -c ' + shlex.quote(
            'import json,os;print(json.dumps([os.environ.get(n) for n in ' + repr(names) + ']))')
        for enabled, expected in [('false', [None, None]), ('true', ['YES', '1'])]:
            with self.subTest(enabled=enabled):
                env = dict(os.environ, IOS_OBJECT_DIAGNOSTICS=enabled)
                env.update({name: 'inherited' for name in names})
                result = subprocess.run(['bash', '-c', prefix + command], env=env,
                                        text=True, capture_output=True, check=True)
                self.assertEqual(json.loads(result.stdout), expected)

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
        self.assertIn('needs: [ios-build, ios-ui, android, android-ui]', workflow['native-gate'])
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
            for results in itertools.product(('success', 'failure', 'cancelled', 'skipped'), repeat=4):
                build, ios, android, android_ui = results
                expected = ((target == 'both' and results == ('success',) * 4)
                            or (target == 'ios' and results == ('success', 'success', 'skipped', 'skipped'))
                            or (target == 'android' and results == ('skipped', 'skipped', 'success', 'success')))
                with self.subTest(target=target, results=results):
                    result = subprocess.run(['bash', '-e', '-c', gate], env=dict(os.environ,
                        TARGET=target, IOS_BUILD_RESULT=build, IOS_RESULT=ios, ANDROID_RESULT=android, ANDROID_UI_RESULT=android_ui),
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
