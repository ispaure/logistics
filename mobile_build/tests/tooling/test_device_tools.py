"""Protect identity and physical-device gates used by local deployment."""
import copy
import json
import plistlib
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from mobile_build.deployment import device_tools
from mobile_build.cloud_build import ios_compiler
from mobile_build.deployment.device_tools import BUNDLE, normal_launcher, select_device, signing_settings


class DeviceDeploymentTests(unittest.TestCase):
    def test_refresh_updates_dependencies_in_existing_projects(self):
        for existing in (False, True):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'build').mkdir()
                pbx = root / 'project.pbxproj'
                if existing:
                    pbx.touch()
                def stage_payload(repo, replacement, **kwargs):
                    replacement.mkdir()
                with (patch.object(device_tools, 'ROOT', root),
                      patch.object(device_tools, 'PBX', pbx),
                      patch.object(device_tools, 'stage', side_effect=stage_payload),
                      patch.object(device_tools, 'run') as run):
                    device_tools.refresh_sources({})
                command = run.call_args_list[1].args[0]
                self.assertEqual(command[3:5], ['update' if existing else 'create', 'iOS'])
                self.assertEqual('--update-requirements' in command, existing)

    def test_existing_project_receives_new_ios_sharing_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'pyproject.toml'
            config.write_text('[tool.briefcase]\nversion="0.1.9"\n'
                              '[tool.briefcase.app.logisticsmobile]\nbuild="202610242"\n'
                              '[tool.briefcase.app.logisticsmobile.iOS.info]\n'
                              'CFBundleDisplayName = "Logisticks"\nCFBundleName = "Logisticks"\n'
                              'UIFileSharingEnabled = true\nLSSupportsOpeningDocumentsInPlace = true\n')
            pbx, info = root / 'project.pbxproj', root / 'Info.plist'
            info.write_bytes(plistlib.dumps({'CFBundleIdentifier': BUNDLE, 'MainModule': 'tests.logisticsmobile',
                                            'CFBundleShortVersionString': '0.1.8', 'CFBundleVersion': '202610239'}))
            with (patch.object(device_tools, 'ROOT', root), patch.object(device_tools, 'PBX', pbx),
                  patch.object(device_tools, 'INFO', info),
                  patch('subprocess.check_output', return_value=json.dumps(self.project()).encode())):
                device_tools.prepare_project('ABCDEFGHIJ')
                result = plistlib.loads(info.read_bytes())
                self.assertEqual(result['CFBundleDisplayName'], 'Logisticks')
                self.assertEqual(result['CFBundleName'], 'Logisticks')
                self.assertEqual(result['CFBundleIdentifier'], BUNDLE)
                self.assertIs(result['UIFileSharingEnabled'], True)
                self.assertIs(result['LSSupportsOpeningDocumentsInPlace'], True)
                self.assertEqual(result['MainModule'], 'logisticsmobile')
                self.assertEqual(result['CFBundleShortVersionString'], '0.1.9')
                self.assertEqual(result['CFBundleVersion'], '202610242')
                device_tools.prepare_project('ABCDEFGHIJ')
                self.assertEqual(plistlib.loads(info.read_bytes()), result)

    def test_stale_built_versions_are_rejected_before_device_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            (app / 'Info.plist').write_bytes(plistlib.dumps({
                'CFBundleIdentifier': BUNDLE, 'MainModule': 'logisticsmobile',
                'CFBundleShortVersionString': '0.1.8', 'CFBundleVersion': '202610239'}))
            with (patch.object(device_tools, 'configured_ios_info', return_value={
                    'CFBundleShortVersionString': '0.1.9', 'CFBundleVersion': '202610242'}),
                  patch('subprocess.check_output') as signing):
                with self.assertRaisesRegex(RuntimeError, 'configured iOS plist settings'):
                    device_tools.validate_app(app, 'ABCDEFGHIJ', 'phone')
                signing.assert_not_called()

    def test_batch_deploy_uses_saved_targets_and_continues_after_failure(self):
        config = {'device_id': 'phone', 'device_ids': ['phone', 'tablet', 'phone']}
        with patch.object(device_tools, 'run', side_effect=[subprocess.CalledProcessError(1, 'deploy'), None]) as run:
            with self.assertRaisesRegex(RuntimeError, 'Deployment failed for: phone'):
                device_tools.deploy_all(config, allow_wired=True)
        self.assertEqual(run.call_count, 2)
        self.assertEqual([call.args[0][-3:] for call in run.call_args_list],
                         [['--device', 'phone', '--allow-wired'], ['--device', 'tablet', '--allow-wired']])

    def test_batch_deploy_legacy_default_and_invalid_saved_lists(self):
        with patch.object(device_tools, 'run') as run:
            device_tools.deploy_all({'device_id': 'phone'})
            self.assertEqual(run.call_args.args[0][-2:], ['--device', 'phone'])
            for targets in ([], 'phone', [''], [None], ['--other']):
                with self.assertRaises(RuntimeError):
                    device_tools.deploy_all({'device_id': 'phone', 'device_ids': targets})

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

    def test_share_extension_uses_same_pinned_team_without_changing_identity(self):
        data = self.project()
        for name in ('debug', 'release'):
            data['objects']['inbox-' + name] = {'isa':'XCBuildConfiguration',
                'buildSettings':{'PRODUCT_BUNDLE_IDENTIFIER':BUNDLE + '.inbox'}}
        signing_settings(data, 'ABCDEFGHIJ')
        for name in ('debug', 'release'):
            self.assertEqual(data['objects']['inbox-' + name]['buildSettings']['DEVELOPMENT_TEAM'], 'ABCDEFGHIJ')

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

    def test_ipad_selection_with_phone_present_and_simulator_rejected(self):
        def device(kind, udid, reality='physical'):
            return {'identifier': udid, 'hardwareProperties': {
                'reality': reality, 'deviceType': kind, 'udid': udid},
                'deviceProperties': {'name': kind},
                'connectionProperties': {'pairingState': 'paired'}}
        phone = device('iPhone', 'phone')
        ipad = device('iPad', 'tablet')
        simulator = device('iPad', 'simulator', 'simulated')
        devices = [phone, ipad, simulator]
        self.assertEqual(select_device(devices, 'iPad')[1], 'tablet')
        self.assertEqual(select_device(devices, 'phone')[1], 'phone')
        with self.assertRaises(RuntimeError):
            select_device(devices)
        with self.assertRaises(RuntimeError):
            select_device(devices, 'simulator')

    def test_ipad_build_provisions_selected_device_and_preserves_default_and_identity(self):
        ipad = {'identifier': 'tablet', 'hardwareProperties': {
            'reality': 'physical', 'deviceType': 'iPad', 'udid': 'tablet-udid'},
            'connectionProperties': {'pairingState': 'paired'}}
        identity = {'application_identifier': 'ABCDEFGHIJ.' + BUNDLE}
        config = dict(bundle_id=BUNDLE, team_id='ABCDEFGHIJ', device_id='phone-udid',
                      signing_identity=identity)
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / '.device.json'
            config_path.write_text(json.dumps(config))
            with (patch.object(device_tools, 'CONFIG', config_path),
                  patch.object(device_tools, 'ROOT', Path(temporary)),
                  patch.object(device_tools, 'installed', return_value=[]),
                  patch.object(device_tools, 'choose', return_value=('/Xcode', '27.1')),
                  patch.object(device_tools, 'device_json', return_value={'devices': [ipad]}),
                  patch.object(device_tools, 'refresh_sources'),
                  patch.object(device_tools, 'prepare_project'),
                  patch.object(device_tools, 'run') as run,
                  patch.object(device_tools, 'validate_app', return_value=identity) as validate,
                  patch('sys.argv', ['device_tools.py', 'build', '--device', 'tablet'])):
                device_tools.main()
                command = run.call_args.args[0]
                self.assertEqual(command[command.index('-destination') + 1], 'id=tablet-udid')
                validate.assert_called_once_with(device_tools.APP, 'ABCDEFGHIJ', 'tablet-udid')
                self.assertEqual(json.loads(config_path.read_text()), config)


if __name__ == '__main__':
    unittest.main()
