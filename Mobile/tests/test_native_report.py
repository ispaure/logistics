"""UI evidence verifier contracts; these fixtures are not native device evidence."""
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
