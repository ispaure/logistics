"""QA acceptance cannot install a main/release APK or target a physical device."""
from commonUtils.testing.stages import TestStage
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mobile_build.validation import document_storage_tools as tools

TEST_STAGE = TestStage.REGRESSION


class MobileFeedbackToolsTests(unittest.TestCase):
    def test_ios_runtime_on_android_is_rejected_before_qa_staging(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / 'evidence'
            argv = ['document_storage_tools', 'android', '--ios-runtime',
                    'com.apple.CoreSimulator.SimRuntime.iOS-27-1', '--output', str(output)]
            with patch.object(tools.sys, 'argv', argv), \
                    patch.object(tools.sys, 'stderr', new_callable=StringIO) as error_output, \
                    patch.object(tools, 'stage') as stage:
                with self.assertRaises(SystemExit) as error:
                    tools.main()
                self.assertEqual(error.exception.code, 2)
                self.assertIn('--ios-runtime requires iOS', error_output.getvalue())
                stage.assert_not_called()
                self.assertFalse(output.exists())

    def test_wrong_package_and_non_debug_apks_are_rejected_before_device_creation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for metadata in (
                    "package: name='io.github.ispaure.logisticsmobile'\napplication-debuggable\n",
                    "package: name='io.github.ispaure.logisticsstorageqa'\n"):
                with self.subTest(metadata=metadata), \
                        patch('mobile_build.deployment.android_deploy.build_tools', return_value=root), \
                        patch.object(tools.subprocess, 'check_output', return_value=metadata), \
                        patch.object(tools, 'AndroidEmulator') as emulator:
                    with self.assertRaisesRegex(ValueError, 'Debug build.*isolated QA'):
                        tools.exercise_android_app(root / 'input.apk', root, root / 'evidence', {}, {})
                    emulator.assert_not_called()

    def test_mobile_feedback_rejects_explicit_android_device_before_staging(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / 'evidence'
            argv = ['document_storage_tools', 'android', '--probe', 'mobile-feedback',
                    '--device', 'physical-device', '--output', str(output)]
            with patch.object(tools.sys, 'argv', argv), patch.object(tools, 'stage') as stage:
                with self.assertRaises(SystemExit) as error:
                    tools.main()
                self.assertEqual(error.exception.code, 2)
                stage.assert_not_called()
                self.assertFalse(output.exists())
