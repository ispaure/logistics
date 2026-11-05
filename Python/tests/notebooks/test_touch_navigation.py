"""Production canvas gesture arbitration without a GUI backend."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION


class TouchNavigationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required for the V8 touch navigation driver')
    def test_production_touch_navigation(self):
        driver = Path(__file__).with_name('touch_navigation_logic.js')
        result = subprocess.run(['node', str(driver)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['success'])

    @unittest.skipUnless(shutil.which('node'), 'Node is required for the V8 zoom visibility driver')
    def test_production_mobile_zoom_visibility(self):
        driver = Path(__file__).with_name('zoom_visibility_logic.js')
        result = subprocess.run(['node', str(driver)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['success'])
