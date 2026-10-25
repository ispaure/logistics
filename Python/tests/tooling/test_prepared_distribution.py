"""Exact review and interrupted-attempt guards; no provider request is sent."""
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from Scripts.distribute_prepared import reviewed,distribute


class PreparedDistributionTests(unittest.TestCase):
    def test_unreviewed_report_never_executes_provider(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'report.json';path.write_text('{}')
            with patch.dict(os.environ,{},clear=True),patch('Scripts.distribute_prepared.subprocess.run') as run:
                with self.assertRaisesRegex(ValueError,'review'):distribute(path,Path(directory)/'receipt.json')
            run.assert_not_called()

    def test_interrupted_attempt_is_not_blindly_repeated(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);report=root/'prepared.json';receipt=root/'receipt.json'
            data=dict(provider='TestFlight',workspace=str(root),release=dict(source=dict(dirty=False),build=dict(build_number='7')),destination={'group':'synthetic'})
            report.write_text(json.dumps(data))
            approval=[dict(original_path=str(report.resolve()),sha256=hashlib.sha256(report.read_bytes()).hexdigest())]
            env=dict(BUILD_MANAGER_APPROVED_PLAN='synthetic-plan',BUILD_MANAGER_APPROVED_ARTIFACTS=json.dumps(approval))
            with patch.dict(os.environ,env),patch('Scripts.distribute_prepared.subprocess.run',side_effect=ConnectionError('synthetic lost supervision')) as run:
                with self.assertRaises(ConnectionError):distribute(report,receipt)
                with self.assertRaisesRegex(ValueError,'Reconcile'):distribute(report,receipt)
                self.assertEqual(run.call_count,1)
            self.assertEqual(json.loads(receipt.with_suffix('.attempt.json').read_text())['status'],'unknown until reconciled')
