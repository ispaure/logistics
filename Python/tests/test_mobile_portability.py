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
        try:
            completed = subprocess.run([sys.executable, '-m', 'mobile.smoke', '--target', 'host'],
                                       cwd=root, env=env, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired as error:
            self.fail(f'Mobile harness timed out. stdout={error.stdout!r}; stderr={error.stderr!r}')
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        line = next(line for line in completed.stdout.splitlines() if line.startswith('LOGISTICS_MOBILE_RESULT='))
        report = json.loads(line.split('=', 1)[1])
        self.assertEqual(report['environment'], 'desktop-harness')
        self.assertEqual(report['tests_run'], len(report['expected_tests']))
        self.assertTrue(report['success'])
        self.assertEqual(report['skipped'], 0)


    def test_local_mobile_source_mode_never_relaxes_clean_default_or_runtime_identity(self):
        from mobile.smoke import verify_source
        source={'dirty':True,'source_sha256':'c'*64}
        with self.assertRaisesRegex(RuntimeError,'clean staged'):verify_source(source,'android')
        verify_source(source,'android','c'*64)
        with self.assertRaisesRegex(RuntimeError,'fingerprint differs'):verify_source(source,'android','d'*64)
        with self.assertRaises(ValueError):verify_source(source,'host','c'*64)
        verify_source(dict(source,dirty=False),'android')
