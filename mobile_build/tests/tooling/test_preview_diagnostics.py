"""The failure probe records evidence and cleans up without changing acceptance."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from mobile_build.native_tests.tests.logisticsmobile import preview_diagnostics as diagnostic


class PreviewDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_host_copies_only_current_preview_diagnostics(self):
        import os
        from mobile_build.validation import ui_tools
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / 'Library/Caches'
            cache.mkdir(parents=True)
            evidence = cache / 'logistics-preview-diagnostics.json'
            evidence.write_text('{"probes": []}')
            logs = root / 'logs'
            with patch.object(ui_tools.subprocess, 'run', return_value=SimpleNamespace(
                    returncode=0, stdout=str(root))):
                self.assertIsNone(ui_tools.simulator_report('fixture-device', 1, diagnostics=logs))
                self.assertEqual((logs / 'ios-preview-diagnostics.json').read_text(), evidence.read_text())
                os.utime(evidence, ns=(0, 0))
                ui_tools.simulator_report('fixture-device', 1, diagnostics=logs)
            self.assertFalse((logs / 'ios-preview-diagnostics.json').exists())

    async def test_fresh_views_are_removed_on_success_and_failure(self):
        parent = Mock()
        original = SimpleNamespace(parent=parent)
        probes = [Mock(), Mock()]
        with TemporaryDirectory() as directory:
            app = SimpleNamespace(paths=SimpleNamespace(cache=Path(directory)))
            with patch('toga.WebView', side_effect=probes), \
                    patch.object(diagnostic, 'native_state', return_value=dict(loading=True)), \
                    patch.object(diagnostic, 'wait_for_text', new=AsyncMock(
                        side_effect=[None, RuntimeError('synthetic load stall')])), \
                    patch('services.documents.mobile_views.retire_webview') as retire:
                await diagnostic.diagnose_preview(app, original)
            report = json.loads((Path(directory) / 'logistics-preview-diagnostics.json').read_text())
        self.assertEqual([row['rendered'] for row in report['probes']], [True, False])
        self.assertEqual(report['probes'][1]['error'], 'synthetic load stall')
        self.assertEqual(parent.add.call_count, 2)
        self.assertEqual(parent.remove.call_count, 2)
        self.assertEqual(retire.call_count, 2)
        self.assertIs(original.parent, parent)
        self.assertNotIn('success', report)

    async def test_missing_parent_retains_diagnostic_error(self):
        with TemporaryDirectory() as directory:
            app = SimpleNamespace(paths=SimpleNamespace(cache=Path(directory)))
            with patch.object(diagnostic, 'native_state', return_value={}):
                await diagnostic.diagnose_preview(app, SimpleNamespace(parent=None))
            report = json.loads((Path(directory) / 'logistics-preview-diagnostics.json').read_text())
        self.assertIn('no parent', report['diagnostic_error'])
        self.assertEqual(report['probes'], [])
