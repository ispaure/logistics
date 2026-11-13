"""QA acceptance cannot install a main/release APK or target a physical device."""
from commonUtils.testing.stages import TestStage
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch

from mobile_build.validation import document_storage_tools as tools

TEST_STAGE = TestStage.REGRESSION


class MobileFeedbackToolsTests(unittest.TestCase):
    def test_comic_packaged_launch_completes_real_host_startup(self):
        import toga
        from commonUtils.testing.event_loop import close_loop
        from mobile_build.native_tests.tests.logisticsmobile.comic_guidance_probe import ComicGuidanceProbe
        with TemporaryDirectory() as directory, \
                patch.dict(os.environ, {'TOGA_DUMMY_HOME': directory}), \
                patch.object(toga.App, 'app', toga.App.app):
            try:
                # Same entry-point contract emitted by copy_payload. Use the
                # real app/startup and only replace the native platform backend.
                exec('from mobile_build.native_tests.tests.logisticsmobile.comic_guidance_probe import main\n'
                     'main().main_loop()', {})
                app = toga.App.app
                self.assertIsInstance(app, ComicGuidanceProbe)
                self.assertFalse(app._startup_in_progress)
                self.assertTrue(app.active_host)
                self.assertIsNotNone(app.main_window.content)
                app.checkpoint()
            finally:
                app = toga.App.app
                if isinstance(app, ComicGuidanceProbe):
                    app.main_window.close()
                    close_loop(app.loop)

    def test_comic_probe_only_overrides_intended_host_hooks(self):
        from mobile.app import LogisticsMobile
        from mobile_build.native_tests.tests.logisticsmobile.comic_guidance_probe import ComicGuidanceProbe
        inherited = {name for base in LogisticsMobile.__mro__ for name in vars(base)}
        defined = {name for name in vars(ComicGuidanceProbe) if not name.startswith('__')}
        self.assertEqual(inherited & defined, {'startup', 'on_running'})
        self.assertIs(ComicGuidanceProbe.checkpoint, LogisticsMobile.checkpoint)

    def test_comic_probe_returns_app_for_the_packaged_main_loop(self):
        from mobile_build.native_tests.tests.logisticsmobile import comic_guidance_probe
        with patch.object(comic_guidance_probe, 'ComicGuidanceProbe') as factory:
            self.assertIs(comic_guidance_probe.main(), factory.return_value)
            factory.assert_called_once_with('Comic Guidance QA', 'io.github.ispaure.logisticscomicqa')
            factory.return_value.main_loop.assert_not_called()

    def test_comic_driver_waits_for_missing_or_partial_requests(self):
        for raw in (b'', b'cat: cache/comic-guidance-request.json: No such file or directory\n',
                    b'run-as: package is not running\n', b'{"action":', b'\xff'):
            for android in (False, True):
                with self.subTest(raw=raw, android=android):
                    self.assertIsNone(tools.comic_guidance_action(raw, android=android))

    def test_comic_driver_accepts_only_supported_platform_actions(self):
        for android in (False, True):
            self.assertEqual(tools.comic_guidance_action(b'{"action":"background"}', android=android),
                             'background')
        for action in ('reduce-motion-on', 'reduce-motion-off'):
            raw = tools.json.dumps(dict(action=action)).encode()
            self.assertEqual(tools.comic_guidance_action(raw, android=True), action)
            with self.assertRaises(ValueError):
                tools.comic_guidance_action(raw)
        for raw in (b'[]', b'null', b'{}', b'{"action":12}', b'{"action":"install"}'):
            for android in (False, True):
                with self.subTest(raw=raw, android=android), self.assertRaises(ValueError):
                    tools.comic_guidance_action(raw, android=android)

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
