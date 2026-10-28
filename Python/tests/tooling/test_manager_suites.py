from build_manager.test_manifest import discover as _discover
"""Named suite routing and required release evidence; no live provider/device work."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from build_manager import Phase, Plan
from build_manager.test_results import read_junit
from logistics_build import manager_suites as suites
from logistics_build.build_project import LogisticsProject

ROOT = Path(__file__).resolve().parents[3]


class ManagerSuiteTests(unittest.TestCase):
    def test_host_report_plan_declares_files_without_running_discovery(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite = root / 'suite'
            (suite / 'nested').mkdir(parents=True)
            (suite / 'test_live_one.py').write_text('raise AssertionError("inventory must not import tests")')
            (suite / 'nested/test_live_two.py').write_text('raise AssertionError("inventory must not import tests")')
            (suite / 'test_other.py').write_text('')
            phase = Phase('shared', (sys.executable, 'Python/tests/run_regressions.py', 'suite',
                '--isolate-modules', '--include-pattern', 'test_live*'), str(root))
            plan = Plan('Fixture', 'Test', {}, (phase,), str(root))
            planned = suites.with_reports(plan, 'android')
            self.assertEqual(planned.phases[0].test_files, ('nested/test_live_two.py', 'test_live_one.py'))

    def test_catalog_selection_rejects_unknown_inapplicable_and_remote_suites(self):
        suites.selection(ROOT, 'portable.contracts', 'Test', 'macos', 'This Mac', 'test_manager*.py')
        for suite, operation, target, backend, pattern in (
            ('unknown', 'Test', 'macos', 'This Mac', ''),
            ('ios.native', 'Test', 'android', 'This Mac', ''),
            ('portable.contracts', 'Test', 'macos', 'GitHub', ''),
            ('release.acceptance', 'Reviewed Firebase workflow', 'android', 'This Mac', 'test_*.py')):
            with self.subTest(suite=suite, backend=backend), self.assertRaises(ValueError):
                suites.selection(ROOT, suite, operation, target, backend, pattern)

    def test_ios_runtime_suite_keeps_only_core_gates_and_generated_receipt(self):
        project = LogisticsProject(ROOT)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            phases = (
                Phase('ios-build', (sys.executable, '-c', 'pass'), str(root), kind='build'),
                Phase('iphone', (sys.executable, '-c', 'pass'), str(root), dependencies=('ios-build',), artifacts=(str(root/'iphone.json'),)),
                Phase('iphone-cleanup', (sys.executable, '-c', 'pass'), str(root), dependencies=('iphone',), always=True, kind='cleanup'),
                Phase('ios-runtime-tools', (sys.executable, '-c', 'pass'), str(root), kind='setup'),
                Phase('ios-runtime', (sys.executable, '-c', 'pass'), str(root), dependencies=('ios-runtime-tools','iphone-cleanup'), artifacts=(str(root/'core.json'),)),
                Phase('ios-runtime-cleanup', (sys.executable, '-c', 'pass'), str(root), dependencies=('ios-runtime',), always=True, kind='cleanup'))
            full = Plan('Logistics', 'Test', {}, phases, str(root))
            with patch.object(project, '_make_plan', return_value=full), patch('logistics_build.build_retention.clean'):
                core = project.make_plan('Test', 'ios', 'This Mac — iOS Simulators', suite='ios.runtime')
                native = project.make_plan('Test', 'ios', 'This Mac — iOS Simulators', suite='ios.native')
            self.assertEqual([p.id for p in core.phases], ['ios-runtime-tools','ios-runtime','ios-runtime-cleanup'])
            self.assertEqual(core.phases[1].dependencies, ('ios-runtime-tools',))
            self.assertIn('--runtime', core.phases[1].argv)
            self.assertEqual([p.id for p in native.phases], ['ios-build','iphone','iphone-cleanup'])
            with patch.dict('os.environ', LOGISTICS_IOS_RUNTIME_EVIDENCE='wrong-external-receipt.json'):
                gate = suites.acceptance_phase(core, 'ios')
            self.assertEqual(gate.argv[gate.argv.index('--runtime-report')+1], str(root/'core.json'))
            self.assertIn('ios-runtime-cleanup', gate.dependencies)

    def test_selected_desktop_suite_reaches_only_its_declared_directory_and_pattern(self):
        project = LogisticsProject(ROOT)
        from mobile_build.deployment.manager_settings import defaults
        values = defaults(project.mobile)
        values['tools.desktop_python'] = sys.executable
        identity = dict(logistics_commit='a', commonUtils_commit='b', fingerprint='fixture', dirty=False)
        with patch('logistics_build.build_project.sys.platform', 'darwin'), patch('logistics_build.build_retention.clean'), patch('logistics_build.build_project.identity', return_value=identity), \
                patch('logistics_build.build_project.materialize'), patch('logistics_build.build_project.manager_settings.settings', return_value=(values, {})), \
                patch('logistics_build.build_project.manager_settings.app_version', return_value='1.0.0'), \
                patch('build_manager.local.inspect_python', return_value={'system': 'Darwin'}), \
                patch('logistics_build.build_project.platform.system', return_value='Darwin'):
            plan = project.make_plan('Test', 'macos', 'This Mac', suite='portable.contracts', pattern='test_manager*.py')
        phase = plan.phases[-1]
        self.assertEqual([row.id for row in plan.phases], ['environment', 'portable.contracts'])
        self.assertIn('Python/tests/tooling', phase.argv)
        self.assertIn('test_manager*.py', phase.argv)
        self.assertIn('junit', phase.artifact_types.values())
        self.assertEqual(plan.source['test_suite'], 'portable.contracts')

    def test_real_isolated_runner_retains_failure_skip_and_duration(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'test_fixture.py').write_text('import unittest\nclass Cases(unittest.TestCase):\n'
                ' def test_pass(self): pass\n def test_fail(self): self.fail("expected evidence")\n'
                ' @unittest.skip("host absent")\n def test_skip(self): pass\n')
            output = root / 'cases.xml'
            result = subprocess.run([sys.executable, str(ROOT / 'Python/tests/run_regressions.py'), str(root),
                '--isolate-modules', '--junit', str(output), '--report', str(root / 'timing.json')],
                capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            cases = read_junit(output)
            self.assertIn('failed', [case['status'] for case in cases])
            self.assertIn('skipped', [case['status'] for case in cases])
            self.assertIn('expected evidence', '\n'.join(case['message'] for case in cases))
            self.assertTrue(all(case['seconds'] is not None for case in cases))

    def fixtures(self, root, target='android'):
        source = dict(logistics_commit='a', commonUtils_commit='b', dirty=False)
        (root / '.manager-source.json').write_text(json.dumps({'source': source}))
        path = root / 'mobile_build/native_tests/tests/logisticsmobile/__init__.py'
        path.parent.mkdir(parents=True)
        path.write_text("CASES=('native_one','native_two')\n")
        path = root / 'Python/mobile/smoke.py'
        path.parent.mkdir(parents=True)
        path.write_text("EXPECTED_TESTS=('runtime_one','runtime_two')\n")
        native = dict(schema=1, suite='logistics-native-ui', target=target, source=source, success=True,
                      cases=['native_one','native_two'], expected_cases=['native_one','native_two'])
        runtime = dict(schema=1, suite='logistics-mobile-documents', target=target, sys_platform=target, source=source,
                       success=True, expected_tests=['runtime_one','runtime_two'], tests_run=2, failures=0, errors=0, skipped=0)
        a, b = root / 'native.json', root / 'runtime.json'
        a.write_text(json.dumps(native));b.write_text(json.dumps(runtime))
        return a, b, native, runtime

    def test_complete_android_evidence_passes_but_missing_skips_or_wrong_source_fail(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            a, b, native, runtime = self.fixtures(root)
            self.assertEqual(suites.release_evidence(root, 'android', [a], b)['status'], 'passed')
            for field, value in [('skipped', 1), ('tests_run', 1), ('sys_platform', 'darwin')]:
                changed = dict(runtime, **{field: value})
                b.write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    suites.release_evidence(root, 'android', [a], b)
            b.unlink()
            with self.assertRaisesRegex(ValueError, 'runtime evidence'):
                suites.release_evidence(root, 'android', [a], b)
            self.assertTrue(all(case['seconds'] is None for case in suites.native_cases(native, root, 'android')))

    def test_captured_dirty_release_evidence_requires_exact_snapshot_fingerprint(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            a, b, native, runtime = self.fixtures(root)
            source = dict(logistics_commit='a', commonUtils_commit='b', dirty=True, fingerprint='c'*64)
            (root/'.manager-source.json').write_text(json.dumps({'source':source}))
            staged = dict(source, manager_source_fingerprint='c'*64, source_sha256='d'*64)
            native['source'] = staged
            runtime['source'] = staged
            a.write_text(json.dumps(native)); b.write_text(json.dumps(runtime))
            self.assertEqual(suites.release_evidence(root, 'android', [a], b)['status'], 'passed')
            for bad in (dict(staged, manager_source_fingerprint='e'*64),
                        dict(staged, manager_source_fingerprint=''),
                        dict(staged, source_sha256=''),
                        dict(staged, logistics_commit='wrong')):
                runtime['source'] = bad
                b.write_text(json.dumps(runtime))
                with self.assertRaisesRegex(ValueError, 'Runtime source'):
                    suites.release_evidence(root, 'android', [a], b)

    def test_staging_binds_only_unchanged_manager_snapshot(self):
        from mobile_build.tools import captured_source_fingerprint
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIsNone(captured_source_fingerprint(root))
            (root/'.manager-source.json').write_text(json.dumps(dict(
                source={'fingerprint':'a'*64}, snapshot_fingerprint='b'*64)))
            with patch('logistics_build.build_snapshots.identity', return_value={'fingerprint':'b'*64}):
                self.assertEqual(captured_source_fingerprint(root), 'a'*64)
            with patch('logistics_build.build_snapshots.identity', return_value={'fingerprint':'c'*64}):
                with self.assertRaisesRegex(ValueError, 'Captured source changed'):
                    captured_source_fingerprint(root)

    def test_ios_acceptance_requires_all_device_families_cleanup_and_actual_runtime(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            a, runtime, native, _ = self.fixtures(root, 'ios')
            paths = []
            for kind in ('iphone', 'duo'):
                path = root / (kind + '.json')
                path.write_text(json.dumps(dict(kind=kind, status='passed', owned_simulator_removed=True, report=native)))
                paths.append(path)
            self.assertEqual(suites.release_evidence(root, 'ios', paths, runtime)['status'], 'passed')
            with self.assertRaisesRegex(ValueError, 'device-family'):
                suites.release_evidence(root, 'ios', paths[:1], runtime)
            with self.assertRaisesRegex(ValueError, 'device-family'):
                suites.release_evidence(root, 'ios', paths, runtime, require_ipad=True)
            record = json.loads(paths[0].read_text());record['owned_simulator_removed'] = False
            paths[0].write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, 'cleanup'):
                suites.release_evidence(root, 'ios', paths, runtime)

    def test_reviewed_workflow_depends_on_native_runtime_gate_and_prepared_artifact(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = LogisticsProject(root)
            source = dict(logistics_commit='a', commonUtils_commit='b', fingerprint='fixed', dirty=False)
            build = Phase('prepare-verified-artifact', (sys.executable, '-c', 'pass'), str(root), kind='build', artifacts=(str(root/'prepared.json'),))
            native = Phase('android-native', (sys.executable, '-c', 'pass'), str(root), artifacts=(str(root/'native.json'),))
            runtime = Phase('android-runtime', (sys.executable, '-c', 'pass'), str(root), artifacts=(str(root/'runtime.json'),))
            prepared = Plan('Logistics', 'Prepare Firebase', source, (build,), str(root/'workspace'), effect='build')
            tests = Plan('Logistics', 'Test', source, (native, runtime), str(root/'workspace'))
            with patch('build_manager.test_manifest.discover', side_effect=lambda root, group: _discover(Path(__file__).resolve().parents[3], group)), patch('logistics_build.build_retention.clean'), patch.object(project, '_make_plan', side_effect=[prepared, tests]):
                plan = project.make_plan('Reviewed Firebase workflow', 'android', 'This Mac')
            rows = {phase.id: phase for phase in plan.phases}
            self.assertEqual(rows['release-acceptance'].dependencies, ('commonutils','portable-contracts','desktop-ui','mobile-host','android-native','android-runtime'))
            self.assertEqual(rows['android-native'].dependencies, ('commonutils','portable-contracts','desktop-ui','mobile-host'))
            self.assertEqual(rows['android-runtime'].dependencies, ('commonutils','portable-contracts','desktop-ui','mobile-host'))
            self.assertIn('Python/tests/tooling', rows['portable-contracts'].argv)
            self.assertIn('Python/tests/application', rows['desktop-ui'].argv)
            self.assertIn('mobile_build/tests', rows['mobile-host'].argv)
            self.assertIn('release-acceptance', rows['prepare-verified-artifact'].dependencies)
            self.assertEqual(rows['reviewed-distribution'].dependencies, ('prepare-verified-artifact',))
            self.assertEqual(rows['reviewed-distribution'].effect, 'upload')
            self.assertNotIn('host.mobile-device-session', plan.resources)
            device_resource = 'android.device-workspace:' + plan.workspace
            for name in ('android-native', 'android-runtime'):
                self.assertEqual(rows[name].resources[device_resource], 1)
            self.assertFalse(rows['portable-contracts'].resources)
            self.assertEqual(rows['prepare-verified-artifact'].resources['host.mobile-build'], 1)
            self.assertEqual(rows['prepare-verified-artifact'].resources['host.signing-keychain'], 1)
            self.assertEqual(rows['reviewed-distribution'].resources['provider.destination:firebase:Logistics'], 1)

    def test_reviewed_ios_forces_required_ipad_coverage(self):
        with TemporaryDirectory() as directory:
            root = Path(directory);project = LogisticsProject(root)
            source = dict(logistics_commit='a', commonUtils_commit='b', fingerprint='fixed', dirty=False)
            build = Phase('prepare-verified-artifact', (sys.executable,'-c','pass'),str(root),kind='build',artifacts=(str(root/'prepared.json'),))
            phases = tuple(Phase(kind,(sys.executable,'-c','pass'),str(root),artifacts=(str(root/(kind+'.json')),)) for kind in ('iphone','duo','ipad'))
            prepared = Plan('Logistics','Prepare TestFlight',source,(build,),str(root/'workspace'),effect='build')
            native = Plan('Logistics','Test',source,phases,str(root/'workspace'))
            with patch('build_manager.test_manifest.discover', side_effect=lambda root, group: _discover(Path(__file__).resolve().parents[3], group)), patch('logistics_build.build_retention.clean'), patch.object(project,'_make_plan',side_effect=[prepared,native]) as make:
                plan = project.make_plan('Reviewed TestFlight workflow','ios','This Mac',include_ipad=False)
            self.assertTrue(make.call_args_list[1].kwargs['include_ipad'])
            gate = next(phase for phase in plan.phases if phase.id=='release-acceptance')
            self.assertIn('--require-ipad',gate.argv)

    def test_ios_backend_can_retry_into_retained_result_directory_with_fresh_owned_devices(self):
        from logistics_build import ios_backend
        with TemporaryDirectory() as directory:
            root = Path(directory);(root/'mobile_build').mkdir()
            (root/'.manager-source.json').write_text(json.dumps({'source':{'commit':'fixed'}}))
            result, lease = root/'retained/result.json',root/'device-lease.json'
            with patch.object(ios_backend,'AppleSimulators') as clients, patch.object(ios_backend.os,'chdir'), \
                    patch('mobile_build.validation.ui_tools.run',return_value={'success':True}):
                clients.return_value.create.return_value='owned-fixture-device'
                for attempt in range(2):
                    ios_backend.test(root,result,'iphone','fixture-model','fixture-runtime',lease)
                    self.assertEqual(json.loads(result.read_text())['status'],'passed')
                    self.assertFalse(lease.exists())
                self.assertEqual(clients.return_value.create.call_count,2)
                self.assertEqual(clients.return_value.remove.call_count,2)

    def test_ios_retry_retires_existing_lease_or_stops_without_overwriting_it(self):
        from logistics_build import ios_backend
        for blocked in (False, True):
            with self.subTest(cleanup_blocked=blocked), TemporaryDirectory() as directory:
                root=Path(directory);(root/'mobile_build').mkdir()
                (root/'.manager-source.json').write_text(json.dumps({'source':{'commit':'fixed'}}))
                result,lease=root/'retained/result.json',root/'device-lease.json'
                previous={'device':'previous-owned-uuid','name':'Build Manager previous-owned-token'}
                lease.write_text(json.dumps(previous))
                with patch.object(ios_backend,'AppleSimulators') as clients, patch.object(ios_backend.os,'chdir'), \
                     patch('mobile_build.validation.ui_tools.run',return_value={'success':True}):
                    clients.return_value.create.return_value='new-owned-uuid'
                    if blocked:
                        clients.return_value.remove.side_effect=RuntimeError('verified cleanup blocked')
                        with self.assertRaisesRegex(RuntimeError,'cleanup blocked'):
                            ios_backend.test(root,result,'iphone','fixture-model','fixture-runtime',lease)
                        clients.return_value.create.assert_not_called()
                        self.assertEqual(json.loads(lease.read_text()),previous)
                    else:
                        ios_backend.test(root,result,'iphone','fixture-model','fixture-runtime',lease)
                        self.assertEqual(clients.return_value.remove.call_args_list[0].args,
                                         ('previous-owned-uuid','Build Manager previous-owned-token'))
                        self.assertFalse(lease.exists())
