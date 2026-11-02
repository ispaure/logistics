"""Archive restaging must test current code rather than stale compiled payloads."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from hashlib import sha1
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from mobile_build.validation.video_probe_tools import prepare


class VideoProbeRestagingTests(unittest.TestCase):
    def test_release_apk_is_rejected_before_staging_or_starting_an_emulator(self):
        from mobile_build.validation.video_probe_tools import run
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('mobile_build.validation.video_probe_tools.deployment_environment', return_value={}), \
                    patch('mobile_build.validation.video_probe_tools.tools_environment', return_value=({}, None)), \
                    patch('mobile_build.validation.video_probe_tools.build_tools', return_value=root), \
                    patch('mobile_build.validation.video_probe_tools.subprocess.check_output', return_value=b'package: release\n'), \
                    patch('mobile_build.validation.video_probe_tools.prepare') as stage, \
                    patch('mobile_build.validation.video_probe_tools.AndroidEmulator') as emulator:
                with self.assertRaisesRegex(ValueError, 'Debug APK'):
                    run(root / 'release.apk', root / 'evidence')
                stage.assert_not_called()
                emulator.assert_not_called()

    def test_cloud_probe_replaces_old_feature_bytecode_and_keeps_native_binary(self):
        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            contents = BytesIO()
            with ZipFile(contents, 'w') as app:
                for name in ('features/media/playback.pyc', 'features/video/playback.pyc',
                             'logisticsmobile/__main__.pyc', 'tests/logisticsmobile/__main__.pyc'):
                    app.writestr(name, b'stale payload')
            original = workspace / 'base.apk'
            with ZipFile(original, 'w') as apk:
                apk.writestr('assets/chaquopy/app.imy', contents.getvalue())
                apk.writestr('assets/chaquopy/build.json', json.dumps(dict(assets={'app.imy': 'old'})))
                apk.writestr('classes.dex', b'Lio/github/ispaure/logistics/video/VideoPlayer$Listener;')
                apk.writestr('lib/arm64-v8a/libvlc.so', b'unchanged native decoder')
            fixture = workspace / 'fixtures'
            fixture.mkdir()
            (fixture / 'sentinel.mp4').write_bytes(b'fixture')

            def stage(root, destination, **options):
                (destination / 'features/video').mkdir(parents=True)
                (destination / 'features/video/playback.py').write_text('CURRENT = True\n')
                (destination / 'logisticsmobile').mkdir()
                (destination / 'logisticsmobile/__main__.py').write_text('production entrypoint')
                (destination / 'source.json').write_text('{"fingerprint": "current"}')

            with patch('mobile_build.validation.video_probe_tools.stage', side_effect=stage), patch(
                    'mobile_build.validation.video_probe_tools.cloud_fixtures', return_value=fixture) as publish:
                tool = workspace / 'reviewed-rclone'
                unsigned = prepare(original, workspace, cloud=True, rclone=tool)
                publish.assert_called_once_with(workspace, rclone=tool)
            with ZipFile(unsigned) as apk:
                self.assertEqual(apk.read('lib/arm64-v8a/libvlc.so'), b'unchanged native decoder')
                raw = apk.read('assets/chaquopy/app.imy')
                self.assertEqual(json.loads(apk.read('assets/chaquopy/build.json'))['assets']['app.imy'], sha1(raw).hexdigest())
                self.assertNotIn('lib/arm64-v8a/wrap.sh', apk.namelist())
                with ZipFile(BytesIO(raw)) as app:
                    self.assertEqual(app.read('features/video/playback.py'), b'CURRENT = True\n')
                    self.assertNotIn('features/media/playback.pyc', app.namelist())
                    self.assertNotIn('features/video/playback.pyc', app.namelist())
                    self.assertNotIn('logisticsmobile/__main__.pyc', app.namelist())
                    self.assertIn(b'video_cloud_probe', app.read('logisticsmobile/__main__.py'))
                    self.assertIn('tests/logisticsmobile/video_webdav.py', app.namelist())


class PhysicalHDRReportTests(unittest.TestCase):
    def test_failed_or_incomplete_device_evidence_is_not_success(self):
        from mobile_build.validation.video_hdr_device_tools import require_hdr_success
        transitions = [{'event': event} for event in ['playing', 'paused', 'resumed'] * 2]
        valid = dict(success=True, hdrActiveObserved=True, hdrTransitions=transitions)
        require_hdr_success(valid)
        for changes in (dict(success=False, error='metadata lost'),
                        dict(hdrActiveObserved=False),
                        dict(hdrTransitions=[]),
                        dict(hdrTransitions=transitions[:-1])):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                require_hdr_success(dict(valid, **changes))

    def test_cleanup_failures_still_restore_normal_app(self):
        import subprocess
        from unittest.mock import Mock
        from mobile_build.validation.video_hdr_device_tools import restore_after_probe
        success = subprocess.CompletedProcess(['device'], 0, 'ok', '')
        failed = subprocess.CompletedProcess(['device'], 1, '', 'cleanup failed')
        for failure in (subprocess.TimeoutExpired('cleanup', 180), OSError('disconnected'), failed):
            with self.subTest(failure=failure), TemporaryDirectory() as directory:
                output = Path(directory)
                command = Mock(side_effect=[failure, success])
                with self.assertRaisesRegex(RuntimeError, 'Normal app restored'):
                    restore_after_probe(command, Path('Normal.app'), 'bundle', 'QA-cache', output, 'device')
                self.assertEqual(command.call_args_list[-1].args, ('install', 'app', Path('Normal.app')))
                evidence = json.loads((output / 'cleanup.json').read_text())
                self.assertTrue(evidence['app_restored'])
                self.assertFalse(evidence['cache_cleanup_requested'])
                self.assertTrue(evidence['cleanup_error'])

    def test_restoration_failure_is_recorded_and_propagated(self):
        import subprocess
        from unittest.mock import Mock
        from mobile_build.validation.video_hdr_device_tools import restore_after_probe
        success = subprocess.CompletedProcess(['device'], 0, 'ok', '')
        for failure in (subprocess.TimeoutExpired('restore', 180),
                        subprocess.CompletedProcess(['device'], 1, '', 'restore failed')):
            with self.subTest(failure=failure), TemporaryDirectory() as directory:
                output = Path(directory)
                with self.assertRaises(subprocess.SubprocessError):
                    restore_after_probe(Mock(side_effect=[success, failure]), Path('Normal.app'),
                                        'bundle', 'QA-cache', output, 'device')
                evidence = json.loads((output / 'cleanup.json').read_text())
                self.assertFalse(evidence['app_restored'])
                self.assertTrue(evidence['cache_cleanup_requested'])
                self.assertTrue(evidence['restore_error'])

    def test_successful_cleanup_and_restoration(self):
        import subprocess
        from unittest.mock import Mock
        from mobile_build.validation.video_hdr_device_tools import restore_after_probe
        success = subprocess.CompletedProcess(['device'], 0, 'ok', '')
        with TemporaryDirectory() as directory:
            output = Path(directory)
            restore_after_probe(Mock(return_value=success), Path('Normal.app'),
                                'bundle', 'QA-cache', output, 'device')
            evidence = json.loads((output / 'cleanup.json').read_text())
            self.assertTrue(evidence['app_restored'])
            self.assertTrue(evidence['cache_cleanup_requested'])

    def test_interrupt_during_cleanup_still_attempts_restoration(self):
        import subprocess
        from unittest.mock import Mock
        from mobile_build.validation.video_hdr_device_tools import restore_after_probe
        success = subprocess.CompletedProcess(['device'], 0, 'ok', '')
        with TemporaryDirectory() as directory:
            output = Path(directory)
            command = Mock(side_effect=[KeyboardInterrupt(), success])
            with self.assertRaises(KeyboardInterrupt):
                restore_after_probe(command, Path('Normal.app'), 'bundle', 'QA-cache', output, 'device')
            self.assertEqual(command.call_args_list[-1].args, ('install', 'app', Path('Normal.app')))
            self.assertTrue(json.loads((output / 'cleanup.json').read_text())['app_restored'])
