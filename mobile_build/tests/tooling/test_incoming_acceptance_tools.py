"""QA receiver preparation must preserve the real native intake boundary."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from copy import deepcopy
from pathlib import Path
import plistlib
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from logistics_build.incoming_acceptance import MAIN_BUNDLE, QA_BUNDLE, SENDER_BUNDLE, cleanup, cleanup_ios, ios_identity, plan, verify_ios


class IncomingAcceptanceToolsTests(unittest.TestCase):
    def test_provider_checkpoint_ack_requires_exact_ready_file_while_held(self):
        from mobile_build.validation.incoming_ios_tools import ProviderObservation
        with TemporaryDirectory() as directory:
            root = Path(directory)
            observer = ProviderObservation.__new__(ProviderObservation)
            observer.device, observer.case, observer.mode = 'fixture-device', 'cancel', 'cancel'
            observer.output, observer.telemetry, observer.paths, observer.held = root, root / 'cancel.json', (), None
            observer.environment, observer.next_container_check = {}, 0
            observer.telemetry_paths, observer.container_errors, observer.binding = [str(observer.telemetry)], [], None
            observer.fixtures = [dict(name='first.txt', length=4, sha256='abcd')]
            queue = dict(ready={}, partial={}, failure=False, producer=False)
            observer.before = dict(publications={}, publication_raw_filenames={}, publication_temporary=[],
                                   queues=dict(main=deepcopy(queue), share=deepcopy(queue)))
            state = deepcopy(observer.before)
            state['queues']['share']['ready']['one.ready'] = dict(name='first.txt', length=4, sha256='wrong')
            telemetry = dict(schema=1, mode='cancel', events=[dict(event=name, uptime=index) for index, name in
                                    enumerate(('prepared', 'armed', 'requested'))])
            observer.telemetry.write_text(json.dumps(telemetry))
            ack = root / 'cancel-checkpoint.json'
            with patch('mobile_build.validation.incoming_ios_tools._receiver_state', return_value=state):
                observer.observe()
                self.assertFalse(ack.exists())
                state['queues']['share']['ready']['one.ready']['sha256'] = 'abcd'
                observer.observe()
            self.assertEqual(json.loads(ack.read_text()), dict(schema=1, mode='cancel', requested_uptime=2))
            saved = json.loads((root / 'cancel-provider-observation.json').read_text())
            self.assertTrue(saved['held_checkpoint']['passed'])
            self.assertEqual(saved['held_checkpoint']['telemetry_before'], saved['held_checkpoint']['telemetry_after'])
            observer.held = None
            ack.unlink()
            telemetry['events'].append(dict(event='released', uptime=3))
            observer.telemetry.write_text(json.dumps(telemetry))
            with patch('mobile_build.validation.incoming_ios_tools._receiver_state') as snapshot:
                observer.observe()
                snapshot.assert_not_called()
            self.assertFalse(ack.exists())

    def test_provider_acceptance_rejects_early_load_fallback_and_cancel_before_action(self):
        from mobile_build.validation.incoming_ios_tools import ProviderObservation
        with TemporaryDirectory() as directory:
            root = Path(directory)
            observer = ProviderObservation.__new__(ProviderObservation)
            observer.case, observer.mode, observer.output, observer.held = 'cancel', 'cancel', root, {'passed': True}
            observer.telemetry = root / 'cancel.json'
            observer.environment, observer.next_container_check = {}, 0
            observer.telemetry_paths, observer.container_errors, observer.binding = [str(observer.telemetry)], [], {'bound': True}
            observer.fixtures = [dict(name=name) for name in ('first.txt', 'second.txt')]
            candidate = dict(first_data_type='public.plain-text', file_url_conformance=True,
                             registered_types=['public.plain-text', 'public.file-url'])
            valid = dict(schema=1, mode='cancel', items=[
                dict(filename=item['name'], content_type='public.plain-text', candidate=deepcopy(candidate),
                     url_writable_types=['public.file-url']) for item in observer.fixtures],
                events=[dict(event=name, uptime=stamp) for name, stamp in
                        zip(('prepared', 'armed', 'requested', 'checkpoint-observed', 'cancelled'), (1, 2, 4, 5, 8))])
            log = root / 'cancel.log'
            log.write_text('[IncomingFiles] cancel-provider-selection-start\n3\n'
                           '[IncomingFiles] cancel-provider-held-main-stopped\n4.5\n'
                           '[IncomingFiles] cancel-provider-action-start\n7\n')
            xctest = dict(returncode=0, log=str(log))
            observer.telemetry.write_text(json.dumps(valid))
            self.assertTrue(observer.verify(xctest)['passed'])
            invalid = []
            value = deepcopy(valid)
            value['events'][2]['event'] = 'early-load'
            invalid.append(value)
            value = deepcopy(valid)
            value['events'][-1]['uptime'] = 6
            invalid.append(value)
            value = deepcopy(valid)
            value['items'][1]['candidate']['first_data_type'] = 'public.file-url'
            invalid.append(value)
            value = deepcopy(valid)
            value['items'][1]['candidate']['registered_types'].reverse()
            invalid.append(value)
            for value in invalid:
                with self.subTest(value=value):
                    observer.telemetry.write_text(json.dumps(value))
                    with self.assertRaises(ValueError):
                        observer.verify(xctest)
            observer.telemetry.write_text(json.dumps(valid))
            observer.held = None
            with self.assertRaises(ValueError):
                observer.verify(xctest)

    def test_provider_observer_rebinds_after_xctest_replaces_source_data_container(self):
        from mobile_build.validation.incoming_ios_tools import ProviderObservation
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original, current = root / 'original/Documents', root / 'replacement/Documents'
            original.mkdir(parents=True)
            evidence = current / 'ProviderEvidence/cancel.json'
            evidence.parent.mkdir(parents=True)
            evidence.write_text(json.dumps(dict(schema=1, mode='cancel', events=[dict(event='prepared', uptime=1)])))
            fixtures = [dict(id=f'cancel-{name}', name=name) for name in ('first', 'second')]
            with patch('mobile_build.validation.incoming_ios_tools._receiver_paths', return_value=()), \
                 patch('mobile_build.validation.incoming_ios_tools._sender_documents', side_effect=[original, current]):
                observer = ProviderObservation('fixture-device', 'cancel', fixtures, {}, root, {})
                observer.observe()
            self.assertEqual(observer.telemetry, evidence)
            self.assertEqual(observer.binding['source_bundle'], SENDER_BUNDLE)
            self.assertEqual(len(observer.binding['resolved_paths']), 2)
            self.assertEqual(json.loads((root / 'cancel-provider-binding.json').read_text())['telemetry_path'], str(evidence))
            self.assertIsNone(observer.held)
            self.assertFalse((evidence.parent / 'cancel-checkpoint.json').exists())

    def test_window_proof_requires_readers_after_restart_and_one_main_publication(self):
        from mobile_build.validation.incoming_ios_tools import CASES, verify_window_routing
        with TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / 'files-open.log'
            proof = dict(schema=3, route='files-open-with', windows_before=2, windows_after=3,
                         active_window_after_delivery='new-home', primary_app_settings_preserved=True,
                         secondary_app_settings_preserved=True, restart_before_read=True,
                         read_window='primary-after-restart', opened_from_on_my_tablet=True,
                         reopened_from_on_my_tablet=True)
            log.write_text('[IncomingFiles] ipad-window-routing-proof\n' + json.dumps(proof) + '\n')
            xctest = dict(returncode=0, case='files-open', test=CASES['files-open'], log=str(log))
            publication = dict(passed=True, queue_route_matches=True, before={'publications': {}},
                               after={'publications': {'one.txt': {}}}, expected={'one.txt': {'id': 'files-open'}})
            self.assertEqual(verify_window_routing(xctest, publication, root)['status'], 'passed')
            for field in ('restart_before_read', 'reopened_from_on_my_tablet', 'secondary_app_settings_preserved'):
                invalid = dict(proof, **{field: False})
                log.write_text('[IncomingFiles] ipad-window-routing-proof\n' + json.dumps(invalid) + '\n')
                with self.assertRaises(ValueError):
                    verify_window_routing(xctest, publication, root)
            log.write_text('[IncomingFiles] ipad-window-routing-proof\n' + json.dumps(proof) + '\n')
            publication['after']['publications']['two.txt'] = {}
            with self.assertRaises(ValueError):
                verify_window_routing(xctest, publication, root)

    def test_android_plan_keeps_phone_tablet_cleanup_and_normal_build_separate(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            java = root / 'java'
            (java / 'bin').mkdir(parents=True)
            (java / 'bin/java').touch()
            project = SimpleNamespace(root=root, mobile=root / 'mobile_build',
                                      results_directory=root / 'test-results/build-manager',
                                      backend_options=lambda *args: ['This Mac — Android Emulator'])
            workspace = root / 'mobile_build/.tools/build-manager/workspaces/android'
            options = {'tools.xcode': '', 'tools.android_sdk': str(root / 'sdk'),
                       'tools.java': str(java), 'tools.mobile_python': '/selected/python', 'android.avd': ''}
            with patch('build_manager.android_emulators.AndroidEmulator.inspect', return_value='HVF usable') as inspect:
                result = plan(project, 'android', {'fingerprint': 'a' * 64}, root, workspace, options, {})
            inspect.assert_called_once()
            phases = {phase.id: phase for phase in result.phases}
            self.assertEqual(set(phases), {'android-build', 'android-incoming-phone', 'android-incoming-tablet',
                'android-incoming-phone-cleanup', 'android-incoming-tablet-cleanup', 'android-incoming-build-cleanup'})
            self.assertIn('prepare', phases['android-build'].argv)
            self.assertNotIn('--test', phases['android-build'].argv)
            self.assertEqual(phases['android-incoming-tablet'].dependencies,
                             ('android-build', 'android-incoming-phone-cleanup'))
            for name in ('android-incoming-phone-cleanup', 'android-incoming-tablet-cleanup', 'android-incoming-build-cleanup'):
                self.assertTrue(phases[name].always)
                self.assertEqual(phases[name].kind, 'cleanup')
            self.assertEqual(result.source['incoming_profiles'],
                             [dict(profile='phone', model='pixel_9'), dict(profile='tablet', model='pixel_tablet')])

    def test_incoming_selection_cannot_be_hosted_or_narrowed_to_one_filename(self):
        from logistics_build.manager_suites import selection
        root = Path(__file__).resolve().parents[3]
        for platform in ('ios', 'android'):
            with self.assertRaisesRegex(ValueError, 'local host'):
                selection(root, platform + '.incoming', 'Test', platform, 'GitHub', '')
            with self.assertRaisesRegex(ValueError, 'cannot narrow'):
                selection(root, platform + '.incoming', 'Test', platform, 'This Mac', 'test_one.py')

    def test_simulator_cleanup_requires_matched_lease_and_preserves_main_app_device(self):
        class Client:
            def __init__(self, main_installed=False):
                self.apps = {QA_BUNDLE: {}, SENDER_BUNDLE: {}}
                if main_installed:
                    self.apps[MAIN_BUNDLE] = {}
                self.removed = False
                self.calls = []

            def matching(self, device, name):
                self.calls.append(('match', device, name))
                return None if self.removed else {'state': 'Booted'}

            def invoke(self, action, device, bundle):
                self.calls.append((action, device, bundle))
                self.apps.pop(bundle)

            def remove(self, device, name):
                self.calls.append(('remove', device, name))
                self.removed = True

        with TemporaryDirectory() as directory:
            root = Path(directory)
            value = dict(device='00000000-0000-0000-0000-000000000001',
                         name='Build Manager iphone ' + 'a' * 32, role='iphone')
            path = root / 'iphone-lease.json'
            path.write_text(json.dumps(value))
            client = Client()
            with patch('logistics_build.incoming_acceptance.ios_apps', side_effect=lambda *args: dict(client.apps)):
                result = cleanup_ios(client, root, root / 'cleanup.json')
            self.assertTrue(result[0]['removed'])
            self.assertEqual(client.apps, {})
            self.assertFalse(path.exists())
            self.assertTrue((root / 'iphone-removed-lease.json').is_file())
            self.assertEqual([call[2] for call in client.calls if call[0] == 'uninstall'], [QA_BUNDLE, SENDER_BUNDLE])
            path.write_text(json.dumps(value))
            client = Client(main_installed=True)
            original = dict(client.apps)
            with patch('logistics_build.incoming_acceptance.ios_apps', return_value=dict(client.apps)):
                with self.assertRaisesRegex(RuntimeError, 'cleanup incomplete'):
                    cleanup_ios(client, root, root / 'cleanup-main.json')
            self.assertEqual(client.apps, original)
            self.assertFalse(client.removed)
            self.assertTrue(path.exists())

    def test_identity_overlay_preserves_app_group_and_document_registration(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            pbx = root / 'App.xcodeproj/project.pbxproj'
            pbx.parent.mkdir()
            pbx.write_bytes(plistlib.dumps({'objects': {
                'app': {'buildSettings': {'PRODUCT_BUNDLE_IDENTIFIER': MAIN_BUNDLE}},
                'extension': {'buildSettings': {'PRODUCT_BUNDLE_IDENTIFIER': MAIN_BUNDLE + '.inbox'}},
                'other': {'buildSettings': {'PRODUCT_BUNDLE_IDENTIFIER': 'other.application'}},
            }}))
            group = root / 'Main.entitlements'
            original = plistlib.dumps({'com.apple.security.application-groups': ['group.' + MAIN_BUNDLE]})
            group.write_bytes(original)
            info = root / 'Main-Info.plist'
            document_types = [{'CFBundleTypeRole': 'Viewer', 'LSItemContentTypes': ['public.data']}]
            info.write_bytes(plistlib.dumps({'CFBundleIdentifier': MAIN_BUNDLE,
                                            'CFBundleDocumentTypes': document_types}))
            ios_identity(root)
            values = plistlib.loads(pbx.read_bytes())['objects']
            self.assertEqual(values['app']['buildSettings']['PRODUCT_BUNDLE_IDENTIFIER'], QA_BUNDLE)
            self.assertEqual(values['extension']['buildSettings']['PRODUCT_BUNDLE_IDENTIFIER'], QA_BUNDLE + '.inbox')
            self.assertEqual(values['other']['buildSettings']['PRODUCT_BUNDLE_IDENTIFIER'], 'other.application')
            self.assertEqual(group.read_bytes(), original)
            self.assertEqual(plistlib.loads(info.read_bytes())['CFBundleDocumentTypes'], document_types)

    def test_shutdown_or_uninspectable_simulator_preserves_main_app_and_reports_remaining_lease(self):
        from unittest.mock import Mock
        with TemporaryDirectory() as directory:
            root = Path(directory)
            record = dict(device='00000000-0000-0000-0000-000000000002',
                          name='Build Manager ipad ' + 'b' * 32, role='ipad')
            path = root / 'ipad-lease.json'
            path.write_text(json.dumps(record))
            for state, apps in (('Shutdown', {MAIN_BUNDLE: {}}), ('Shutdown', RuntimeError('Inspection unavailable')),
                                ('Booted', RuntimeError('Inspection unavailable'))):
                with self.subTest(state=state, apps=type(apps).__name__):
                    client = Mock()
                    client.matching.return_value = dict(state=state)
                    with patch('logistics_build.incoming_acceptance.ios_apps',
                               **({'side_effect': apps} if isinstance(apps, Exception) else {'return_value': apps})):
                        with self.assertRaisesRegex(RuntimeError, 'cleanup incomplete'):
                            cleanup_ios(client, root, root / 'cleanup.json')
                    client.remove.assert_not_called()
                    client.invoke.assert_not_called()
                    self.assertTrue(path.is_file())
                    receipt = json.loads((root / 'cleanup.json').read_text())
                    self.assertFalse(receipt[0]['removed'])
                    self.assertIn('preserving', receipt[0]['error'])

    def test_standalone_simulator_cleanup_locks_only_the_owned_pair(self):
        from build_manager.locking import operation_lock_path, workspace_lock
        from logistics_build.incoming_acceptance import main
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / 'ios/simulators-example'
            workspace.mkdir(parents=True)
            recipe = root / 'recipe.json'
            recipe.write_text('{}')
            pair_lock = operation_lock_path(workspace)

            def checked_lock(path):
                self.assertEqual(path, pair_lock)
                return workspace_lock(path, timeout=.01)

            def inspect_lock(*args):
                with self.assertRaises(RuntimeError):
                    with workspace_lock(pair_lock, timeout=.01):
                        self.fail('Cleanup did not own its pair lock')

            argv = ['incoming_acceptance', 'cleanup-devices', '--platform', 'ios', '--profile', 'iphone',
                    '--workspace', str(workspace), '--output', str(root / 'output'), '--recipe', str(recipe)]
            with workspace_lock(workspace.parent / 'operation.lock'):
                with patch('sys.argv', argv), patch('signal.signal'), \
                     patch('build_manager.apple_simulators.AppleSimulators'), \
                     patch('build_manager.locking.workspace_lock', side_effect=checked_lock), \
                     patch('logistics_build.incoming_acceptance.cleanup_ios', side_effect=inspect_lock) as cleanup_call:
                    main()
                cleanup_call.assert_called_once()
            with workspace_lock(pair_lock, timeout=.01):
                pass

    def test_receiver_verification_rejects_probe_launcher_and_missing_extension(self):
        with TemporaryDirectory() as directory:
            app = Path(directory)
            (app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': QA_BUNDLE,
                                                          'MainModule': 'logisticsmobile'}))
            launcher = app / 'app/logisticsmobile/__main__.py'
            launcher.parent.mkdir(parents=True)
            launcher.write_text('from mobile.app import main\n\nmain().main_loop()\n')
            with self.assertRaisesRegex(ValueError, 'Share extension'):
                verify_ios(app)
            info = app / 'PlugIns/LogisticsInbox.appex/Info.plist'
            info.parent.mkdir(parents=True)
            info.write_bytes(plistlib.dumps({'CFBundleIdentifier': QA_BUNDLE + '.inbox',
                'NSExtension': {'NSExtensionPointIdentifier': 'com.apple.share-services'}}))
            self.assertEqual(verify_ios(app)['bundle'], QA_BUNDLE)
            launcher.write_text('from tests.fake_receiver import main\nmain()\n')
            with self.assertRaisesRegex(ValueError, 'ordinary application'):
                verify_ios(app)

    def test_cleanup_rejects_unowned_workspace_and_main_app_identity(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / 'test-results/build-scratch/run-test'
            workspace.mkdir(parents=True)
            sentinel = workspace / 'preserve'
            sentinel.write_text('not owned')
            recipe = root / 'recipe.json'
            value = dict(schema=1, bundle=QA_BUNDLE, root=str(root), workspace=str(workspace))
            recipe.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'ownership'):
                cleanup(recipe)
            self.assertTrue(sentinel.exists())
            (workspace / '.manager-scratch').touch()
            recipe.write_text(json.dumps(dict(value, bundle=MAIN_BUNDLE)))
            with self.assertRaisesRegex(ValueError, 'unowned'):
                cleanup(recipe)
            self.assertTrue(sentinel.exists())


if __name__ == '__main__':
    unittest.main()
