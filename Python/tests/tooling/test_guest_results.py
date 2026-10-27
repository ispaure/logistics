"""Collect evidence before conditional cleanup on either guest backend."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from Scripts.guest_results import GuestResultLifecycle


class GuestResultTests(unittest.TestCase):
    def test_interrupted_wrapper_retains_ownership_before_guest_work(self):
        with TemporaryDirectory() as folder:
            result = dict(source={'commit': 'fixed'}, status='running', vm='owned-vm',
                          workspace='/var/tmp/owned-token', workspace_token='owned-token',
                          operation='exact-worker')
            GuestResultLifecycle(result, folder, 'fixture', 'guest_workspace')
            # Simulate abrupt wrapper termination: neither collect nor finish runs.
            saved = json.loads((Path(folder) / 'result.json').read_text())
            self.assertEqual(saved, result)
            self.assertEqual(saved['status'], 'running')
            self.assertNotIn('guest_workspace_removed', saved)

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


    def test_headless_wait_labels_advisory_state_without_inventing_test_results(self):
        from contextlib import redirect_stdout
        import io
        from Scripts.guest_results import waiting_progress
        output = io.StringIO()
        with redirect_stdout(output):
            progress = waiting_progress('Windows', 'selected checks')
            progress(dict(state='waiting', seconds=30))
            progress(dict(state='reconciling', seconds=31))
        text = output.getvalue()
        self.assertIn('waiting for worker result', text)
        self.assertIn('reconciling worker receipt', text)
        self.assertIn('30s (headless)', text)
        self.assertNotIn('passed', text)
