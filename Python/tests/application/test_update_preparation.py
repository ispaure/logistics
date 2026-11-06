"""Exercise update preparation with synthetic releases and local staging."""

import json
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from services import updates


TEST_STAGE = TestStage.REGRESSION


class UpdatePreparationTests(TestCase):
    def setUp(self):
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.root = folder / 'installed'
        self.root.mkdir()
        self.installed_file = self.root / 'application.txt'
        self.installed_file.write_text('installed', encoding='utf-8')
        self.addCleanup(self.assert_installed_unchanged)
        self.state_root = folder / 'state'
        self.available = {'branch': 'main', 'commit': 'a' * 40}
        self.choice = self.enterContext(patch.object(
            updates, 'choice', return_value=updates.UpdateChoice(True, 'main')))
        self.source = self.enterContext(patch.object(updates, 'source'))
        self.snapshot = self.source.return_value.release_snapshot

    def assert_installed_unchanged(self):
        self.assertEqual(list(self.root.iterdir()), [self.installed_file])
        self.assertEqual(self.installed_file.read_text(encoding='utf-8'), 'installed')

    def prepare(self):
        return updates.prepare(self.available, root=self.root, state_root=self.state_root)

    def test_successful_cleanup_reraises_original_exception(self):
        primary = ValueError('snapshot rejected')
        self.snapshot.side_effect = primary

        with self.assertRaises(ValueError) as caught:
            self.prepare()

        self.assertIs(caught.exception, primary)
        self.assertEqual(list(self.state_root.iterdir()), [])

    def test_cleanup_failure_reports_both_errors_and_owned_workspace(self):
        primary = ValueError('snapshot rejected')
        cleanup = PermissionError('staging access denied')
        self.snapshot.side_effect = primary

        with patch.object(updates.shutil, 'rmtree', side_effect=cleanup) as remove:
            with self.assertRaises(RuntimeError) as caught:
                self.prepare()

        workspace = self.snapshot.call_args.args[1]
        remove.assert_called_once_with(workspace)
        self.assertEqual(list(self.state_root.iterdir()), [workspace])
        self.assertIs(caught.exception.__cause__, primary)
        for detail in ('cleanup could not complete', str(primary), str(cleanup), str(workspace)):
            self.assertIn(detail, str(caught.exception))

    def test_cleanup_failure_preserves_control_flow_and_adds_note(self):
        for primary in (KeyboardInterrupt(), SystemExit(2)):
            with self.subTest(type=type(primary).__name__):
                cleanup = PermissionError('staging access denied')
                self.snapshot.side_effect = primary

                with patch.object(updates.shutil, 'rmtree', side_effect=cleanup) as remove:
                    with self.assertRaises(type(primary)) as caught:
                        self.prepare()

                workspace = self.snapshot.call_args.args[1]
                remove.assert_called_once_with(workspace)
                self.assertTrue(workspace.is_dir())
                self.assertIs(caught.exception, primary)
                self.assertIsNone(primary.__cause__)
                self.assertEqual(len(primary.__notes__), 1)
                self.assertIn(str(cleanup), primary.__notes__[0])
                self.assertIn(str(workspace), primary.__notes__[0])

    def test_success_retains_request_format_and_staging(self):
        plan = {'kind': 'test plan'}
        with patch.object(updates, 'prepare_archive', return_value=plan) as prepare_archive:
            request = self.prepare()

        workspace = request.parent
        self.snapshot.assert_called_once_with(self.available, workspace)
        prepare_archive.assert_called_once_with(
            self.root, self.snapshot.return_value, self.available['commit'], updates.PROTECTED)
        self.assertEqual(request, workspace / 'request.json')
        self.assertEqual(workspace.parent, self.state_root)
        self.assertTrue((workspace / 'apply_update.py').is_file())
        self.assertEqual(json.loads(request.read_text(encoding='utf-8')), {
            'pid': os.getpid(),
            'plan': plan,
            'restart': updates.restart_command(self.root),
            'status': str(self.state_root / 'last-result.json'),
        })
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(request.stat().st_mode), 0o600)

    def test_preference_veto_happens_before_workspace_allocation(self):
        for choice in (updates.UpdateChoice(False, 'main'), updates.UpdateChoice(True, 'beta')):
            with self.subTest(choice=choice):
                self.choice.return_value = choice
                with self.assertRaisesRegex(ValueError, 'Update preferences changed'):
                    self.prepare()

                self.assertFalse(self.state_root.exists())
                self.source.assert_not_called()
