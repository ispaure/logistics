"""UI evidence verifier contracts; these fixtures are not native device evidence."""
import base64
import importlib.util
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('mobile_ui_tools', REPO / 'Mobile/ui_tools.py')
ui_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui_tools)


class NativeReportTests(unittest.TestCase):
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
            for changes in (dict(cases=[]), dict(success=False), dict(backend='toga_dummy.app'),
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
