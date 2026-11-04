"""Failure unwinding must retire archive workers without hiding the assertion."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class ArchiveFailureCleanupTests(unittest.TestCase):
    def test_real_archive_fixtures_preserve_failure_and_retire_workers(self):
        helper = Path(__file__).with_name('archive_failure_cleanup.py')
        with TemporaryDirectory(prefix='logistics-archive-cleanup-') as directory:
            root = Path(directory)
            output = root / 'cleanup.json'
            environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', TMPDIR=str(root),
                               COMMONUTILS_STORAGE_ROOT=str(root / 'storage'),
                               XDG_CONFIG_HOME=str(root / 'config'), XDG_CACHE_HOME=str(root / 'cache'))
            completed = subprocess.run([sys.executable, str(helper), '--output', str(output)],
                                       env=environment, capture_output=True, text=True, timeout=60)
            detail = completed.stdout + completed.stderr
            if output.exists():
                detail += '\n' + output.read_text()
            self.assertEqual(completed.returncode, 0, detail)
            report = json.loads(output.read_text())
            self.cleanup_report = report
            self.assertEqual(report['status'], 'passed', detail)
            self.assertEqual([row['case'] for row in report['cases']], [
                'test_creation_uses_config_and_keeps_source',
                'test_zip_suggests_stem_and_prompts_without_configuration',
                'test_folder_zip_keeps_root_and_uses_config_without_prompt',
            ])
