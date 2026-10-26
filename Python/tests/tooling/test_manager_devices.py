"""Controlled device contracts. No live discovery, native build or installation."""
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, Mock

from commonUtils.runtime.streams import file_sha256
from Scripts import manager_devices as devices
from Scripts.build_project import LogisticsProject
from Scripts.manager_journeys import PlanningContext


class ManagerDeviceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.mobile = self.root / 'mobile_build'
        (self.mobile / '.tools').mkdir(parents=True)
        self.package = self.root / 'app.apk'; self.package.write_bytes(b'synthetic apk')
        self.saved = [dict(platform='Android', id='hardware-1', connection='usb-1', name='Tablet', online=False)]
        (self.mobile / '.tools/test-devices.json').write_text(json.dumps(self.saved))
        (self.mobile / '.device.json').write_text(json.dumps(dict(bundle_id=devices.BUNDLE, team_id='ABCDEFGHIJ', device_id='udid-1', device_ids=['udid-1','udid-2'])))
        self.data = dict(schema=1, platform='android', package=str(self.package), package_sha256=file_sha256(self.package),
            bundle_id=devices.BUNDLE, source={'fingerprint':'source'}, targets=[dict(id='hardware-1', connection='usb-1', name='Tablet')])
        self.report = self.root / 'prepared.json'; self.report.write_text(json.dumps(self.data))
        self.receipt = self.root / 'receipt.json'
        self.env = dict(BUILD_MANAGER_APPROVED_PLAN='plan', BUILD_MANAGER_OPERATION_ID='operation',
            BUILD_MANAGER_APPROVED_ARTIFACTS=json.dumps([dict(original_path=str(self.report.resolve()), sha256=file_sha256(self.report))]))

    def test_saved_metadata_only_no_device_commands_and_nothing_selected_by_default(self):
        with patch('subprocess.run', side_effect=AssertionError('No device commands')), patch('subprocess.check_output', side_effect=AssertionError('No device commands')):
            choices = devices.choices(self.root)
        self.assertEqual([row['id'] for row in choices['devices.android']], ['hardware-1'])
        self.assertEqual([row['id'] for row in choices['devices.ios']], ['udid-1','udid-2'])
        with self.assertRaisesRegex(ValueError, 'Choose at least one'):
            devices.selected_devices(self.root, 'android', {})
        self.assertEqual(devices.selected_devices(self.root, 'android', {'devices.android':'["hardware-1"]'})[0]['connection'], 'usb-1')

    def test_selected_device_requires_review_and_exact_package_and_never_falls_back(self):
        from mobile_build.deployment import android_deploy as android
        with patch.object(android, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'needs manager review'):
                devices.install(self.report, 'hardware-1', self.receipt)
            with patch.dict(os.environ, self.env):
                with self.assertRaisesRegex(ValueError, 'not a reviewed recipient'):
                    devices.install(self.report, 'other-device', self.receipt)
                self.package.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'changed'):
                    devices.install(self.report, 'hardware-1', self.receipt)
            run.assert_not_called()

    def test_install_uses_exact_bytes_on_one_target_and_retains_attempt_receipt(self):
        from mobile_build.deployment import android_deploy as android
        with patch.dict(os.environ, self.env), patch.object(android, 'tools_environment', return_value=({},'/fake/adb')), \
                patch.object(android, 'run', side_effect=['device', 'hardware-1', 'Success']) as run:
            result = devices.install(self.report, 'hardware-1', self.receipt)
            self.assertEqual(result['device'], 'hardware-1')
            self.assertEqual(run.call_args_list[-1].args[0], ['/fake/adb','-s','usb-1','install','-r',str(self.package)])
            self.assertTrue(self.receipt.with_suffix('.attempt.json').exists())
            with self.assertRaisesRegex(ValueError, 'Reconcile'):
                devices.install(self.report, 'hardware-1', self.receipt)
            self.assertEqual(run.call_count, 3)

    def test_offline_and_changed_identity_do_not_install_or_mark_attempt(self):
        from mobile_build.deployment import android_deploy as android
        with patch.dict(os.environ, self.env), patch.object(android, 'tools_environment', return_value=({},'/fake/adb')):
            for responses in (['offline'], ['device','wrong-hardware']):
                with patch.object(android, 'run', side_effect=responses) as run:
                    with self.assertRaises(ValueError):devices.install(self.report, 'hardware-1', self.receipt)
                    self.assertFalse(any('install' in call.args[0] for call in run.call_args_list))
                    self.assertFalse(self.receipt.with_suffix('.attempt.json').exists())

    def test_failed_install_is_never_retried_blindly(self):
        from mobile_build.deployment import android_deploy as android
        with patch.dict(os.environ, self.env), patch.object(android, 'tools_environment', return_value=({},'/fake/adb')), \
                patch.object(android, 'run', side_effect=['device','hardware-1',RuntimeError('Interrupted')]) as run:
            with self.assertRaises(RuntimeError):devices.install(self.report, 'hardware-1', self.receipt)
            self.assertFalse(self.receipt.exists())
            with self.assertRaisesRegex(ValueError, 'Reconcile'):devices.install(self.report, 'hardware-1', self.receipt)
            self.assertEqual(run.call_count,3)

    def test_plan_has_one_preparation_and_individual_reviewed_deploys_and_hash_bound_recipe(self):
        project = LogisticsProject(self.root)
        source = dict(fingerprint='source', dirty=True, effective_settings=dict(values={'tools.mobile_python':sys.executable}))
        context = PlanningContext(str(project.root), 'working-tree', json.dumps(source))
        def snapshot(*args, **kwargs):
            (project.private / 'snapshots/source/mobile_build').mkdir(parents=True)
        with patch('Scripts.build_snapshots.materialize', side_effect=snapshot):
            plan = devices.make_plan(project, 'android', [dict(id='one',name='Phone',connection='one'), dict(id='two',name='Tablet',connection='two')], context,'working-tree')
        self.assertEqual([row.effect for row in plan.phases], ['build','deploy','deploy'])
        self.assertEqual([row.dependencies for row in plan.phases[1:]], [('prepare-device-app',)]*2)
        self.assertIn('--sha256', plan.phases[0].argv)
        self.assertIn('one', plan.phases[1].argv); self.assertNotIn('two', plan.phases[1].argv)
        self.assertEqual(len(plan.phases[0].artifacts), 2)

    def test_source_or_recipe_change_blocks_preparation_before_any_tools(self):
        recipe = self.root / 'recipe.json'; recipe.write_text('{}')
        with patch.object(devices, 'check_source', side_effect=AssertionError('must not reach source')):
            with self.assertRaisesRegex(ValueError, 'recipe changed'):devices.prepare(recipe, 'wrong')

    def test_android_preparation_disables_discovery_and_builds_without_devices(self):
        from mobile_build.deployment import android_deploy as android
        workspace = self.root / 'workspace'; workspace.mkdir()
        apk = self.root / 'gradle/app/build/outputs/apk/debug/app-debug.apk'; apk.parent.mkdir(parents=True); apk.write_bytes(b'build')
        recipe = self.root / 'recipe.json'; recipe.write_text(json.dumps(dict(self.data, workspace=str(workspace), root=str(self.root))))
        with patch.object(devices, 'check_source'), patch.object(android, 'PROJECT', self.root / 'gradle'), patch.object(android, 'deploy') as build:
            devices.prepare(recipe, file_sha256(recipe))
        build.assert_called_once_with(build_only=True, devices=[], discover=False)
        self.assertEqual((workspace / 'app.apk').read_bytes(), b'build')
        self.assertTrue((workspace / 'prepared.json').exists())

    def test_ios_installs_extracted_reviewed_app_on_only_selected_udid_and_cleans_extraction(self):
        from mobile_build.deployment import device_tools as ios
        identity = dict(bundle_id=devices.BUNDLE, team_id='ABCDEFGHIJ')
        config = self.mobile / '.device.json'
        data = dict(self.data, platform='ios', workspace=str(self.root), config=str(config),
                    config_sha256=file_sha256(config), identity=identity,
                    targets=[dict(id='udid-1', connection='udid-1', name='iPhone')])
        self.report.write_text(json.dumps(data)); self.env['BUILD_MANAGER_APPROVED_ARTIFACTS'] = json.dumps([
            dict(original_path=str(self.report.resolve()), sha256=file_sha256(self.report))])
        def extract(command, **kwargs):
            (Path(command[-1]) / 'Logistics Mobile.app').mkdir()
        with patch.dict(os.environ, self.env), patch.object(ios, 'installed', return_value=[]), \
                patch.object(ios, 'choose', return_value=('/fake/xcode','sdk')), \
                patch.object(ios, 'device_json', side_effect=[{'devices':[]}, {'installed':True}]) as native, \
                patch.object(ios, 'select_device', return_value=({},'udid-1',{})), \
                patch.object(ios, 'validate_app', return_value=identity), patch('subprocess.run', side_effect=extract):
            result = devices.install(self.report, 'udid-1', self.receipt)
        self.assertEqual(result['device'], 'udid-1')
        self.assertEqual(native.call_args_list[-1].args[0][:5], ['device','install','app','--device','udid-1'])
        self.assertFalse(list(self.root.glob('install-*')))

    def test_ios_preparation_builds_generic_target_without_contacting_or_registering_devices(self):
        from mobile_build.deployment import device_tools as ios
        workspace = self.root / 'workspace'; workspace.mkdir()
        config = self.mobile / '.device.json'
        data = dict(self.data, platform='ios', root=str(self.root), workspace=str(workspace), config=str(config),
                    config_sha256=file_sha256(config), targets=[dict(id='udid-1',name='iPhone')])
        recipe = self.root / 'recipe.json'; recipe.write_text(json.dumps(data))
        def archive(command, **kwargs):Path(command[-1]).write_bytes(b'archive')
        with patch.object(devices, 'check_source'), patch.object(ios, 'installed', return_value=[]), \
                patch.object(ios, 'choose', return_value=('/fake/xcode','sdk')), \
                patch.object(ios, 'refresh_sources'), patch.object(ios, 'prepare_project'), \
                patch.object(ios, 'run') as build, patch.object(ios, 'device_json', side_effect=AssertionError('No devices')), \
                patch.object(ios, 'validate_app', return_value={'team_id':'ABCDEFGHIJ'}), patch('subprocess.run', side_effect=archive):
            devices.prepare(recipe, file_sha256(recipe))
        command = build.call_args.args[0]
        self.assertIn('generic/platform=iOS', command)
        self.assertNotIn('-allowProvisioningDeviceRegistration', command)
        self.assertNotIn('-allowProvisioningUpdates', command)
        self.assertNotIn('udid-1', command)
