"""Run mobile core fixtures in a fresh interpreter that rejects desktop imports."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


class MobilePortabilityTests(unittest.TestCase):
    def test_headless_mobile_core_and_document_fixtures(self):
        root = Path(__file__).resolve().parents[2]
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(root / 'Python'), str(root / 'Python/tests'))))
        completed = subprocess.run([sys.executable, '-m', 'logisticsmobile.smoke', '--target', 'host'],
                                   cwd=root, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        line = next(line for line in completed.stdout.splitlines() if line.startswith('LOGISTICS_MOBILE_RESULT='))
        report = json.loads(line.split('=', 1)[1])
        self.assertEqual(report['environment'], 'desktop-harness')
        self.assertEqual(report['tests_run'], 14)
        self.assertTrue(report['success'])
        self.assertEqual(report['skipped'], 0)
