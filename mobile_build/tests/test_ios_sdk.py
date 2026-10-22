import unittest
from mobile_build.select_ios_sdk import choose, version


class AppleSDKTests(unittest.TestCase):
    def test_older_build_cannot_claim_duo_opt_in(self):
        with self.assertRaises(RuntimeError):
            choose([('/old', '26.5'), ('/partial', '27.0')])
        self.assertEqual(choose([('/old', '26.5'), ('/duo', '27.1')]), ('/duo', '27.1'))

    def test_sdk_selection_handles_patch_versions_and_invalid_metadata(self):
        self.assertEqual(choose([('/patch', '27.1.1'), ('/duo', '27.1')]), ('/patch', '27.1.1'))
        with self.assertRaises(ValueError):
            version('unknown')


class DuoSimulatorSetupTests(unittest.TestCase):
    def runtime(self, value='27.1', *, duo=True):
        return {'identifier': 'com.apple.CoreSimulator.SimRuntime.iOS-' + value.replace('.', '-'),
                'version': value, 'isAvailable': True,
                'supportedDeviceTypes': [{'identifier': 'com.apple.CoreSimulator.SimDeviceType.' +
                                          ('iPhone-Duo' if duo else 'iPhone-18-Pro')}]}

    def device_types(self):
        return {'devicetypes': [{'identifier': 'com.apple.CoreSimulator.SimDeviceType.iPhone-Duo',
                                'name': 'iPhone Duo'}]}

    def test_existing_duo_is_preserved_without_downloading_or_creating(self):
        from unittest.mock import patch
        from mobile_build.select_ios_sdk import prepare_duo
        data = {'devices': {self.runtime()['identifier']: [dict(udid='existing', state='Booted',
            name='Renamed phone', deviceTypeIdentifier='com.apple.CoreSimulator.SimDeviceType.iPhone-Duo', isAvailable=True)]}}
        with patch('mobile_build.select_ios_sdk.simulator_data', return_value=data), \
                patch('mobile_build.select_ios_sdk.subprocess.run') as download, \
                patch('mobile_build.select_ios_sdk.subprocess.check_output') as create:
            self.assertEqual(prepare_duo('/selected', '27.2'), 'existing')
        download.assert_not_called()
        create.assert_not_called()

    def test_installed_runtime_gets_a_distinct_duo_device(self):
        from unittest.mock import patch
        from mobile_build.select_ios_sdk import prepare_duo
        with patch('mobile_build.select_ios_sdk.simulator_data', side_effect=[
                {'devices': {self.runtime()['identifier']: [dict(name='iPhone Duo', udid='ordinary', state='Shutdown',
                    deviceTypeIdentifier='com.apple.CoreSimulator.SimDeviceType.iPhone-18-Pro', isAvailable=True)]}},
                {'runtimes': [self.runtime(), self.runtime('27.2', duo=False)]}, self.device_types()]), \
                patch('mobile_build.select_ios_sdk.subprocess.run') as download, \
                patch('mobile_build.select_ios_sdk.subprocess.check_output', return_value='created\n') as create:
            self.assertEqual(prepare_duo('/selected', '27.2'), 'created')
        download.assert_not_called()
        self.assertEqual(create.call_args.args[0][-2:], [self.device_types()['devicetypes'][0]['identifier'],
                                                        self.runtime()['identifier']])
        self.assertEqual(create.call_args.kwargs['env']['DEVELOPER_DIR'], '/selected')

    def test_newer_runtime_without_duo_downloads_the_compatible_runtime(self):
        from unittest.mock import patch
        from mobile_build.select_ios_sdk import prepare_duo
        with patch('mobile_build.select_ios_sdk.simulator_data', side_effect=[
                {'devices': {}}, {'runtimes': [self.runtime('27.2', duo=False)]},
                {'runtimes': [self.runtime()]}, self.device_types()]), \
                patch('mobile_build.select_ios_sdk.platform.machine', return_value='arm64'), \
                patch('mobile_build.select_ios_sdk.subprocess.run') as download, \
                patch('mobile_build.select_ios_sdk.subprocess.check_output', return_value='created'):
            self.assertEqual(prepare_duo('/selected', '27.2'), 'created')
        self.assertEqual(download.call_args.args[0], ['xcodebuild', '-downloadPlatform', 'iOS',
            '-buildVersion', '27.1', '-architectureVariant', 'arm64'])
        self.assertEqual(download.call_args.kwargs['env']['DEVELOPER_DIR'], '/selected')

    def test_unavailable_runtime_after_download_fails_without_phone_substitution(self):
        from unittest.mock import patch
        from mobile_build.select_ios_sdk import prepare_duo
        with patch('mobile_build.select_ios_sdk.simulator_data', side_effect=[
                {'devices': {}}, {'runtimes': []}, {'runtimes': []}]), \
                patch('mobile_build.select_ios_sdk.subprocess.run'), \
                patch('mobile_build.select_ios_sdk.subprocess.check_output') as create:
            with self.assertRaisesRegex(RuntimeError, 'Duo-compatible iOS Simulator runtime'):
                prepare_duo('/selected', '27.2')
        create.assert_not_called()

    def test_missing_duo_device_type_fails_explicitly(self):
        from unittest.mock import patch
        from mobile_build.select_ios_sdk import prepare_duo
        with patch('mobile_build.select_ios_sdk.simulator_data', side_effect=[
                {'devices': {}}, {'runtimes': [self.runtime()]}, {'devicetypes': []}]), \
                patch('mobile_build.select_ios_sdk.subprocess.check_output') as create:
            with self.assertRaisesRegex(RuntimeError, 'no iPhone Duo'):
                prepare_duo('/selected', '27.2')
        create.assert_not_called()

    def test_download_failure_is_not_reported_as_coverage(self):
        import subprocess
        from unittest.mock import patch
        from mobile_build.select_ios_sdk import prepare_duo
        with patch('mobile_build.select_ios_sdk.simulator_data', side_effect=[
                {'devices': {}}, {'runtimes': []}]), \
                patch('mobile_build.select_ios_sdk.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'xcodebuild')):
            with self.assertRaises(subprocess.CalledProcessError):
                prepare_duo('/selected', '27.2')
