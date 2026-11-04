"""Memory accounting includes renderer descendants without unrelated processes."""
import unittest
from unittest.mock import patch
from commonUtils.testing.stages import TestStage
from tests.notebooks.process_memory import tree_memory, process_tree_memory

TEST_STAGE = TestStage.REGRESSION


class ProbeMemoryTests(unittest.TestCase):
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
