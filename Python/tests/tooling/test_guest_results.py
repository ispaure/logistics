"""Collect evidence before conditional cleanup on either guest backend."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from Scripts.guest_results import GuestResultLifecycle


class GuestResultTests(unittest.TestCase):
    def test_collection_failure_preserves_remote_workspace(self):
        with TemporaryDirectory() as folder:
            result = dict(source={'commit': 'fixed'}, status='passed')
            lifecycle = GuestResultLifecycle(result, folder, 'fixture', 'guest_workspace')
            cleanup = Mock()
            lifecycle.collect(Mock(side_effect=OSError('transfer lost')), Path(folder) / 'missing', cleanup)
            cleanup.assert_not_called()
            self.assertEqual(result['status'], 'failed')
            self.assertTrue(result['guest_workspace_preserved_for_recovery'])
            lifecycle.finish()
            self.assertEqual(json.loads((Path(folder) / 'result.json').read_text())['retrieval_error'], 'transfer lost')

    def test_collected_invalid_report_is_retained_and_remote_copy_cleaned(self):
        with TemporaryDirectory() as folder:
            evidence = Path(folder) / 'guest.json'
            evidence.write_text(json.dumps(dict(source={'commit': 'other'}, backend='fixture', phases=[])))
            result = dict(source={'commit': 'fixed'}, status='passed')
            cleanup = Mock()
            lifecycle = GuestResultLifecycle(result, folder, 'fixture', 'test_workspace')
            lifecycle.collect(Mock(), evidence, cleanup)
            cleanup.assert_called_once()
            self.assertTrue(evidence.exists())
            self.assertTrue(result['test_workspace_removed'])
            self.assertEqual(result['status'], 'failed')

    def test_cleanup_failure_and_cancelled_outcome_remain_explicit(self):
        for status, cleanup_error in (('cancelled', None), ('passed', OSError('cleanup denied'))):
            with self.subTest(status=status), TemporaryDirectory() as folder:
                evidence = Path(folder) / 'guest.json'
                evidence.write_text(json.dumps(dict(source={'commit': 'fixed'}, backend='fixture',
                                                    status=status, phases=[dict(id='one', status=status)])))
                result = dict(source={'commit': 'fixed'}, status=status)
                lifecycle = GuestResultLifecycle(result, folder, 'fixture', 'test_workspace')
                lifecycle.collect(Mock(), evidence, Mock(side_effect=cleanup_error))
                self.assertEqual(result['phases'][0]['status'], status)
                self.assertEqual(result['status'], 'failed' if cleanup_error else status)
                self.assertEqual('cleanup_error' in result, bool(cleanup_error))

    def test_passing_exit_requires_matching_passing_evidence(self):
        for report in (None, dict(source={'commit': 'fixed'}, backend='fixture', status='failed', phases=[])):
            with self.subTest(report=report), TemporaryDirectory() as folder:
                evidence = Path(folder) / 'guest.json'
                if report:
                    evidence.write_text(json.dumps(report))
                result = dict(source={'commit': 'fixed'}, status='passed')
                lifecycle = GuestResultLifecycle(result, folder, 'fixture', 'guest_workspace')
                lifecycle.collect(Mock(), evidence, Mock())
                self.assertEqual(result['status'], 'failed')
                self.assertIn('retrieval_error', result)
