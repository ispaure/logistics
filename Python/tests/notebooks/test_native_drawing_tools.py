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
        args = [sys.executable, '-u', str(Path(__file__).with_name('notebook_mobile_ui_probe.py')),
                '--header-only', '--output', str(output)]
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen',
                   QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu', QT_QUICK_BACKEND='software')
        if sys.platform == 'linux' and (display := shutil.which('xvfb-run')):
            args = [display, '-a', '--server-args=-screen 0 1440x1000x24', *args]
            env.update(QT_QPA_PLATFORM='xcb', QT_OPENGL='software')
        result = subprocess.run(args, capture_output=True, text=True, timeout=120, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
