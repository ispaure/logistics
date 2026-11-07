"""Canvas header layout and legacy dispatcher contracts; no native hardware claim."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import sys
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION


class NativeDrawingToolsJavascriptTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required for production drawing-tool checks')
    def test_original_handlers_state_ink_guards_and_idle_only_lease_restore(self):
        result = subprocess.run(['node', str(Path(__file__).with_name('native_drawing_tools_logic.js'))],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('state and lease restoration PASS', result.stdout)


class CanvasHeaderTests(unittest.TestCase):
    def test_canvas_filename_controls_and_library_panels_at_phone_duo_tablet_sizes(self):
        root = Path(__file__).resolve().parents[3]
        output = root / 'test-results/notebook-canvas-header'
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('notebook_mobile_ui_probe.py')),
                                 '--header-only', '--output', str(output)], capture_output=True, text=True,
                                timeout=90, env=dict(os.environ, QT_QPA_PLATFORM='offscreen',
                                    QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu', QT_QUICK_BACKEND='software'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
