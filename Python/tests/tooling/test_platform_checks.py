"""Native-check supervision retains output and retires timed-out descendants."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from logistics_build.platform_checks import run_check


class PlatformCheckTests(unittest.TestCase):
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
