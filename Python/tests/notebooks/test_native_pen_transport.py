"""Production native-pen JS routing and explicit pressure choice; no hardware claim."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
import shutil
import subprocess
import unittest


class NativePenTransportTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required for production native-pen transport checks')
    def test_twenty_packets_retirement_and_pressure_choice(self):
        result = subprocess.run(['node', str(Path(__file__).with_name('native_pen_transport_logic.js'))],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"paired_packets":40', result.stdout)
        self.assertIn('"default_event_force_preserved":true', result.stdout)
        self.assertIn('"failed_save_nonerror_ack_dispatches_preserved_stroke":true', result.stdout)
