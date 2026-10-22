from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from mobile_build import testflight_deploy as launcher


class TestFlightLauncherTests(unittest.TestCase):
    def test_next_build_exceeds_existing_workspaces(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'build/testflight/299912319').mkdir(parents=True)
            self.assertEqual(launcher.next_build(root), '299912320')

    def test_upload_only_after_successful_export_and_explicit_yes(self):
        with patch.object(launcher.subprocess, 'run') as run:
            launcher.deploy('202610151', ask=lambda prompt: 'y')
        self.assertEqual([call.args[0][2] for call in run.call_args_list], ['plan', 'archive', 'export', 'upload'])
        self.assertEqual(run.call_args.kwargs['env']['TESTFLIGHT_UPLOAD'], '1')

    def test_default_answer_does_not_upload(self):
        with patch.object(launcher.subprocess, 'run') as run:
            launcher.deploy('202610151', ask=lambda prompt: '')
        self.assertEqual(run.call_count, 3)

    def test_build_failure_stops_before_prompt_or_upload(self):
        with patch.object(launcher.subprocess, 'run', side_effect=launcher.subprocess.CalledProcessError(1, 'archive')) as run:
            with self.assertRaises(launcher.subprocess.CalledProcessError):
                launcher.deploy('202610151', ask=lambda prompt: self.fail('Unexpected upload prompt'))
        self.assertEqual(run.call_count, 1)
