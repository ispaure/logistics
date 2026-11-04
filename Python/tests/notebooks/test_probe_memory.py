"""Memory accounting includes renderer descendants without unrelated processes."""
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from commonUtils.testing.stages import TestStage
from tests.notebooks.process_memory import tree_memory, process_tree_memory, record_sample, finish_report

TEST_STAGE = TestStage.REGRESSION


class ProbeMemoryTests(unittest.TestCase):
    def test_over_budget_sample_remains_in_failure_evidence(self):
        report = {}
        sample = dict(rss_bytes=2 * 1024 ** 2, processes=[dict(pid=7, rss_bytes=2 * 1024 ** 2)])
        with self.assertRaises(AssertionError):
            record_sample(report, sample, 7, limit_mib=1)
        self.assertEqual(report['process_tree_samples'][0]['rss_bytes'], 2 * 1024 ** 2)
        self.assertEqual(report['process_tree_samples'][0]['renderer_pid'], 7)

    def test_missing_renderer_is_rejected_and_counters_are_preserved(self):
        report = {}
        with self.assertRaisesRegex(AssertionError, 'renderer missing'):
            record_sample(report, dict(rss_bytes=100, processes=[dict(pid=1, rss_bytes=100)]), 7)
        self.assertEqual(report['process_tree_samples'][0]['renderer_pid'], 7)

    def test_teardown_failure_still_writes_a_failed_report(self):
        def retire():
            raise TimeoutError('publication pending')
        report = dict(success=True, error='original workload failure')
        with TemporaryDirectory() as directory:
            output = Path(directory) / 'result.json'
            with self.assertRaisesRegex(TimeoutError, 'publication pending'):
                finish_report(output, report, retire)
            written = json.loads(output.read_text())
        self.assertFalse(written['success'])
        self.assertEqual(written['error'], 'original workload failure')
        self.assertIn('publication pending', written['teardown_error'])

    def test_descendants_are_included_once_regardless_of_row_order(self):
        sample = tree_memory([(4, 2, 400), (3, 1, 300), (9, 8, 900),
                              (2, 1, 200), (1, 0, 100)], 1)
        self.assertEqual(sample['rss_bytes'], 1000)
        self.assertEqual([p['pid'] for p in sample['processes']], [1, 2, 3, 4])

    def test_missing_probe_is_a_measurement_failure(self):
        with self.assertRaisesRegex(RuntimeError, 'missing'):
            tree_memory([(2, 1, 200)], 1)

    def test_posix_reads_rss_only_for_the_selected_process_tree(self):
        with patch('tests.notebooks.process_memory.platform.system', return_value='Darwin'), \
                patch('tests.notebooks.process_memory.os.getpid', return_value=1), \
                patch('tests.notebooks.process_memory.subprocess.check_output',
                      side_effect=['1 0\n2 1\n3 2\n9 8\n', '1 100\n2 200\n3 300\n']) as query:
            sample = process_tree_memory()
        self.assertEqual(sample['rss_bytes'], 600 * 1024)
        self.assertEqual(query.call_args_list[0].args[0], ['ps', '-axo', 'pid=,ppid='])
        self.assertEqual(query.call_args_list[1].args[0], ['ps', '-p', '1,2,3', '-o', 'pid=,rss='])
