"""Execute the actual selection gesture handlers with a synthetic DOM in V8."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION


class SelectionGestureTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required for the V8 selection gesture driver')
    def test_production_selection_handlers(self):
        driver = Path(__file__).with_name('selection_work_logic.js')
        result = subprocess.run(['node', str(driver)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['passed'])
