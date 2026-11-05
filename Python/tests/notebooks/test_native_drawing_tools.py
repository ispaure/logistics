"""Production native drawing dispatcher/lease; no native hardware claim."""
from pathlib import Path
import shutil
import subprocess
import unittest
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION


class NativeDrawingToolsJavascriptTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required for production drawing-tool checks')
    def test_original_handlers_state_ink_guards_and_idle_only_lease_restore(self):
        result = subprocess.run(['node', str(Path(__file__).with_name('native_drawing_tools_logic.js'))],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('state and lease restoration PASS', result.stdout)
