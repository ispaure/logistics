"""Project integration contracts; controlled providers never publish or upload."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from logistics_build.build_project import LogisticsProject
from build_manager.test_manifest import discover as _discover
from mobile_build.deployment import firebase_deploy, manager_settings, testflight_deploy, testflight_external


class ManagerAdapterTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix='logistics-adapter-contracts-')
        self.addCleanup(temporary.cleanup)
        private = Path(temporary.name)
        initialize = LogisticsProject.__init__
        def isolated(project, root):
            initialize(project, root)
            from uuid import uuid4
            project.private = private / uuid4().hex
        initialization = patch.object(LogisticsProject, '__init__', isolated)
        initialization.start(); self.addCleanup(initialization.stop)
        discovery = patch('build_manager.test_manifest.discover', side_effect=lambda root, group: _discover(Path(__file__).resolve().parents[3], group))
        discovery.start(); self.addCleanup(discovery.stop)
        retention = patch("logistics_build.build_retention.clean", return_value=[])
        retention.start()
        self.addCleanup(retention.stop)

    def test_only_shared_step_resources_serialize_mobile_platforms(self):
        from logistics_build.build_project import declare_resources
        from build_manager import Phase, Plan
        with TemporaryDirectory() as directory:
            phase = Phase('build', ('fixture-python', '-V'), directory, kind='build')
            check = Phase('contracts', ('fixture-python', '-V'), directory)
            for target in ('ios', 'android'):
                plan = declare_resources(Plan('Fixture', 'Test', {}, (phase, check), directory), target)
                self.assertEqual(plan.phases[0].resources['host.mobile-build'], 1)
                self.assertEqual(plan.phases[0].resources['project.workspace:' + directory], 1)
                self.assertFalse(plan.phases[1].resources)
                self.assertNotIn('host.mobile-device-session', plan.resources)

    def test_mobile_runtime_preparation_and_tests_share_the_actual_project_lock(self):
        from logistics_build.build_project import declare_resources
        from build_manager import Phase, Plan
        with TemporaryDirectory() as directory:
            shared = 'project.mobile-runtime:' + directory
            for target in ('ios', 'android'):
                phases = tuple(Phase(target + suffix, ('fixture-python', '-V'), directory)
                               for suffix in ('-runtime-tools', '-runtime', '-native'))
                plan = declare_resources(Plan('Fixture', 'Test', {}, phases,
                    str(Path(directory) / target)), target)
                self.assertEqual(plan.phases[0].resources[shared], 1)
                self.assertEqual(plan.phases[1].resources[shared], 1)
                self.assertNotIn(shared, plan.phases[2].resources)

    def test_ios_manual_signing_forwards_every_extension_and_rejects_missing_profiles(self):
        project = LogisticsProject(Path(__file__).resolve().parents[3])
        with TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / 'snapshot'
            support = snapshot / 'mobile_build/build_support'
            support.mkdir(parents=True)
            (support / 'widget_build.py').touch()
            values = manager_settings.defaults(project.mobile)
            references = dict(app_profile='main', inbox_profile='inbox',
                              widget_profile='widgets', widget_actions_profile='actions')
            values.update({'signing.' + key: value for key, value in references.items()})
            def prepare():
                return project.mobile_plan('Prepare TestFlight', 'ios', {}, snapshot,
                    root / 'ios', values, {}, '', '', False)
            plan = prepare()
            for key, value in references.items():
                flag = '--profile' if key == 'app_profile' else '--' + key.replace('_', '-')
                argv = plan.phases[0].argv
                self.assertEqual(argv[argv.index(flag) + 1], value)
            values['signing.widget_profile'] = ''
            with self.assertRaisesRegex(ValueError, 'Manual iOS signing requires all extension profiles'):
                prepare()
            values.update({'signing.' + key: '' for key in references})
            automatic = prepare()
            self.assertNotIn('--profile', automatic.phases[0].argv)

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
        self.assertEqual(plan.effect, 'dispatch')
        self.assertTrue(all(phase.effect=='dispatch' for phase in plan.phases))
        with self.assertRaises(ValueError):
            project.github_plan('Test', 'ios', dict(source, dirty=True), root, {}, 'working-tree', '')

    def test_signed_tester_preparation_accepts_captured_working_source(self):
        root = Path(__file__).resolve().parents[3]
        project = LogisticsProject(root)
        from build_manager.proposed_workflow import propose
        proposal = propose(capability=project.journey_capability, goal='deliver', revision='working-tree',
            platforms=['ios', 'android'], destinations=['testflight', 'firebase'], backends={})
        self.assertNotIn('source', {b.id for b in proposal.blockers})
        source = dict(logistics_commit='a'*40, commonUtils_commit='b'*40, dirty=True, fingerprint='c'*64)
        values = manager_settings.defaults(project.mobile)
        with TemporaryDirectory() as directory:
            snapshot = Path(directory)
            (snapshot/'mobile_build').mkdir()
            with patch('logistics_build.build_project.sys.platform', 'darwin'), \
                    patch('logistics_build.build_project.identity', return_value=source), \
                    patch('logistics_build.build_project.materialize', side_effect=lambda root, dest, *a, **kw: (dest/'mobile_build').mkdir(parents=True, exist_ok=True)), \
                    patch('logistics_build.build_project.manager_settings.settings', return_value=(values, {})), \
                    patch('logistics_build.build_project.manager_settings.app_version', return_value='1.2.3'):
                for operation, target in (('Prepare Firebase','android'), ('Prepare TestFlight','ios')):
                    plan = project.make_plan(operation, target, 'This Mac')
                    self.assertTrue(plan.source['dirty'])
                    self.assertEqual(plan.source['fingerprint'], source['fingerprint'])
                    self.assertFalse(any(p.effect in {'upload', 'publish', 'dispatch'} for p in plan.phases))

    def test_macos_local_plan_has_environment_gate_and_exact_desktop_commands(self):
        from logistics_build.validation_plans import desktop_checks
        root = Path(__file__).resolve().parents[3]
        project = LogisticsProject(root)
        with patch('logistics_build.build_project.sys.platform', 'darwin'), patch('logistics_build.build_project.platform.system', return_value='Darwin'), patch('logistics_build.build_project.identity', return_value=dict(logistics_commit='a' * 40, dirty=True, fingerprint='fixture')), \
                patch('logistics_build.build_project.materialize'), patch('build_manager.local.inspect_python', return_value={'system': 'Darwin'}):
            plan = project.make_plan('Test', 'macos', 'This Mac')
        names = [phase.id for phase in plan.phases]
        expected = [name for name, _, _ in desktop_checks('Darwin', 'reports')]
        self.assertEqual(names, ['environment', *expected, 'release-tooling'])
        self.assertEqual(next(phase for phase in plan.phases if phase.id == 'logistics').dependencies, ('environment', 'commonutils'))
        self.assertTrue(all('environment' in phase.dependencies for phase in plan.phases[1:]))
        self.assertTrue(all(phase.environment['LOGISTICS_REQUIRE_LOCALCRYPT_TESTS'] == '1' for phase in plan.phases))
        self.assertEqual(plan.source['toolchain']['system'], 'Darwin')
        with patch('logistics_build.build_project.sys.platform', 'darwin'), patch('logistics_build.build_project.platform.system', return_value='Darwin'), patch('logistics_build.build_project.identity', return_value=dict(logistics_commit='a' * 40, dirty=True, fingerprint='fixture')), \
                patch('logistics_build.build_project.materialize'), patch('build_manager.local.inspect_python', return_value={'system': 'Darwin'}):
            focused = project.make_plan('Test', 'macos', 'This Mac', pattern='test_dev_commands.py')
        command = focused.phases[1].argv
        self.assertEqual(command[0], plan.phases[0].argv[0])
        self.assertIn('Python/tests/run_regressions.py', command)
        self.assertEqual(command[command.index('--pattern') + 1], 'test_dev_commands.py')
        self.assertIn('junit', focused.phases[1].artifact_types.values())
        hosted = project.github_plan('Test', 'macos', dict(dirty=False, logistics_commit='a' * 40), root, {}, 'alpha', '')
        self.assertEqual(hosted.source['hosted_coverage'], 'macos')

    def test_linux_plan_requires_explicit_guests_and_uses_frozen_host_driver(self):
        root = Path(__file__).resolve().parents[3]
        project = LogisticsProject(root)
        values = manager_settings.defaults(root / 'mobile_build')
        values.update({'vm.fedora': 'Synthetic Fedora'})
        source = dict(logistics_commit='a' * 40, dirty=True, fingerprint='fixture', selection='working-tree')
        with patch('logistics_build.build_project.sys.platform', 'darwin'), patch('logistics_build.build_project.identity', return_value=source), patch('logistics_build.build_project.materialize') as snapshot, \
                patch('logistics_build.build_project.manager_settings.settings', return_value=(values, {})), \
                patch('build_manager.parallels.Parallels') as provider:
            provider.return_value.selected.return_value = dict(uuid='fedora-id', name='Synthetic Fedora', status='running')
            plan = project.make_plan('Test', 'linux', 'Local Parallels VM')
            self.assertEqual([phase.id for phase in plan.phases], ['fedora'])
            self.assertEqual(plan.source['linux_coverage'], 'fedora')
            provider.return_value.selected.assert_called_once_with('Synthetic Fedora')
            self.assertTrue(all(phase.cwd == str(project.private / 'snapshots/fixture') for phase in plan.phases))
            self.assertTrue(all(phase.artifacts for phase in plan.phases))
            snapshot.assert_called_once()
        with patch('logistics_build.build_project.sys.platform', 'darwin'), patch('logistics_build.build_project.identity', return_value=source), patch('logistics_build.build_project.materialize') as snapshot, \
                patch('logistics_build.build_project.manager_settings.settings', return_value=(values, {})), \
                patch('build_manager.parallels.Parallels') as provider:
            provider.return_value.selected.side_effect = ValueError('Guest is unavailable')
            with self.assertRaisesRegex(ValueError, 'Guest is unavailable'):
                project.make_plan('Test', 'linux', 'Local Parallels VM')
            snapshot.assert_not_called()

    def test_linux_container_uses_only_fedora_on_explicit_host(self):
        root = Path(__file__).resolve().parents[3]
        project = LogisticsProject(root)
        values = manager_settings.defaults(project.mobile)
        values.update({'vm.fedora_mode': 'container-on-ubuntu',
                       'vm.fedora_container_host': 'Authorized host'})
        source = dict(fingerprint='fixture', selection='HEAD')
        with patch('logistics_build.build_project.materialize'), patch('build_manager.parallels.Parallels') as provider:
            provider.return_value.selected.return_value = dict(uuid='host-id', name='Authorized host', status='running')
            plan = project.local_vm_plan('Test', 'linux', source, root / 'test-results/fixture', values, '')
        provider.return_value.selected.assert_called_once_with('Authorized host')
        self.assertEqual([phase.id for phase in plan.phases], ['fedora'])
        command = plan.phases[0].argv
        self.assertEqual(command[command.index('--distribution') + 1], 'fedora')
        self.assertIn('--container-image', command)
        self.assertEqual(plan.source['linux_coverage'], 'fedora')

    def test_descriptor_exposes_existing_ios_build_operation(self):
        root = Path(__file__).resolve().parents[3]
        capability = json.loads((root / 'build-project.json').read_text())['capabilities']
        self.assertIn('Build', capability['operations_by_target']['ios'])
        self.assertEqual(capability['host_backends']['darwin']['ios']['Build'], ['This Mac'])

    def test_ios_development_build_captures_edits_without_installation(self):
        project = LogisticsProject(Path(__file__).resolve().parents[3])
        values = manager_settings.defaults(project.mobile)
        source = dict(dirty=True, commonUtils_dirty=True, fingerprint='fixture')
        with patch('logistics_build.build_project.sys.platform', 'darwin'):
            plan = project.mobile_plan('Build', 'ios', source, project.root,
                                       project.private / 'fixture-ios', values, {}, '', '', False)
        self.assertEqual([phase.id for phase in plan.phases], ['ios-build'])
        self.assertEqual(plan.effect, 'build')
        self.assertEqual(plan.source, source)
        self.assertIn('logistics_build.ios_backend', plan.phases[0].argv)
        self.assertIn('build', plan.phases[0].argv)
        self.assertTrue(plan.phases[0].artifacts)
        with patch('logistics_build.build_project.sys.platform', 'linux'):
            with self.assertRaisesRegex(ValueError, 'macOS'):
                project.mobile_plan('Build', 'ios', source, project.root,
                                    project.private, values, {}, '', '', False)

    def test_ios_sequence_has_one_build_strict_families_and_owned_cleanup(self):
        project = LogisticsProject(Path(__file__).resolve().parents[3])
        values = manager_settings.defaults(project.mobile)
        def row(kind):
            return dict(udid=kind, name=kind, isAvailable=True, state='Shutdown', deviceTypeIdentifier='com.apple.CoreSimulator.SimDeviceType.'+kind)
        inventory = {'devices': {'com.apple.CoreSimulator.SimRuntime.iOS-27-1': [row('iPhone-18-Pro'),row('iPhone-Duo'),row('iPad-Pro')]}}
        with patch('logistics_build.build_project.sys.platform','darwin'), patch('build_manager.apple_simulators.AppleSimulators') as client:
            client.return_value.devices.return_value = inventory
            client.return_value.toolchain.return_value = {'xcode':'Synthetic Xcode','sdk':'Synthetic SDK'}
            plan = project.ios_simulator_plan({}, project.root, project.private/'fixture-ios', values, {}, '', True)
            self.assertEqual([phase.id for phase in plan.phases], ['ios-build','iphone','iphone-cleanup','duo','duo-cleanup','ipad','ipad-cleanup','ios-runtime-tools','ios-runtime','ios-runtime-cleanup'])
            self.assertEqual([row['kind'] for row in plan.source['simulator_sequence']], ['iphone','duo','ipad'])
            self.assertTrue(all(phase.always for phase in plan.phases if phase.kind=='cleanup'))
            self.assertEqual({phase.id:phase.dependencies for phase in plan.phases if phase.id in ('iphone','duo','ipad')},
                             {'iphone':('ios-build',),'duo':('iphone-cleanup',),'ipad':('duo-cleanup',)})
            phases = {phase.id: phase for phase in plan.phases}
            self.assertEqual(phases['ios-runtime'].dependencies, ('ios-runtime-tools', 'ipad-cleanup'))
            self.assertTrue(phases['ios-runtime-cleanup'].always)
            inventory['devices']['com.apple.CoreSimulator.SimRuntime.iOS-27-1'].pop(1)
            core_only = project.ios_simulator_plan({}, project.root, project.private/'fixture-ios', values, {}, '', False, runtime_only=True)
            self.assertEqual([row['kind'] for row in core_only.source['simulator_sequence']], ['iphone'])
            with self.assertRaisesRegex(RuntimeError,'Duo'):
                project.ios_simulator_plan({},project.root,project.private/'fixture-ios',values,{},'',False)

    def test_windows_transfer_rejects_source_links_instead_of_copying_target_bytes(self):
        from logistics_build.windows_backend import source_zip
        with TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'file.py').write_text('synthetic source')
            (root/'link.py').symlink_to('file.py')
            with patch('logistics_build.windows_backend.source_members',return_value=['link.py']):
                with self.assertRaisesRegex(ValueError,'cannot flatten'):
                    source_zip(root)

    def test_historical_plan_uses_the_resolved_source_version(self):
        root=Path(__file__).resolve().parents[3]
        project=LogisticsProject(root)
        source=dict(logistics_commit='a'*40,commonUtils_commit='b'*40,dirty=False,selection='HEAD',fingerprint='fixture')
        with patch('logistics_build.build_project.git',return_value='fixture-branch'), \
                patch('logistics_build.build_project.identity',return_value=source), \
                patch('logistics_build.build_project.manager_settings.app_version',return_value='1.2.3') as version:
            plan=project.make_plan('Test','ios','GitHub',revision='HEAD')
        version.assert_called_once_with(project.mobile,revision='a'*40)
        self.assertEqual(plan.source['app_version'],'1.2.3')
