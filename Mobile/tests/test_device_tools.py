"""Protect identity and physical-device gates used by local deployment."""
import copy
import shlex
import unittest

from Mobile.cloud_build import ios_compiler
from Mobile.device_tools import BUNDLE, normal_launcher, select_device, signing_settings


class DeviceDeploymentTests(unittest.TestCase):
    def project(self):
        return {'objects': {name: {'isa': 'XCBuildConfiguration', 'buildSettings': {
            'PRODUCT_BUNDLE_IDENTIFIER': BUNDLE,
            'OTHER_LDFLAGS[sdk=iphoneos*]': ['native-bridge'],
        }} for name in ('debug', 'release')}}

    def test_sdk_path_with_spaces_survives_go_compiler_argument_parsing(self):
        sdk = '/Applications/Xcode 27.1.app/Contents/Developer/SDKs/iPhoneOS.sdk'
        target = 'arm64-apple-ios15.0'
        self.assertEqual(shlex.split(ios_compiler(target, sdk)),
                         ['clang', '-target', target, '-isysroot', sdk])

    def test_signing_preserves_bundle_and_native_linker_settings(self):
        data = signing_settings(self.project(), 'ABCDEFGHIJ')
        for obj in data['objects'].values():
            settings = obj['buildSettings']
            self.assertEqual(settings['PRODUCT_BUNDLE_IDENTIFIER'], BUNDLE)
            self.assertEqual(settings['DEVELOPMENT_TEAM'], 'ABCDEFGHIJ')
            self.assertEqual(settings['OTHER_LDFLAGS[sdk=iphoneos*]'], ['native-bridge'])
        self.assertEqual(signing_settings(copy.deepcopy(data), 'ABCDEFGHIJ'), data)
        with self.assertRaises(RuntimeError):
            signing_settings(data, 'OTHERTEAM1X')

    def test_changed_bundle_or_project_layout_is_rejected(self):
        data = self.project()
        data['objects']['debug']['buildSettings']['PRODUCT_BUNDLE_IDENTIFIER'] += '.test'
        with self.assertRaises(RuntimeError):
            signing_settings(data, 'ABCDEFGHIJ')
        with self.assertRaises(RuntimeError):
            signing_settings({'objects': {}}, 'ABCDEFGHIJ')

    def test_normal_launcher_preserves_identity_version_and_permissions(self):
        info = {'CFBundleIdentifier': BUNDLE, 'MainModule': 'tests.logisticsmobile',
                'CFBundleVersion': '0.1.5', 'NSLocalNetworkUsageDescription': 'LM server'}
        self.assertEqual(normal_launcher(info), dict(info, MainModule='logisticsmobile'))
        with self.assertRaises(RuntimeError):
            normal_launcher({'CFBundleIdentifier': 'other.app'})

    def test_only_paired_physical_iphone_is_selected_with_current_or_legacy_fields(self):
        phone = {'identifier': 'core-device-id', 'properties': {
            'hardware': {'reality': 'physical', 'deviceType': 'iPhone', 'udid': 'phone-udid'},
            'connection': {'pairingState': 'paired', 'transportType': 'localNetwork'}}}
        simulator = copy.deepcopy(phone)
        simulator['properties']['hardware']['reality'] = 'simulated'
        self.assertEqual(select_device([simulator, phone], 'phone-udid')[1], 'phone-udid')
        legacy = {'identifier': 'legacy-id', 'hardwareProperties': phone['properties']['hardware'],
                  'connectionProperties': phone['properties']['connection']}
        self.assertEqual(select_device([legacy])[1], 'phone-udid')
        with self.assertRaises(RuntimeError):
            select_device([simulator])
        with self.assertRaises(RuntimeError):
            select_device([phone, legacy])
        phone['properties']['connection']['pairingState'] = 'unpaired'
        with self.assertRaises(RuntimeError):
            select_device([phone])


if __name__ == '__main__':
    unittest.main()
