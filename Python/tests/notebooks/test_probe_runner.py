"""Probe selection preserves core gates and schedules the previously manual checks."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from tests.notebooks import notebook_platform_probe as runner

TEST_STAGE = TestStage.REGRESSION


class NotebookProbeRunnerTests(unittest.TestCase):
    def run_probe(self, output, **options):
        self.commands = []

        def execute(argv, **kwargs):
            self.commands.append((argv, kwargs))
            if any(str(arg).endswith('notebook_acceptance_probe.py') for arg in argv):
                destination = Path(argv[argv.index('--output') + 1])
                destination.mkdir(parents=True)
                for name in ('acceptance.rmdoc', 'modern.rmdoc'):
                    (destination / name).write_bytes(b'fixture handoff')
            return SimpleNamespace(returncode=0)

        with patch.object(runner.platform, 'system', return_value='Darwin'), \
                patch.object(runner.subprocess, 'run', side_effect=execute):
            code = runner.main(output, **options)
        return code, json.loads((output / 'native-result.json').read_text())

    def test_default_preserves_the_five_core_gates(self):
        with TemporaryDirectory() as directory:
            code, result = self.run_probe(Path(directory))
        self.assertEqual(code, 0)
        self.assertEqual([row['name'] for row in result['checks']], list(runner.CORE_PROBES))
        stress = self.commands[0][0]
        self.assertEqual(stress[stress.index('--latency-mode') + 1], 'enforce')

    def test_full_matrix_runs_storage_once_and_hands_archives_to_codec(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            compiler = root / 'go'
            compiler.touch()
            code, result = self.run_probe(root / 'reports', profile='full', rendering='all', go=compiler,
                                          latency_mode='diagnostic', max_process_tree_mib=2048,
                                          max_remount_growth_mib=128)
        self.assertEqual(code, 0)
        for name, (_, _, renderer_sensitive) in runner.PROBES.items():
            self.assertEqual(sum(row['name'] == name for row in result['checks']),
                             3 if renderer_sensitive else 1, name)
        codec, = [argv for argv, _ in self.commands if any(str(arg).endswith('independent_codec_probe.py') for arg in argv)]
        self.assertEqual(codec.count('--archive'), 2)
        memory = self.commands[1][0]
        self.assertEqual(memory[memory.index('--max-remount-growth-mib') + 1], '128')
        laptop, = [argv for argv, _ in self.commands if '--laptop-only' in argv][:1]
        self.assertIn('notebook_mobile_ui_probe.py', Path(laptop[1]).name)

    def test_unknown_selection_cannot_report_a_vacuous_pass(self):
        with TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, 'known'):
            runner.main(Path(directory), probes=['missing'])

    def test_failure_is_retained_while_remaining_selected_probes_run(self):
        with TemporaryDirectory() as directory, \
                patch.object(runner.platform, 'system', return_value='Darwin'), \
                patch.object(runner.subprocess, 'run', side_effect=[SimpleNamespace(returncode=1),
                                                                  SimpleNamespace(returncode=0)]):
            output = Path(directory)
            self.assertEqual(runner.main(output, probes=['templates', 'mobile-ui']), 1)
            result = json.loads((output / 'native-result.json').read_text())
            self.assertEqual([row['status'] for row in result['checks']], ['failed', 'passed'])
