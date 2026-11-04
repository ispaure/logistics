"""Native failures retain actionable diagnostics without granting acceptance."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mobile_build.native_tests.tests.logisticsmobile.__main__ import exception_summary
from mobile_build.validation import ui_tools


class NativeFailureReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / 'android-native-ui.log'
        self.output = self.root / 'android-native-ui.json'
        self.source = dict(logistics_commit='a' * 40, commonUtils_commit='b' * 40,
                           source_sha256='c' * 64, dirty=False)
        def revision(argv, **kwargs):
            key = 'commonUtils_commit' if 'commonUtils' in argv[2] else 'logistics_commit'
            return self.source[key]
        self.revisions = patch.object(ui_tools.subprocess, 'check_output', side_effect=revision)
        self.revisions.start()
        self.addCleanup(self.revisions.stop)

    def report(self, *, success=False, error='AttributeError: native text conversion failed\n\n'):
        cases = list(ui_tools.contract.CASES)
        return dict(schema=1, suite='logistics-native-ui', target='android', backend='toga_android.app',
                    success=success, cases=cases if success else cases[:-1], expected_cases=cases,
                    error=error, source=dict(self.source))

    def write_chunks(self, report):
        encoded = base64.b64encode(json.dumps(report).encode()).decode()
        chunks = [encoded[index:index + 450] for index in range(0, len(encoded), 450)]
        self.path.write_text('\n'.join('I/python.stdout: LOGISTICS_NATIVE_UI_CHUNK=' + json.dumps(dict(
            index=index, count=len(chunks), encoding='base64', data=data))
            for index, data in enumerate(chunks)) + '\n')

    def test_valid_failed_chunks_retain_exact_report_counts_error_and_exit_232(self):
        incoming = self.report()
        self.write_chunks(incoming)
        with self.assertRaises(RuntimeError) as caught:
            ui_tools.collect_android_report(self.path, 232, self.output)
        message = str(caught.exception)
        self.assertIn('failed (232)', message)
        self.assertIn(f"completed {len(incoming['cases'])}/{len(incoming['expected_cases'])} cases", message)
        self.assertIn('AttributeError: native text conversion failed', message)
        self.assertNotIn('LOGISTICS_NATIVE_UI_CHUNK', message)
        self.assertLess(len(message), 1200)
        saved = json.loads((self.root / 'android-native-ui-stdout.json').read_text())
        self.assertEqual(saved, incoming)
        transport = json.loads((self.root / 'android-report-transport.json').read_text())
        self.assertEqual(transport['briefcase_exit_code'], 232)
        self.assertEqual(transport['status'], 'failed')
        self.assertEqual(transport['completed_cases'], len(incoming['cases']))
        self.assertEqual(transport['expected_cases'], len(ui_tools.contract.CASES))
        self.assertEqual(transport['error'], 'AttributeError: native text conversion failed')
        self.assertFalse(self.output.exists())

    def test_legacy_empty_error_is_diagnostic_only_and_zero_exit_cannot_pass_failure(self):
        incoming = self.report(error='')
        self.write_chunks(incoming)
        with self.assertRaisesRegex(RuntimeError, r'failed \(0\).*without an exception summary'):
            ui_tools.collect_android_report(self.path, 0, self.output)
        self.assertEqual(json.loads((self.root / 'android-native-ui-stdout.json').read_text()), incoming)
        with self.assertRaises(ValueError):
            ui_tools.verify_report(incoming, 'android', self.output)
        self.assertFalse(self.output.exists())

    def test_foreign_source_backend_and_invalid_case_prefix_are_rejected(self):
        for kind in ('app-source', 'shared-source', 'backend', 'out-of-order', 'foreign-inventory'):
            with self.subTest(kind=kind):
                incoming = self.report()
                if kind == 'app-source':
                    incoming['source']['logistics_commit'] = 'd' * 40
                elif kind == 'shared-source':
                    incoming['source']['commonUtils_commit'] = 'd' * 40
                elif kind == 'backend':
                    incoming['backend'] = 'toga_iOS.app'
                elif kind == 'out-of-order':
                    incoming['cases'] = list(reversed(incoming['cases']))
                else:
                    incoming['expected_cases'] = ['foreign-case']
                self.write_chunks(incoming)
                with self.assertRaisesRegex(RuntimeError, r'failed \(232\).*report rejected'):
                    ui_tools.collect_android_report(self.path, 232, self.output)
                self.assertFalse((self.root / 'android-native-ui-stdout.json').exists())
                self.assertFalse(self.output.exists())

    def test_invalid_or_missing_chunks_preserve_real_exit_without_dumping_raw_tail(self):
        for content in ('ordinary native crash output\n',
                        'LOGISTICS_NATIVE_UI_CHUNK={"index":1,"count":2,"encoding":"base64","data":"QQ=="}\n',
                        'LOGISTICS_NATIVE_UI_CHUNK={"index":0,"count":1,"encoding":"base64","data":"!invalid!"}\n'):
            with self.subTest(content=content[:50]):
                self.path.write_text(content)
                with self.assertRaisesRegex(RuntimeError, r'failed \(232\).*report unavailable or invalid') as caught:
                    ui_tools.collect_android_report(self.path, 232, self.output)
                self.assertNotIn('LOGISTICS_NATIVE_UI_CHUNK', str(caught.exception))
                self.assertFalse(self.output.exists())

    def test_nonzero_process_exit_never_passes_a_complete_success_report(self):
        self.write_chunks(self.report(success=True, error=''))
        with self.assertRaisesRegex(RuntimeError, r'failed \(232\).*process failed after reporting'):
            ui_tools.collect_android_report(self.path, 232, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(json.loads((self.root / 'android-report-transport.json').read_text())['status'], 'failed')

    def test_full_success_still_requires_exact_inventory_and_writes_acceptance_report(self):
        incoming = self.report(success=True, error='')
        self.write_chunks(incoming)
        self.assertEqual(ui_tools.collect_android_report(self.path, 0, self.output), incoming)
        self.assertEqual(json.loads(self.output.read_text()), incoming)
        self.assertEqual(json.loads((self.root / 'android-report-transport.json').read_text())['status'], 'passed')

    def test_failed_local_report_requires_the_exact_staged_manifest(self):
        incoming = self.report()
        incoming['source']['dirty'] = True
        manifest = self.root / 'source.json'
        manifest.write_text(json.dumps(incoming['source']))
        self.write_chunks(incoming)
        with self.assertRaisesRegex(RuntimeError, r'failed \(232\).*completed'):
            ui_tools.collect_android_report(self.path, 232, self.output, local_manifest=manifest)
        self.assertFalse(self.output.exists())

    def test_exception_summary_uses_last_nonempty_line_and_remains_bounded(self):
        self.assertEqual(exception_summary('Traceback:\nAssertionError: nested traceback\nAttributeError: actual cause\n\n'),
                         'AttributeError: actual cause')
        self.assertEqual(exception_summary(' \n\n'), 'Native check failed without an exception summary.')
        self.assertEqual(len(exception_summary('X' * 1000 + '\n\n')), 600)
