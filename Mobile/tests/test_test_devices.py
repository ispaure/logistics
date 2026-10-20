"""Device batching must avoid duplicate updates, rebuilds and identity changes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Mobile import test_devices as devices
from Mobile import firebase_deploy as firebase, testflight_deploy as testflight


class TestDeviceDeployment(unittest.TestCase):
    def test_single_android_target_excludes_other_platform_and_devices(self):
        targets = [dict(platform='Android', id='s8', name='S8+', connection='usb', online=True),
                   dict(platform='Android', id='boox', name='Boox', connection='wifi', online=True),
                   dict(platform='iOS', id='s8', name='iPhone', online=True)]
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(devices, 'WORKSPACES', Path(directory)), \
                patch.object(devices, 'run_platform') as run:
            devices.deploy_devices(targets, target=('Android', 's8'))
        run.assert_called_once_with('Android', [targets[0]])

    def test_single_ios_target_never_builds_android(self):
        targets = [dict(platform='iOS', id='phone', name='iPhone', online=True),
                   dict(platform='iOS', id='tablet', name='iPad', online=True),
                   dict(platform='Android', id='boox', name='Boox', online=True)]
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(devices, 'WORKSPACES', Path(directory)), \
                patch.object(devices, 'run_platform') as run:
            devices.deploy_devices(targets, target=('iOS', 'phone'))
        run.assert_called_once_with('iOS', [targets[0]])

    def test_unavailable_selected_device_never_falls_back(self):
        for selected in ([], [dict(platform='Android', id='s8', online=False)]):
            targets = selected + [dict(platform='iOS', id='phone', online=True)]
            with patch.object(devices.android, 'deploy') as build, patch.object(devices.subprocess, 'run') as ios:
                with self.assertRaisesRegex(ValueError, 'Selected device is unavailable'):
                    devices.deploy_devices(targets, target=('Android', 's8'))
            build.assert_not_called()
            ios.assert_not_called()

    def test_testflight_gui_waits_for_verified_build_and_decline_never_uploads(self):
        with patch.object(testflight.sys, 'argv', ['testflight', '--gui', '--build-number', '202610201']), \
                patch.object(testflight, 'gui_input', return_value='n') as ask, \
                patch.object(testflight.subprocess, 'run') as run:
            testflight.main()
        ask.assert_called_once()
        self.assertEqual([call.args[0][2] for call in run.call_args_list], ['plan', 'archive', 'export'])

    def test_firebase_gui_decline_does_not_distribute(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(firebase, 'PRIVATE', Path(directory)), \
                patch.object(firebase.sys, 'argv', ['firebase', '--gui']), \
                patch.object(firebase, 'firebase_cli', return_value='firebase'), \
                patch.object(firebase, 'preflight', return_value=({'app_id': 'test'}, 'friends')) as preflight, \
                patch.object(firebase, 'build', return_value=(Path('beta.apk'), Path('notes.txt'))), \
                patch.object(firebase, 'gui_input', return_value='n') as ask, \
                patch.object(firebase.subprocess, 'run') as run:
            firebase.main()
        preflight.assert_called_once_with('firebase', login=False, allow_login=False)
        ask.assert_called_once()
        run.assert_not_called()

    def test_android_deduplicates_usb_and_wireless_by_hardware_id(self):
        def run(command, env):
            if command[-1] == 'devices':
                return 'List of devices attached\nwireless:123\tdevice\nusb\tdevice\nblocked\tunauthorized\n'
            return 'hardware' if command[-1] == 'ro.serialno' else 'Galaxy S8+'
        with patch.object(devices.android, 'tools_environment', return_value=({}, Path('/adb'))), \
                patch.object(devices.android, 'discover_wireless'), \
                patch.object(devices.android, 'run', side_effect=run):
            result = devices.android_devices()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['connection'], 'usb')

    def test_worker_builds_android_once_and_continues_after_install_failure(self):
        targets = [dict(platform='Android', name=n, connection=n, online=True) for n in ('boox', 's8')]
        targets += [dict(platform='iOS', name='phone', id='udid', online=True),
                    dict(platform='Android', name='offline', online=False)]
        with patch.object(devices.android, 'deploy') as build, \
                patch.object(devices.android, 'tools_environment', return_value=({}, '/adb')), \
                patch.object(devices.android, 'install_apk', side_effect=[ValueError('signature mismatch'), None]) as install, \
                patch.object(devices.subprocess, 'run') as ios:
            with self.assertRaisesRegex(RuntimeError, 'boox'):
                devices.deploy_platform([d for d in targets if d['online']])
        build.assert_called_once_with(build_only=True)
        self.assertEqual(install.call_count, 2)
        self.assertEqual(ios.call_args.args[0][-3:], ['--device', 'udid', '--allow-wired'])

    def test_no_devices_fails_before_build(self):
        with patch.object(devices.android, 'deploy') as build:
            with self.assertRaisesRegex(ValueError, 'No test devices'):
                devices.deploy_devices([])
        build.assert_not_called()

    def test_registry_retains_offline_android_and_reports_discovery_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / 'devices.json'
            registry.write_text(json.dumps([dict(platform='Android', id='s8', name='Galaxy S8+', online=True)]))
            with patch.object(devices, 'REGISTRY', registry), \
                    patch.object(devices.android, 'deployment_environment', return_value={}), \
                    patch.object(devices, 'android_devices', side_effect=ValueError('ADB unavailable')), \
                    patch.object(devices, 'ios_devices', return_value=[]), \
                    patch.object(devices.ios, 'CONFIG', Path(directory) / 'absent'):
                result, errors = devices.inventory()
            self.assertFalse(result[0]['online'])
            self.assertIn('ADB unavailable', errors[0])


if __name__ == '__main__':
    unittest.main()
