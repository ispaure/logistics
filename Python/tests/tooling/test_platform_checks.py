"""Native-check supervision retains output and retires timed-out descendants."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
import json
import os
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from logistics_build.platform_checks import run_check


class PlatformCheckTests(unittest.TestCase):
    def test_admission_failure_keeps_diagnostic_without_claiming_child_execution(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            marker = root / 'started'
            command = [sys.executable, '-c', f'from pathlib import Path; Path({str(marker)!r}).touch()']
            with patch('build_manager.test_workers.admitted_environment',
                       side_effect=ValueError('Worker limits changed; prepare a new plan.')):
                row = run_check('rejected', command, root=root, results=root,
                                environment={}, timeout=10)
            self.assertEqual(row['status'], 'failed')
            self.assertNotEqual(row['exit_code'], 0)
            self.assertFalse(marker.exists())
            self.assertIn('Worker limits changed', (root / 'rejected.log').read_text())

    def test_native_check_admits_reviewed_shared_runner_through_host_budget(self):
        from build_manager import resources, test_workers
        with TemporaryDirectory() as folder, patch.object(sys, 'platform', 'darwin'):
            root = Path(folder)
            runner = root / 'Python/tests'
            runner.mkdir(parents=True)
            (runner / 'parallel_regressions.py').write_text(
                "SUPPORTED_WORKERS = (1, 2, 4, 8)\n"
                "RESERVATION_ENV = 'BUILD_MANAGER_RESERVED_TEST_WORKERS'\n"
                "QT_GROUPS = {'Python/commonUtils/tests/index': ('test_fixture.py',)}\n")
            (runner / 'run_regressions.py').write_text(
                'import json, os, sys\nfrom pathlib import Path\n'
                'config = {key: os.environ.get(key) for key in '
                '("BUILD_MANAGER_RESERVED_TEST_WORKERS", "BUILD_MANAGER_TEST_PLATFORM")}\n'
                'print(json.dumps(config))\n'
                'Path(sys.argv[sys.argv.index("--junit")+1]).write_text('
                '\'<testsuite><testcase name="passed"/></testsuite>\')\n'
                'Path(sys.argv[sys.argv.index("--report")+1]).write_text(json.dumps(config))\n')
            private = root / 'manager'
            with patch.object(test_workers, 'config_directory', return_value=private), \
                    patch.object(resources, 'config_directory', return_value=private), \
                    patch.dict(os.environ, GITHUB_ACTIONS='', LOGISTICS_REUSE_TEST_RESULTS='off'):
                test_workers.configure(dict(per_platform=2, host=2))
                row = run_check('shared', [sys.executable, 'Python/tests/run_regressions.py',
                    'Python/commonUtils/tests', '--isolate-modules'], root=root, results=root / 'results',
                    environment={'QT_QPA_PLATFORM': 'offscreen'}, timeout=10)
            self.assertEqual(row['status'], 'passed', row)
            data = json.loads((root / 'results/shared.log').read_text().strip())
            self.assertEqual(data, dict(BUILD_MANAGER_RESERVED_TEST_WORKERS='2', BUILD_MANAGER_TEST_PLATFORM='macos'))
            report = json.loads((Path(row['execution']) / 'result.json').read_text())
            junit, timing = report['phases'][0]['artifacts']
            self.assertEqual((junit['kind'], timing['kind']), ('junit', 'json'))
            self.assertEqual(json.loads(Path(timing['path']).read_text()), data)

    def test_success_retains_unicode_log_and_actual_outcome(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            row = run_check('fixture',[sys.executable,'-c',"print('native — ü')"], root=root,
                            results=root, environment={'PYTHONUTF8':'1'}, timeout=10)
            self.assertEqual(row['status'],'passed')
            self.assertEqual(row['exit_code'],0)
            self.assertIn('native — ü',(root/'fixture.log').read_text(encoding='utf-8'))

    def test_timeout_stops_descendant_before_late_publication(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            late = root/'late'
            child = 'import time;from pathlib import Path;time.sleep(2);Path('+repr(str(late))+').write_text("escaped")'
            parent = 'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",'+repr(child)+']);print("started",flush=True);time.sleep(30)'
            row = run_check('timeout',[sys.executable,'-c',parent],root=root,results=root,
                            environment={},timeout=.3)
            self.assertEqual(row['status'],'timeout', (row, (root/'timeout.log').read_text()))
            self.assertEqual(row['exit_code'],124)
            time.sleep(2.1)
            self.assertFalse(late.exists())
            self.assertIn('started',(root/'timeout.log').read_text())
