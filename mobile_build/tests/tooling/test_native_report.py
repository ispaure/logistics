"""UI evidence verifier contracts; these fixtures are not native device evidence."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import base64
import importlib.util
import json
from pathlib import Path
import plistlib
import subprocess
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

REPO = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('mobile_ui_tools', REPO / 'mobile_build/validation/ui_tools.py')
ui_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui_tools)


class NativeReportTests(unittest.TestCase):
    def test_hosted_emulator_records_sdk_revision_and_current_software_backend(self):
        import os
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'emulator').mkdir()
            (root / 'emulator/source.properties').write_text('Pkg.Revision = 37.2.12\n')
            logs = root / 'logs'
            logs.mkdir()
            with patch.dict(os.environ, {'ANDROID_HOME': str(root)}):
                ui_tools.record_android_emulator(logs)
            self.assertEqual(json.loads((logs / 'android-emulator.json').read_text()),
                             dict(revision='37.2.12', renderer='software'))

    def test_host_memory_identifies_process_pressure_without_reading_private_arguments(self):
        with TemporaryDirectory() as directory:
            proc = Path(directory)
            (proc / 'meminfo').write_text('MemTotal: 16384 kB\nMemAvailable: 1024 kB\nSwapFree: 0 kB\n')
            (proc / 'vmstat').write_text('oom_kill 2\n')
            for pid, name, rss in ((11, 'qemu-system', 8192), (12, 'java', 2048)):
                entry = proc / str(pid)
                entry.mkdir()
                (entry / 'status').write_text(f'Name: {name}\nVmRSS: {rss} kB\n')
                # Deliberately no cmdline or environ: only public status is needed.
            (proc / '13').mkdir()  # A process disappearing during sampling is harmless.
            row = ui_tools.linux_host_memory(proc)
            self.assertEqual(row['oom_kill'], 2)
            self.assertEqual(row['memory_mib']['MemAvailable'], 1)
            self.assertEqual(row['processes'], [dict(pid=11, name='qemu-system', rss_kib=8192),
                                                dict(pid=12, name='java', rss_kib=2048)])

    def test_direct_owned_cleanup_bootstraps_real_manager_without_pythonpath(self):
        import sys, shutil
        import build_manager
        code = '''
import runpy, sys
from pathlib import Path
sys.path = [p for p in sys.path if not ((Path(p)/'build_manager').is_dir() or (Path(p)/'commonUtils').is_dir())]
sys.path.insert(0, sys.argv[1])
sys.argv = [sys.argv[2], 'ios-cleanup']
runpy.run_path(sys.argv[0], run_name='__main__')
'''
        with TemporaryDirectory() as directory:
            manager = Path(directory) / 'manager'
            shutil.copytree(Path(build_manager.__file__).parent, manager / 'build_manager',
                            ignore=shutil.ignore_patterns('__pycache__'))
            # Preserve the real manager's pinned dependency beside its package,
            # matching the extracted checkout layout in an isolated interpreter.
            shutil.copytree(Path(build_manager.__file__).parent.parent / 'commonUtils',
                            manager / 'commonUtils',
                            ignore=shutil.ignore_patterns('__pycache__', '.git', 'tests'))
            result = subprocess.run([sys.executable, '-I', '-X', 'utf8', '-c', code,
                str(manager), str(REPO / 'mobile_build/validation/ui_tools.py')],
                cwd=directory, capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_owned_simulator_matches_sdk_and_cleanup_uses_its_saved_identity(self):
        old = dict(udid='old', name='iPhone', state='Booted', isAvailable=True,
                   deviceTypeIdentifier='com.apple.CoreSimulator.SimDeviceType.iPhone-18-Pro')
        current = dict(old, udid='current', state='Shutdown')
        client = Mock()
        client.devices.return_value = {'devices': {
            'com.apple.CoreSimulator.SimRuntime.iOS-26-5': [old],
            'com.apple.CoreSimulator.SimRuntime.iOS-27-0': [current]}}
        client.create.return_value = 'fresh-owned-device'
        client.matching.return_value = None
        with TemporaryDirectory() as directory:
            lease = Path(directory) / 'lease.json'
            device = ui_tools.owned_ios_device(lease, client=client, sdk='27.1')
            record = json.loads(lease.read_text())
            self.assertEqual(device, 'fresh-owned-device')
            client.create.assert_called_once_with(record['name'], current['deviceTypeIdentifier'],
                'com.apple.CoreSimulator.SimRuntime.iOS-27-0')
            client.boot.assert_called_once_with(device)
            with self.assertRaisesRegex(ValueError, 'previous owned'):
                ui_tools.owned_ios_device(lease, client=client, sdk='27.1')
            ui_tools.cleanup_owned_ios_device(lease, client=client)
            client.remove.assert_called_once_with(device, record['name'])
            self.assertTrue(json.loads(lease.read_text())['removed'])

    def test_owned_boot_failure_retains_cleanup_lease_and_foreign_label_is_refused(self):
        client = Mock()
        client.devices.return_value = {'devices': {'com.apple.CoreSimulator.SimRuntime.iOS-27-0': [
            dict(udid='profile', name='iPad', state='Shutdown', isAvailable=True,
                 deviceTypeIdentifier='com.apple.CoreSimulator.SimDeviceType.iPad-Pro')]}}
        client.create.return_value = 'created-before-failure'
        client.boot.side_effect = RuntimeError('synthetic boot failure')
        with TemporaryDirectory() as directory:
            lease = Path(directory) / 'lease.json'
            with self.assertRaisesRegex(RuntimeError, 'boot failure'):
                ui_tools.owned_ios_device(lease, client=client, sdk='27.1', ipad=True)
            record = json.loads(lease.read_text())
            self.assertEqual(record['device'], 'created-before-failure')
            lease.write_text(json.dumps(dict(record, name='Personal simulator')))
            with self.assertRaisesRegex(ValueError, 'ownership label'):
                ui_tools.cleanup_owned_ios_device(lease, client=client)
            client.remove.assert_not_called()

    def test_owned_boot_timeout_preserves_phase_output_and_cleanup_identity(self):
        client = Mock()
        client.devices.return_value = {'devices': {'com.apple.CoreSimulator.SimRuntime.iOS-27-1': [
            dict(udid='profile', name='iPhone Duo', state='Shutdown', isAvailable=True,
                 deviceTypeIdentifier='com.apple.CoreSimulator.SimDeviceType.iPhone-Duo')]}}
        client.create.return_value = 'owned-timeout'
        client.boot.side_effect = subprocess.TimeoutExpired(
            ['xcrun', 'simctl', 'bootstatus'], 180, output=b'Waiting on Data Migration', stderr=None)
        with TemporaryDirectory() as directory:
            lease = Path(directory) / 'lease.json'
            with self.assertRaises(subprocess.TimeoutExpired):
                ui_tools.owned_ios_device(lease, client=client, sdk='27.1', duo=True)
            self.assertEqual(json.loads(lease.read_text())['device'], 'owned-timeout')
            evidence = json.loads(lease.with_name('ios-native-ui-boot-timeout.json').read_text())
            self.assertEqual(evidence['stdout'], 'Waiting on Data Migration')
            self.assertEqual(evidence['stderr'], '')
            self.assertEqual(evidence['timeout'], 180)
            client.matching.return_value = None
            ui_tools.cleanup_owned_ios_device(lease, client=client)
            self.assertTrue(json.loads(lease.read_text())['removed'])

    def test_shared_test_app_is_reused_and_wrong_or_missing_builds_fail_before_launch(self):
        import os
        from unittest.mock import patch
        report = self.report()
        def revision(args, **kwargs):
            key = 'commonUtils_commit' if 'commonUtils' in args[2] else 'logistics_commit'
            return report['source'][key]
        def launch(command, *, stdout, **kwargs):
            self.assertIn('--no-update', command)
            stdout.write(ui_tools.PREFIX + json.dumps(report) + '\n')
            stdout.flush()
            return SimpleNamespace(wait=lambda **kwargs: 0)
        with TemporaryDirectory() as directory, patch.object(ui_tools.subprocess, 'Popen', side_effect=launch) as process, \
                patch.object(ui_tools.subprocess, 'check_output', side_effect=revision):
            previous = Path.cwd()
            os.chdir(directory)
            try:
                project = Path('build/logisticsmobile/ios/xcode')
                app = project / 'build/Debug-iphonesimulator/Logistics Mobile.app'
                (app / 'app/mobile').mkdir(parents=True)
                (app / 'Logistics Mobile').write_text('synthetic binary')
                (project / 'briefcase.toml').write_text('[briefcase]\n')
                Path('payload').mkdir()
                Path('payload/source.json').write_text(json.dumps(report['source']))
                manifest = app / 'app/mobile/source.json'
                manifest.write_text(json.dumps(report['source']))
                info = app / 'Info.plist'
                info.write_bytes(plistlib.dumps(dict(MainModule='tests.logisticsmobile')))
                for family in ('iphone', 'duo'):
                    # Separate jobs restore the same project, without rebuilding.
                    self.assertEqual(ui_tools.run('ios', family, no_update=True), report)
                    self.assertEqual(manifest.read_text(), json.dumps(report['source']))
                self.assertEqual(process.call_count, 2)
                process.reset_mock()
                for source in (dict(report['source'], dirty=True),
                               dict(report['source'], logistics_commit='0' * 40),
                               dict(report['source'], commonUtils_commit='0' * 40)):
                    manifest.write_text(json.dumps(source))
                    with self.assertRaisesRegex(ValueError, 'different source'):
                        ui_tools.run('ios', 'device', no_update=True)
                manifest.write_text(json.dumps(report['source']))
                info.write_bytes(plistlib.dumps(dict(MainModule='logisticsmobile')))
                with self.assertRaisesRegex(ValueError, 'test mode'):
                    ui_tools.run('ios', 'device', no_update=True)
                (app / 'Logistics Mobile').unlink()
                with self.assertRaisesRegex(ValueError, 'missing'):
                    ui_tools.run('ios', 'device', no_update=True)
                process.assert_not_called()
            finally:
                os.chdir(previous)

    def test_simulator_selection_keeps_duo_separate_from_renamed_iphone(self):
        def device(kind, name, state='Shutdown'):
            return dict(isAvailable=True, name=name, state=state, udid=name,
                        deviceTypeIdentifier='com.apple.CoreSimulator.SimDeviceType.' + kind)
        data = {'devices': {'com.apple.CoreSimulator.SimRuntime.iOS-27-1': [
            device('iPhone-Duo', 'iPhone Duo', 'Booted'),
            device('iPhone-18-Pro', 'Review phone'), device('iPad-Pro', 'Review tablet')]}}
        self.assertEqual(ui_tools.select_ios_device(data), 'Review phone')
        self.assertEqual(ui_tools.select_ios_device(data, duo=True), 'iPhone Duo')
        self.assertEqual(ui_tools.select_ios_device(data, ipad=True), 'Review tablet')
        data['devices']['com.apple.CoreSimulator.SimRuntime.iOS-27-1'].pop(0)
        with self.assertRaisesRegex(RuntimeError, 'Duo'):
            ui_tools.select_ios_device(data, duo=True)

    def test_duo_gate_rejects_missing_poses_or_incomplete_rotation(self):
        samples = [dict(panel=panel, orientation=orientation, pose=dict(duo_capable=True))
                   for panel in ('workspaces', 'folder', 'comic', 'documentation')
                   for orientation in ('portrait', 'landscape-left', 'landscape-right')]
        report = dict(ui_review=dict(rotation_samples=samples))
        ui_tools.verify_duo_rotation(report)
        for broken in (samples[:-1], [dict(row, pose=dict(duo_capable=False)) for row in samples], []):
            with self.assertRaises(ValueError):
                ui_tools.verify_duo_rotation(dict(ui_review=dict(rotation_samples=broken)))

    def test_repeated_running_callback_keeps_one_exercise_per_app(self):
        coroutine, task = object(), Mock()
        exercise = Mock(return_value=coroutine)
        loop = Mock()
        loop.create_task.return_value = task
        app = SimpleNamespace(loop=loop)
        self.assertIs(ui_tools.contract.start_native_check(app, exercise), task)
        self.assertIs(ui_tools.contract.start_native_check(app, exercise), task)
        exercise.assert_called_once_with(app)
        loop.create_task.assert_called_once_with(coroutine)
        # A report being flushed must not trigger a second run either.
        task.done.return_value = True
        self.assertIs(ui_tools.contract.start_native_check(app, exercise), task)
        self.assertEqual(loop.create_task.call_count, 1)
        other = SimpleNamespace(loop=loop)
        ui_tools.contract.start_native_check(other, exercise)
        self.assertEqual(loop.create_task.call_count, 2)

    def test_native_report_requires_every_case_and_exact_source(self):
        source = dict(dirty=False,
            logistics_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
            commonUtils_commit=subprocess.check_output(['git', '-C', 'Python/commonUtils', 'rev-parse', 'HEAD'],
                                                       cwd=REPO, text=True).strip())
        report = dict(schema=1, suite='logistics-native-ui', target='android', backend='toga_android.app',
                      cases=list(ui_tools.contract.CASES), expected_cases=list(ui_tools.contract.CASES),
                      success=True, error='', source=source)
        with TemporaryDirectory() as directory:
            log, output = Path(directory) / 'native.log', Path(directory) / 'native.json'
            def write(data):
                log.write_text('native stdout: ' + ui_tools.PREFIX + json.dumps(data) + '\n')
            write(report)
            self.assertEqual(ui_tools.verify(log, 'android', output), report)
            for changes in (dict(cases=[]),
                            dict(cases=[case for case in report['cases'] if case != 'native_rotation_safe_areas']),
                            dict(success=False), dict(backend='toga_dummy.app'),
                            dict(source=dict(source, dirty=True)),
                            dict(source=dict(source, logistics_commit='0' * 40))):
                write(dict(report, **changes))
                with self.assertRaises(ValueError):
                    ui_tools.verify(log, 'android', output)

    def test_chunked_local_report_requires_complete_matching_snapshot(self):
        source = dict(dirty=True, source_sha256='a' * 64,
            logistics_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
            commonUtils_commit=subprocess.check_output(['git', '-C', 'Python/commonUtils', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip())
        report = dict(schema=1, suite='logistics-native-ui', target='ios', backend='toga_iOS.app',
                      cases=list(ui_tools.contract.CASES), expected_cases=list(ui_tools.contract.CASES),
                      success=True, error='', source=source)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            log, output, manifest = root / 'run.log', root / 'result.json', root / 'source.json'
            manifest.write_text(json.dumps(source))
            encoded = base64.b64encode(json.dumps(report).encode()).decode()
            parts = [encoded[index:index+450] for index in range(0, len(encoded), 450)]
            lines = ['LOGISTICS_NATIVE_UI_CHUNK=' + json.dumps(dict(index=index, count=len(parts), encoding='base64', data=data)) for index, data in enumerate(parts)]
            log.write_text('\n'.join(lines))
            self.assertEqual(ui_tools.verify(log, 'ios', output, local_manifest=manifest), report)
            with self.assertRaises(ValueError):
                ui_tools.verify(log, 'ios', output)
            for invalid in (lines[:-1], lines + lines[:1], lines[::-1]):
                log.write_text('\n'.join(invalid))
                with self.assertRaises(ValueError):
                    ui_tools.verify(log, 'ios', output, local_manifest=manifest)
            log.write_text('\n'.join(lines))
            manifest.write_text(json.dumps(source | {'source_sha256': 'b' * 64}))
            with self.assertRaises(ValueError):
                ui_tools.verify(log, 'ios', output, local_manifest=manifest)

    def report(self):
        return dict(schema=1, suite='logistics-native-ui', target='ios', backend='toga_iOS.app',
            cases=list(ui_tools.contract.CASES), expected_cases=list(ui_tools.contract.CASES),
            success=True, error='', source=dict(dirty=False,
                logistics_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
                commonUtils_commit=subprocess.check_output(['git', '-C', 'Python/commonUtils', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()))

    def test_simulator_file_rejects_missing_and_previous_results(self):
        import os
        from unittest.mock import patch
        from types import SimpleNamespace
        report = self.report()
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'Library/Caches/logistics-native-ui-result.json'
            path.parent.mkdir(parents=True)
            result = SimpleNamespace(returncode=0, stdout=directory)
            with patch.object(ui_tools.subprocess, 'run', return_value=result):
                self.assertIsNone(ui_tools.simulator_report('device', 2_000_000_000))
                path.write_text(json.dumps(report))
                os.utime(path, ns=(1_000_000_000, 1_000_000_000))
                self.assertIsNone(ui_tools.simulator_report('device', 2_000_000_000))
                os.utime(path, ns=(3_000_000_000, 3_000_000_000))
                self.assertEqual(ui_tools.simulator_report('device', 2_000_000_000), report)

    def test_lost_log_exit_marker_uses_only_complete_verified_file(self):
        import os
        from unittest.mock import patch
        report = self.report()
        def revision(args, **kwargs):
            key = 'commonUtils_commit' if 'commonUtils' in args[2] else 'logistics_commit'
            return report['source'][key]
        with TemporaryDirectory() as directory, patch.object(ui_tools.subprocess, 'Popen') as process, \
                patch.object(ui_tools.subprocess, 'check_output', side_effect=revision):
            process.return_value.wait.return_value = 200
            previous = Path.cwd()
            os.chdir(directory)
            try:
                with patch.object(ui_tools, 'simulator_report', return_value=report):
                    self.assertEqual(ui_tools.run('ios', 'device'), report)
                    transport = json.loads(Path('logs/ios-report-transport.json').read_text())
                    self.assertEqual(transport['briefcase_exit_code'], 200)
                    with self.assertRaisesRegex(ValueError, 'independent system windows'):
                        ui_tools.run('ios', 'device', require_independent_windows=True)
                for invalid in (dict(report, success=False), dict(report, cases=[]),
                                dict(report, source=dict(report['source'], logistics_commit='0' * 40))):
                    with patch.object(ui_tools, 'simulator_report', return_value=invalid):
                        with self.assertRaises(ValueError):
                            ui_tools.run('ios', 'device')
            finally:
                os.chdir(previous)

    def test_fatal_fault_is_retained_without_a_json_result_or_stale_previous_device(self):
        import os
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cache, logs = root / 'Library/Caches', root / 'logs'
            cache.mkdir(parents=True)
            logs.mkdir()
            fault = cache / 'logistics-native-ui-fault.log'
            fault.write_text('Fatal Python error: Segmentation fault\nNative callback stack')
            os.utime(fault, ns=(3_000_000_000, 3_000_000_000))
            (logs / 'ios-native-ui-cached.json').write_text('previous phone success')
            (logs / 'ios-native-ui-error.txt').write_text('previous phone error')
            result = SimpleNamespace(returncode=0, stdout=str(root))
            with patch.object(ui_tools.subprocess, 'run', return_value=result):
                self.assertIsNone(ui_tools.simulator_report('duo', 2_000_000_000, diagnostics=logs))
                self.assertEqual((logs / 'ios-native-ui-fault.log').read_text(), fault.read_text())
                self.assertFalse((logs / 'ios-native-ui-cached.json').exists())
                self.assertFalse((logs / 'ios-native-ui-error.txt').exists())
                os.utime(fault, ns=(1_000_000_000, 1_000_000_000))
                self.assertIsNone(ui_tools.simulator_report('duo', 2_000_000_000, diagnostics=logs))
                self.assertFalse((logs / 'ios-native-ui-fault.log').exists())

    def test_native_fault_logger_uses_a_real_file_not_the_os_log_stream(self):
        from unittest.mock import patch
        with TemporaryDirectory() as directory, patch('faulthandler.enable') as enable:
            with ui_tools.contract.enable_native_fault_log(directory) as stream:
                self.assertGreaterEqual(stream.fileno(), 0)
                enable.assert_called_once_with(stream, all_threads=True)

    def test_rejected_simulator_report_and_traceback_are_retained(self):
        import os
        from unittest.mock import patch
        rejected = dict(self.report(), success=False, cases=[], error='AssertionError: iPad fixture')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / 'Library/Caches'
            cache.mkdir(parents=True)
            result = cache / 'logistics-native-ui-result.json'
            error = cache / 'logistics-native-ui-error.txt'
            result.write_text(json.dumps(rejected))
            error.write_text('Traceback: actual iPad fixture\nAssertionError: iPad fixture\n')
            for path in (result, error):
                os.utime(path, ns=(3_000_000_000, 3_000_000_000))
            logs = root / 'logs'
            with patch.object(ui_tools.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=str(root))):
                actual = ui_tools.simulator_report('ipad-device', 2_000_000_000, diagnostics=logs)
            validated = logs / 'ios-native-ui.json'
            with self.assertRaises(ValueError):
                ui_tools.verify_report(actual, 'ios', validated)
            self.assertFalse(validated.exists())
            self.assertEqual(json.loads((logs / 'ios-native-ui-cached.json').read_text()), rejected)
            self.assertEqual((logs / 'ios-native-ui-error.txt').read_text(), error.read_text())
            self.assertNotIn('iphone', (logs / 'ios-native-ui-error.txt').read_text())

    def test_diagnostics_use_the_failed_device_and_capture_before_relaunch(self):
        import os
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                Path('logs').mkdir()
                Path('logs/ios-native-ui-device.json').write_text(json.dumps(dict(
                    device='failed-ipad', started_ns=123)))
                events = []
                def capture(device, started, **kwargs):
                    events.append(('capture', device, started))
                def run(command, **kwargs):
                    events.append(('command', command))
                    return SimpleNamespace(stdout=b'', stderr=b'')
                with patch.object(ui_tools, 'simulator_report', side_effect=capture), \
                        patch.object(ui_tools, 'ios_device', side_effect=AssertionError('Wrong-device fallback')), \
                        patch.object(ui_tools.subprocess, 'run', side_effect=run), \
                        patch.object(ui_tools.Path, 'home', return_value=Path(directory)):
                    ui_tools.ios_diagnostics()
                self.assertEqual(events[0], ('capture', 'failed-ipad', 123))
                self.assertEqual(events[1][1][3], 'failed-ipad')
                self.assertIn('failed-ipad', events[2][1])
            finally:
                os.chdir(previous)

    def test_unresponsive_simulator_does_not_suppress_host_diagnostics(self):
        import os
        from unittest.mock import patch
        with TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                Path('logs').mkdir()
                Path('logs/ios-native-ui-owned.json').write_text(json.dumps(dict(device='boot-stalled')))
                commands = []
                def run(command, **kwargs):
                    commands.append(command)
                    if 'spawn' in command or 'launch' in command:
                        raise subprocess.TimeoutExpired(command, 60)
                    if command[0] == 'ps':
                        return SimpleNamespace(stdout='123 1 S 0 2048 Simulator\n', stderr='')
                    kwargs['stdout'].write('host evidence\n')
                    return SimpleNamespace(returncode=0)
                with patch.object(ui_tools.subprocess, 'run', side_effect=run), \
                        patch.object(ui_tools.Path, 'home', return_value=Path(directory)):
                    ui_tools.ios_diagnostics()
                self.assertIn('timed out', Path('logs/ios-system.log').read_text())
                self.assertIn('timed out', Path('logs/ios-launch.result').read_text())
                for name in ('host-memory.txt', 'host-vm.txt', 'host-webkit-processes.txt'):
                    self.assertTrue((Path('logs') / name).read_text())
                self.assertEqual(commands[0][3], 'boot-stalled')
            finally:
                os.chdir(previous)

    def test_process_failures_without_verified_result_still_fail(self):
        import os
        from unittest.mock import patch
        with TemporaryDirectory() as directory, patch.object(ui_tools.subprocess, 'Popen') as process:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                for code in (1, 200, -15):
                    process.return_value.wait.return_value = code
                    with patch.object(ui_tools, 'simulator_report', return_value=None):
                        with self.assertRaises(RuntimeError):
                            ui_tools.run('ios', 'device')
            finally:
                os.chdir(previous)

    def test_successful_native_reports_do_not_hide_unhandled_errors(self):
        import os
        from unittest.mock import patch
        markers = ('Error in handler: fixture', 'Error in handler cleanup: fixture',
                   'Error in async handler: fixture', 'Error in async handler cleanup: fixture',
                   'Task exception was never retrieved', 'Task was destroyed but it is pending',
                   'Exception in callback fixture')
        with TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                for target, transport in (('ios', 'stdout'), ('ios', 'simulator-file'), ('android', 'stdout')):
                    for marker in markers:
                        with self.subTest(target=target, transport=transport, marker=marker):
                            report = self.report()
                            report.update(target=target, backend='toga_iOS.app' if target == 'ios' else 'toga_android.app')
                            def launch(command, *, stdout, **kwargs):
                                if transport == 'stdout':
                                    stdout.write(ui_tools.PREFIX + json.dumps(report) + '\n')
                                stdout.write('native-log: ' + marker + '\n')
                                stdout.flush()
                                return SimpleNamespace(wait=lambda **kwargs: 0)
                            with patch.object(ui_tools.subprocess, 'Popen', side_effect=launch), \
                                    patch.object(ui_tools, 'simulator_report', return_value=report), \
                                    patch.object(ui_tools, 'verify_report', return_value=report):
                                with self.assertRaisesRegex(ValueError, 'Unhandled native app error'):
                                    ui_tools.run(target, 'device')
            finally:
                os.chdir(previous)

    def test_failed_stdout_preserves_assertion_without_accepting_failed_exit(self):
        import os
        from unittest.mock import patch
        report = self.report()
        def launch(command, *, stdout, **kwargs):
            stdout.write(ui_tools.PREFIX + json.dumps(report) + '\n')
            stdout.flush()
            return SimpleNamespace(wait=lambda **kwargs: 232)
        with TemporaryDirectory() as directory, patch.object(ui_tools.subprocess, 'Popen', side_effect=launch), \
                patch.object(ui_tools, 'simulator_report', side_effect=AssertionError('No simulator probe needed')):
            previous = Path.cwd()
            os.chdir(directory)
            try:
                for error in ('AssertionError: Previous page overlaps Home indicator', None):
                    report['error'] = error
                    report['success'] = not error
                    with self.assertRaisesRegex(RuntimeError, error or 'process failed after reporting'):
                        ui_tools.run('ios', 'device')
                    saved = json.loads(Path('logs/ios-native-ui-stdout.json').read_text())
                    self.assertEqual(saved['error'], error)
            finally:
                os.chdir(previous)

    def test_complete_stdout_does_not_depend_on_simulator_service(self):
        import os
        from unittest.mock import patch
        report = self.report()
        def revision(args, **kwargs):
            key = 'commonUtils_commit' if 'commonUtils' in args[2] else 'logistics_commit'
            return report['source'][key]
        def launch(command, *, stdout, **kwargs):
            import sys
            self.assertEqual(command[:3], [sys.executable, '-m', 'briefcase'])
            stdout.write(ui_tools.PREFIX + json.dumps(report) + '\n')
            stdout.flush()
            return SimpleNamespace(wait=lambda **kwargs: code)
        with TemporaryDirectory() as directory, patch.object(ui_tools.subprocess, 'Popen', side_effect=launch), \
                patch.object(ui_tools.subprocess, 'check_output', side_effect=revision), \
                patch.object(ui_tools, 'simulator_report', side_effect=AssertionError('Simulator service unavailable')) as cache:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                for code in (0, 200):
                    self.assertEqual(ui_tools.run('ios', 'device'), report)
                    transport = json.loads(Path('logs/ios-report-transport.json').read_text())
                    self.assertEqual(transport['transport'], 'stdout')
                    self.assertEqual(transport['briefcase_exit_code'], code)
                cache.assert_not_called()
            finally:
                os.chdir(previous)

    def test_failed_structured_stdout_cannot_fall_back_to_successful_cache(self):
        import os
        from unittest.mock import patch
        report = self.report()
        def revision(args, **kwargs):
            key = 'commonUtils_commit' if 'commonUtils' in args[2] else 'logistics_commit'
            return report['source'][key]
        def launch(command, *, stdout, **kwargs):
            stdout.write(ui_tools.PREFIX + json.dumps(emitted) + '\n')
            stdout.flush()
            return SimpleNamespace(wait=lambda **kwargs: 0)
        with TemporaryDirectory() as directory, patch.object(ui_tools.subprocess, 'Popen', side_effect=launch), \
                patch.object(ui_tools.subprocess, 'check_output', side_effect=revision), \
                patch.object(ui_tools, 'simulator_report', return_value=report) as cache:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                for emitted in (dict(report, success=False), dict(report, cases=[]),
                                dict(report, source=dict(report['source'], logistics_commit='0' * 40))):
                    with self.assertRaises(ValueError):
                        ui_tools.run('ios', 'device')
                cache.assert_not_called()
                self.assertFalse(Path('logs/ios-native-ui.json').exists())
            finally:
                os.chdir(previous)


    def test_android_reuse_rejects_normal_apps_and_mismatched_payloads(self):
        import io
        import os
        import zipfile
        with TemporaryDirectory() as directory:
            previous=Path.cwd();os.chdir(directory)
            try:
                apk=Path('build/logisticsmobile/android/gradle/app/build/outputs/apk/debug/app-debug.apk')
                apk.parent.mkdir(parents=True);Path('payload').mkdir()
                source={'dirty':True,'source_sha256':'a'*64}
                Path('payload/source.json').write_text(json.dumps(source))
                def package(tests):
                    stream=io.BytesIO()
                    with zipfile.ZipFile(stream,'w') as application:
                        application.writestr('mobile/source.json',json.dumps(source))
                        if tests:application.writestr('tests/logisticsmobile/__main__.pyc',b'synthetic test bytecode')
                    with zipfile.ZipFile(apk,'w') as archive:archive.writestr('assets/chaquopy/app.imy',stream.getvalue())
                package(False)
                with self.assertRaisesRegex(ValueError,'matching native test'):ui_tools.verify_prebuilt_android()
                package(True);ui_tools.verify_prebuilt_android()
                Path('payload/source.json').write_text(json.dumps(dict(source,source_sha256='b'*64)))
                with self.assertRaisesRegex(ValueError,'matching native test'):ui_tools.verify_prebuilt_android()
            finally:os.chdir(previous)

    def test_local_ios_cached_app_requires_exact_dirty_manifest(self):
        import os
        from unittest.mock import patch
        source=dict(self.report()['source'],dirty=True,source_sha256='c'*64)
        def revision(argv, **kwargs):
            return source['commonUtils_commit' if 'commonUtils' in argv[2] else 'logistics_commit']
        with TemporaryDirectory() as directory, patch.object(ui_tools.subprocess,'check_output',side_effect=revision):
            previous=Path.cwd();os.chdir(directory)
            try:
                project=Path('build/logisticsmobile/ios/xcode');app=project/'build/Debug-iphonesimulator/Logistics Mobile.app'
                (app/'app/mobile').mkdir(parents=True);(app/'Logistics Mobile').write_bytes(b'synthetic')
                (project/'briefcase.toml').write_text('[briefcase]\n');(app/'Info.plist').write_bytes(plistlib.dumps(dict(MainModule='tests.logisticsmobile')))
                Path('payload').mkdir();Path('payload/source.json').write_text(json.dumps(source))
                manifest=app/'app/mobile/source.json';manifest.write_text(json.dumps(source))
                with self.assertRaisesRegex(ValueError,'different source'):ui_tools.verify_prebuilt_ios()
                ui_tools.verify_prebuilt_ios(local=True)
                manifest.write_text(json.dumps(dict(source,source_sha256='d'*64)))
                with self.assertRaisesRegex(ValueError,'different source'):ui_tools.verify_prebuilt_ios(local=True)
            finally:os.chdir(previous)

    def test_local_checkpoints_are_streamed_from_a_real_child_log(self):
        from contextlib import redirect_stdout
        import io
        import sys
        import time
        from threading import Event,Thread
        with TemporaryDirectory() as directory:
            path=Path(directory)/'native.log';path.touch();stopped=Event();output=io.StringIO()
            worker=Thread(target=ui_tools._progress,args=(path,stopped))
            section=json.dumps(dict(name='rotation-panel',details={'panel':'synthetic'},elapsed_s=1.25))
            code='print("LOGISTICS_NATIVE_CASE=synthetic-native");print('+repr('LOGISTICS_NATIVE_TIMING='+section)+')'
            with redirect_stdout(output):
                worker.start()
                try:
                    with path.open('w') as stream:subprocess.run([sys.executable,'-c',code],stdout=stream,check=True,timeout=10)
                    deadline=time.monotonic()+2
                    while 'Native section:' not in output.getvalue() and time.monotonic()<deadline:time.sleep(.01)
                finally:stopped.set();worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
            self.assertIn('Native checkpoint: synthetic-native',output.getvalue())
            self.assertIn('Native section: rotation-panel',output.getvalue())
            self.assertIn('1.25s',output.getvalue())

    def test_failed_local_launch_stops_its_progress_reader(self):
        import os
        from threading import Event
        from unittest.mock import patch
        retired=Event();original=ui_tools._progress
        def progress(path,stopped):
            try:original(path,stopped)
            finally:retired.set()
        with TemporaryDirectory() as directory:
            previous=Path.cwd();os.chdir(directory)
            try:
                with patch.object(ui_tools,'_progress',side_effect=progress), patch.object(ui_tools.subprocess,'Popen',side_effect=OSError('synthetic missing tool')):
                    with self.assertRaisesRegex(OSError,'synthetic missing tool'):ui_tools.run('ios','synthetic',local=True)
                self.assertTrue(retired.is_set())
            finally:os.chdir(previous)
