"""Project integration contracts; controlled providers never publish or upload."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from Scripts.build_project import LogisticsProject
from mobile_build.deployment import firebase_deploy, manager_settings, testflight_deploy, testflight_external


class ManagerAdapterTests(unittest.TestCase):
    def test_prepared_report_keeps_embedded_identity_after_profile_changes(self):
        with TemporaryDirectory() as directory:
            report = Path(directory) / 'prepared.json'
            original = dict(version='1.2.3', build=42, source={'commit': 'a'}, destination='Synthetic group')
            with patch.dict(os.environ, {'LOGISTICS_MANAGER_ARTIFACT_REPORT': str(report)}):
                manager_settings.record_prepared_artifact(original)
            self.assertEqual(json.loads(report.read_text()), original)

    def test_build_preview_does_not_reserve_and_explicit_values_cannot_repeat(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / 'private'
            private.mkdir()
            with patch.object(firebase_deploy, 'ROOT', root), patch.object(firebase_deploy, 'PRIVATE', private):
                preview = firebase_deploy.next_build()
                self.assertFalse((private / 'build.json').exists())
                selected = preview + 5
                self.assertEqual(firebase_deploy.reserve_build(str(selected)), selected)
                with self.assertRaises(ValueError):
                    firebase_deploy.reserve_build(str(selected))
            with patch.object(testflight_deploy, 'ROOT', root):
                preview = int(testflight_deploy.next_build(root))
                self.assertFalse((root / '.tools/build-manager/ios-build.json').exists())
                self.assertEqual(testflight_deploy.reserve_build(str(preview + 5)), str(preview + 5))
                with self.assertRaises(ValueError):
                    testflight_deploy.reserve_build(str(preview + 5))

    def test_authentication_uses_credential_reference_and_environment_precedence(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / 'synthetic.p8'
            key.touch()
            auth = root / 'credentials.json'
            auth.write_text(json.dumps(dict(key_path=str(key), key_id='ABCDEFGHIJ',
                issuer_id='00000000-0000-0000-0000-000000000001')))
            manager_settings.save_profile(root / 'profile.json', {'auth.testflight_reference': str(auth)},
                                          allowed={'auth.testflight_reference'})
            with patch.object(testflight_external, 'ROOT', root), patch.object(testflight_external, 'AUTH', root / '.testflight-auth.json'), \
                    patch.dict(os.environ, {'LOGISTICS_MANAGER_PROFILE': str(root / 'profile.json'), 'ASC_KEY_ID': '0123456789'}):
                value = testflight_external.credentials()
                self.assertEqual(value['key_id'], '0123456789')
                self.assertEqual(value['key_path'], str(key))
                key.unlink()
                with self.assertRaisesRegex(ValueError, 'missing'):
                    testflight_external.credentials()

    def test_github_plan_separates_published_ref_and_expected_commit(self):
        root = Path(__file__).resolve().parents[3]
        project = LogisticsProject(root)
        source = dict(dirty=False, logistics_commit='a' * 40)
        plan = project.github_plan('Test', 'ios', source, root / 'test-results/fixture', {}, 'alpha', '')
        self.assertEqual(len(plan.phases), 2)
        for phase in plan.phases:
            self.assertEqual(phase.argv[phase.argv.index('--ref') + 1], 'alpha')
            self.assertEqual(phase.argv[phase.argv.index('--commit') + 1], 'a' * 40)
        self.assertEqual(plan.effect, 'publish')
        with self.assertRaises(ValueError):
            project.github_plan('Test', 'ios', dict(source, dirty=True), root, {}, 'working-tree', '')

    def test_macos_local_plan_has_environment_gate_and_exact_desktop_commands(self):
        from Scripts.validation_plans import desktop_checks
        root = Path(__file__).resolve().parents[3]
        project = LogisticsProject(root)
        with patch('Scripts.build_project.sys.platform', 'darwin'), patch('Scripts.build_project.identity', return_value=dict(logistics_commit='a' * 40, dirty=True, fingerprint='fixture')), \
                patch('Scripts.build_project.materialize'), patch('build_manager.local.inspect_python', return_value={'system': 'Darwin'}):
            plan = project.make_plan('Test', 'macos', 'This Mac')
        names = [phase.id for phase in plan.phases]
        expected = [name for name, _, _ in desktop_checks('Darwin', 'reports')]
        self.assertEqual(names, ['environment', *expected, 'release-tooling'])
        self.assertTrue(all(phase.dependencies == ('environment',) for phase in plan.phases[1:]))
        self.assertTrue(all(phase.environment['LOGISTICS_REQUIRE_LOCALCRYPT_TESTS'] == '1' for phase in plan.phases))
        self.assertEqual(plan.source['toolchain']['system'], 'Darwin')
        with patch('Scripts.build_project.sys.platform', 'darwin'), patch('Scripts.build_project.identity', return_value=dict(logistics_commit='a' * 40, dirty=True, fingerprint='fixture')), \
                patch('Scripts.build_project.materialize'), patch('build_manager.local.inspect_python', return_value={'system': 'Darwin'}):
            focused = project.make_plan('Test', 'macos', 'This Mac', pattern='test_dev_commands.py')
        command = focused.phases[1].argv
        self.assertEqual(command[command.index('--python') + 1], command[0])
        hosted = project.github_plan('Test', 'macos', dict(dirty=False, logistics_commit='a' * 40), root, {}, 'alpha', '')
        self.assertEqual(hosted.source['hosted_coverage'], 'macos')

    def test_linux_plan_requires_explicit_guests_and_uses_frozen_host_driver(self):
        root = Path(__file__).resolve().parents[3]
        project = LogisticsProject(root)
        values = manager_settings.defaults(root / 'mobile_build')
        values.update({'vm.linux': 'Synthetic Ubuntu', 'vm.fedora': 'Synthetic Fedora'})
        source = dict(logistics_commit='a' * 40, dirty=True, fingerprint='fixture', selection='working-tree')
        with patch('Scripts.build_project.identity', return_value=source), patch('Scripts.build_project.materialize') as snapshot, \
                patch('Scripts.build_project.manager_settings.settings', return_value=(values, {})), \
                patch('build_manager.parallels.Parallels') as provider:
            provider.return_value.selected.side_effect = [dict(uuid='ubuntu-id', name='Synthetic Ubuntu', status='stopped'),
                                                        dict(uuid='fedora-id', name='Synthetic Fedora', status='running')]
            plan = project.make_plan('Test', 'linux', 'Local Parallels VM')
            self.assertEqual([phase.id for phase in plan.phases], ['ubuntu', 'fedora'])
            self.assertEqual(plan.source['linux_coverage'], 'both')
            self.assertTrue(all(phase.cwd == str(project.private / 'snapshots/fixture') for phase in plan.phases))
            self.assertTrue(all(phase.artifacts for phase in plan.phases))
            snapshot.assert_called_once()
        with patch('Scripts.build_project.identity', return_value=source), patch('Scripts.build_project.materialize') as snapshot, \
                patch('Scripts.build_project.manager_settings.settings', return_value=(values, {})), \
                patch('build_manager.parallels.Parallels') as provider:
            provider.return_value.selected.side_effect = ValueError('Guest is unavailable')
            with self.assertRaisesRegex(ValueError, 'Guest is unavailable'):
                project.make_plan('Test', 'linux', 'Local Parallels VM')
            snapshot.assert_not_called()

    def test_ios_sequence_has_one_build_strict_families_and_owned_cleanup(self):
        project = LogisticsProject(Path(__file__).resolve().parents[3])
        values = manager_settings.defaults(project.mobile)
        def row(kind):
            return dict(udid=kind, name=kind, isAvailable=True, state='Shutdown', deviceTypeIdentifier='com.apple.CoreSimulator.SimDeviceType.'+kind)
        inventory = {'devices': {'com.apple.CoreSimulator.SimRuntime.iOS-27-1': [row('iPhone-18-Pro'),row('iPhone-Duo'),row('iPad-Pro')]}}
        with patch('Scripts.build_project.sys.platform','darwin'), patch('build_manager.apple_simulators.AppleSimulators') as client:
            client.return_value.devices.return_value = inventory
            client.return_value.toolchain.return_value = {'xcode':'Synthetic Xcode','sdk':'Synthetic SDK'}
            plan = project.ios_simulator_plan({}, project.root, project.private/'fixture-ios', values, {}, '', True)
            self.assertEqual([phase.id for phase in plan.phases], ['ios-build','iphone','iphone-cleanup','duo','duo-cleanup','ipad','ipad-cleanup'])
            self.assertEqual([row['kind'] for row in plan.source['simulator_sequence']], ['iphone','duo','ipad'])
            self.assertTrue(all(phase.always for phase in plan.phases if phase.kind=='cleanup'))
            self.assertTrue(all(phase.dependencies==('ios-build',) for phase in plan.phases if phase.id in ('iphone','duo','ipad')))
            inventory['devices']['com.apple.CoreSimulator.SimRuntime.iOS-27-1'].pop(1)
            with self.assertRaisesRegex(RuntimeError,'Duo'):
                project.ios_simulator_plan({},project.root,project.private/'fixture-ios',values,{},'',False)

    def test_windows_transfer_rejects_source_links_instead_of_copying_target_bytes(self):
        from Scripts.windows_backend import source_zip
        with TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'file.py').write_text('synthetic source')
            (root/'link.py').symlink_to('file.py')
            with patch('Scripts.windows_backend.source_members',return_value=['link.py']):
                with self.assertRaisesRegex(ValueError,'cannot flatten'):
                    source_zip(root)

    def test_historical_plan_uses_the_resolved_source_version(self):
        root=Path(__file__).resolve().parents[3]
        project=LogisticsProject(root)
        source=dict(logistics_commit='a'*40,commonUtils_commit='b'*40,dirty=False,selection='HEAD',fingerprint='fixture')
        with patch('Scripts.build_project.identity',return_value=source), patch('Scripts.build_project.manager_settings.app_version',return_value='1.2.3') as version:
            plan=project.make_plan('Test','ios','GitHub',revision='HEAD')
        version.assert_called_once_with(project.mobile,revision='a'*40)
        self.assertEqual(plan.source['app_version'],'1.2.3')
