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

    def test_connection_override_is_explicit_scoped_and_does_not_change_saved_metadata(self):
        from Scripts.manager_journeys import run_values
        values = {'devices.android':'["hardware-1"]',
                  'devices.android_connections':'{"hardware-1":"hardware-1"}'}
        run_values(values)
        self.assertEqual(devices.selected_devices(self.root, 'android', values)[0]['connection'], 'hardware-1')
        self.assertEqual(devices.saved_devices(self.root)['android']['hardware-1']['connection'], 'usb-1')
        for invalid in ('[]', '{"other":"usb-2"}', '{"hardware-1":12}', '{"hardware-1":""}'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                devices.selected_devices(self.root, 'android', dict(values, **{'devices.android_connections':invalid}))

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
        self.assertEqual([row.effect for row in plan.phases], ['build','inspect','deploy','inspect','deploy'])
        ready = [row for row in plan.phases if row.effect == 'inspect']
        installs = [row for row in plan.phases if row.effect == 'deploy']
        self.assertEqual([row.retry_exit_codes for row in ready], [(75,), (75,)])
        for check, install in zip(ready, installs):
            self.assertEqual(check.dependencies, ('prepare-device-app',))
            self.assertEqual(install.dependencies, ('prepare-device-app', check.id))
            self.assertFalse(check.resources)
        self.assertIn('--sha256', plan.phases[0].argv)
        self.assertIn('one', plan.phases[1].argv); self.assertNotIn('two', plan.phases[1].argv)
        self.assertEqual(len(plan.phases[0].artifacts), 2)
        self.assertEqual(plan.phases[0].environment['PATH'].split(os.pathsep)[0],
                         str(project.mobile / '.tools/go/bin'))
        self.assertEqual(plan.phases[0].environment['PIP_FIND_LINKS'],
                         str(project.mobile / '.tools/release-wheels'))

    def test_offline_readiness_reconnects_only_selected_transport_without_installing(self):
        from Scripts.manager_devices import DeviceUnavailable
        from mobile_build.deployment import android_deploy as android
        recipe = self.root / 'recipe.json'
        data = dict(self.data)
        data['targets'] = [dict(id='hardware-1', connection='192.0.2.1:12345', name='Tablet')]
        recipe.write_text(json.dumps(data))
        with patch.object(android, 'tools_environment', return_value=({}, '/fake/adb')), \
                patch.object(android, 'run', side_effect=['connected', 'offline']) as run:
            with self.assertRaises(DeviceUnavailable):
                devices.ready(recipe, file_sha256(recipe), 'hardware-1')
        self.assertEqual(run.call_args_list[0].args[0], ['/fake/adb', 'connect', '192.0.2.1:12345'])
        self.assertFalse(any('install' in call.args[0] for call in run.call_args_list))
        self.assertFalse(self.receipt.with_suffix('.attempt.json').exists())
        with patch.object(android, 'tools_environment', return_value=({}, '/fake/adb')), \
                patch.object(android, 'run', side_effect=['connected', 'device', 'wrong-device']):
            with self.assertRaisesRegex(ValueError, 'identity changed'):
                devices.ready(recipe, file_sha256(recipe), 'hardware-1')

    def test_ios_readiness_retries_absent_or_disconnected_selected_device_only(self):
        from mobile_build.deployment import device_tools as ios
        recipe = self.root / 'recipe.json'
        data = dict(self.data, platform='ios', targets=[dict(id='udid-1', name='Phone')])
        recipe.write_text(json.dumps(data))
        selected = dict(identifier='identifier-1', hardwareProperties=dict(udid='udid-1', reality='physical', deviceType='iPhone'),
                        connectionProperties=dict(pairingState='paired', tunnelState='disconnected'))
        with patch.object(ios, 'installed', return_value=[]), patch.object(ios, 'choose', return_value=('/fake/xcode', 'sdk')):
            for rows in ([], [selected]):
                with patch.object(ios, 'device_json', return_value={'devices': rows}) as native:
                    with self.assertRaises(devices.DeviceUnavailable):
                        devices.ready(recipe, file_sha256(recipe), 'udid-1')
                    self.assertEqual(native.call_args.args[0], ['list', 'devices'])
            selected['connectionProperties']['tunnelState'] = 'connected'
            with patch.object(ios, 'device_json', return_value={'devices': [selected]}):
                devices.ready(recipe, file_sha256(recipe), 'udid-1')
        self.assertFalse(self.receipt.exists())

    def test_source_or_recipe_change_blocks_preparation_before_any_tools(self):
        recipe = self.root / 'recipe.json'; recipe.write_text('{}')
        with patch.object(devices, 'check_source', side_effect=AssertionError('must not reach source')):
            with self.assertRaisesRegex(ValueError, 'recipe changed'):devices.prepare(recipe, 'wrong')

    def test_android_preparation_disables_discovery_and_builds_without_devices(self):
        from mobile_build.deployment import android_deploy as android
        workspace = self.root / 'workspace'; workspace.mkdir()
        apk = self.root / 'gradle/app/build/outputs/apk/debug/app-debug.apk'; apk.parent.mkdir(parents=True); apk.write_bytes(b'build')
        recipe = self.root / 'recipe.json'; recipe.write_text(json.dumps(dict(self.data, workspace=str(workspace), root=str(self.root))))
        with patch.object(devices, 'check_source'), patch.object(android, 'PROJECT', self.root / 'gradle'), \
                patch.object(devices, 'sign_android_debug', return_value='certificate'), patch.object(android, 'deploy') as build:
            devices.prepare(recipe, file_sha256(recipe))
        build.assert_called_once_with(build_only=True, devices=[], discover=False)
        self.assertEqual((workspace / 'app.apk').read_bytes(), b'build')
        self.assertTrue((workspace / 'prepared.json').exists())

    def test_signing_conflict_blocks_before_install_attempt_and_retires_pulled_apk(self):
        from mobile_build.deployment import android_deploy as android
        self.data.update(identity={'certificate':'prepared'}, workspace=str(self.root))
        self.report.write_text(json.dumps(self.data))
        self.env['BUILD_MANAGER_APPROVED_ARTIFACTS'] = json.dumps([
            dict(original_path=str(self.report.resolve()), sha256=file_sha256(self.report))])
        with patch.dict(os.environ, self.env), patch.object(android, 'tools_environment', return_value=({}, '/adb')), \
                patch.object(android, 'build_tools', return_value=self.root), \
                patch.object(android, 'apk_certificate', return_value='installed'), \
                patch.object(android, 'run', side_effect=['device', 'hardware-1', 'package:/installed/base.apk', 'pulled']) as run:
            with self.assertRaisesRegex(ValueError, 'signing identity differs'):
                devices.install(self.report, 'hardware-1', self.receipt)
        self.assertFalse(self.receipt.with_suffix('.attempt.json').exists())
        self.assertFalse(any('install' in call.args[0] for call in run.call_args_list))
        self.assertFalse(list(self.root.glob('signature-check-*.apk')))

    def test_beta_signing_is_selected_before_review_without_device_discovery(self):
        from mobile_build.deployment import android_deploy as android
        private = self.root / 'mobile_build/.android-beta'; private.mkdir()
        (private / 'signing.p12').write_bytes(b'fixture key')
        (private / 'signing.json').write_text(json.dumps({'password':'fixture-password'}))
        data = dict(self.data, root=str(self.root), workspace=str(self.root),
                    source={'run_overrides':{'devices.android_signing':'beta'}})
        (self.root / 'signed.apk').write_bytes(b'signed package')
        import hashlib
        certificate = hashlib.sha256(b'fixture certificate').hexdigest()
        with patch.object(android, 'tools_environment', return_value=({'JAVA_HOME':'/java'}, '/adb')), \
                patch.object(android, 'build_tools', return_value=Path('/tools')), \
                patch('subprocess.check_output', return_value=b'fixture certificate'), \
                patch.object(android, 'apk_certificate', return_value=certificate), patch.object(android, 'run') as run:
            self.assertEqual(devices.sign_android_debug(data, self.package), certificate)
        self.assertEqual(self.package.read_bytes(), b'signed package')
        self.assertIn('sign', run.call_args.args[0])
        self.assertNotIn('fixture-password', ' '.join(run.call_args.args[0]))

    def test_shared_release_apk_is_copied_exactly_without_build_or_device_discovery(self):
        from mobile_build.deployment import android_deploy as android
        workspace = self.root / 'workspace'; workspace.mkdir()
        shared = self.root / 'release.json'
        shared.write_text(json.dumps(dict(provider='Firebase', bundle_id=devices.BUNDLE, apk=str(self.package),
            apk_sha256=file_sha256(self.package), certificate='certificate')))
        data = dict(self.data, workspace=str(workspace), shared_report=str(shared))
        with patch.object(android, 'deploy', side_effect=AssertionError('Must not rebuild')), \
                patch('subprocess.run', side_effect=AssertionError('Must not contact devices')):
            devices.prepare_shared(data)
        self.assertEqual(Path(data['package']).read_bytes(), self.package.read_bytes())
        self.assertEqual(data['variant'], 'release')
        self.package.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'):devices.prepare_shared(data)

    def test_release_device_recipe_has_shared_input_and_preserves_review_per_device(self):
        from build_manager import Phase
        project = LogisticsProject(self.root)
        source = dict(fingerprint='source', dirty=False, effective_settings=dict(values={'tools.mobile_python':sys.executable}))
        context = PlanningContext(str(project.root), 'HEAD', json.dumps(source))
        shared = Phase('release', (sys.executable,'-V'), str(self.root), artifacts=(str(self.report),))
        def snapshot(*args, **kwargs):(project.private / 'snapshots/source/mobile_build').mkdir(parents=True)
        with patch('Scripts.build_snapshots.materialize', side_effect=snapshot):
            plan = devices.make_plan(project, 'android', self.data['targets'], context, 'HEAD', shared=shared)
        recipe = json.loads(Path(plan.phases[0].argv[plan.phases[0].argv.index('--recipe')+1]).read_text())
        self.assertEqual(recipe['shared_report'], str(self.report))
        self.assertIn('shared Android Release', plan.phases[0].label)
        self.assertEqual(plan.phases[1].effect, 'inspect')
        self.assertEqual(plan.phases[2].effect, 'deploy')

    def test_shared_ios_release_exports_existing_archive_without_compiling_or_devices(self):
        from mobile_build.deployment import device_tools as ios
        workspace = self.root / 'workspace'; workspace.mkdir()
        config = self.mobile / '.device.json'
        data = dict(self.data, platform='ios', workspace=str(workspace), shared_report='archive.json',
            config=str(config), config_sha256=file_sha256(config), targets=[dict(id='udid-1',name='iPhone')])
        identity = dict(team_id='ABCDEFGHIJ', bundle_id=devices.BUNDLE)
        def export(command, **kwargs):
            output = Path(command[command.index('-exportPath')+1]); output.mkdir(); (output / 'app.ipa').write_bytes(b'ipa')
        def ditto(command, **kwargs):
            if '-x' in command:(Path(command[-1]) / 'Payload/Logistics Mobile.app').mkdir(parents=True)
            else:Path(command[-1]).write_bytes(b'provisioned app')
        with patch('Scripts.manager_packages.checked_archive', return_value=(dict(workspace=str(self.root/'release')),dict(identity=identity))), \
                patch.object(ios, 'installed', return_value=[]), patch.object(ios, 'choose', return_value=('/fake/xcode','sdk')), \
                patch.object(ios, 'run', side_effect=export) as run, patch.object(ios, 'validate_app', return_value=identity), \
                patch.object(ios, 'device_json', side_effect=AssertionError('No devices')), patch('subprocess.run', side_effect=ditto):
            devices.prepare_shared(data)
        self.assertIn('-exportArchive', run.call_args.args[0])
        self.assertNotIn('archive', run.call_args.args[0]); self.assertNotIn('build', run.call_args.args[0])
        self.assertNotIn('-allowProvisioningUpdates', run.call_args.args[0])
        self.assertEqual(Path(data['package']).read_bytes(), b'provisioned app')
        self.assertFalse((workspace/'exported-app').exists())

    def test_actual_ios_preparation_separates_archive_from_export_and_keeps_one_build_number(self):
        project = LogisticsProject(self.root)
        snapshot = self.root / 'snapshot'; (snapshot / 'mobile_build').mkdir(parents=True)
        options = {'tools.mobile_python':sys.executable, 'tools.xcode':'', 'tools.android_sdk':'',
                   'tools.java':'', 'signing.app_profile':'', 'signing.inbox_profile':''}
        plan = project.mobile_plan('Prepare TestFlight', 'ios', {'dirty':False}, snapshot,
                                  self.root / 'workspace', options, {}, '', '42', False)
        archive, export = plan.phases
        self.assertEqual(archive.id, 'build-release-archive')
        self.assertEqual(export.dependencies, (archive.id,))
        self.assertIn('--build-number', archive.argv); self.assertIn('42', archive.argv)
        state = archive.argv[archive.argv.index('--state')+1]
        self.assertEqual(export.argv[export.argv.index('--state')+1], state)
        self.assertIn('export-testflight', export.argv)
        self.assertTrue(all(p.effect == 'build' for p in plan.phases))
        self.assertNotIn('upload', archive.argv); self.assertNotIn('upload', export.argv)

    def test_shared_archive_integrity_is_checked_before_either_export(self):
        from Scripts import manager_packages as packages
        from mobile_build.deployment import testflight_tools as tools
        release = self.root / 'release.json'; release.write_text('{"identity":{}}')
        state = self.root / 'state.json'; state.write_text(json.dumps(dict(workspace=str(self.root),
            release_sha256=file_sha256(release), archive_sha256='archive-hash')))
        with patch.object(tools,'archive_fingerprint',return_value='archive-hash'):
            packages.checked_archive(state)
            release.write_text('{"identity":{"changed":true}}')
            with self.assertRaisesRegex(ValueError,'archive changed'):packages.checked_archive(state)
        with patch.object(tools,'archive_fingerprint',return_value='different'):
            with self.assertRaises(ValueError):packages.checked_archive(state)

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
