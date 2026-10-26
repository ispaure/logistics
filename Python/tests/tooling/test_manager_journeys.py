"""Project-owned combined plans; native tools/providers never run in these tests."""
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from build_manager import Executor, Phase, Plan
from build_manager.test_manifest import discover as _discover
from build_manager.journeys import for_host, validate_plan
from build_manager.workflows import ancestors, approve
from Scripts.build_project import LogisticsProject
from Scripts.manager_journeys import PlanningContext

ROOT = Path(__file__).resolve().parents[3]


class FixtureProject(LogisticsProject):
    def __init__(self, root):
        super().__init__(root)
        self.calls = []
        self.interpreter = Path(sys.executable)

    def _make_plan(self, operation, target, backend, *, _context=None, revision='working-tree', include_ipad=False, **options):
        self.calls.append((operation, target, _context, include_ipad))
        source = _context.source(self, revision)
        workspace = self.private / 'workspaces' / target
        env = {'FIXTURE': 'non-secret'}
        def phase(name, kind='test', deps=(), always=False):
            return Phase(name, (sys.executable, '-c', 'pass'), str(self.root), dependencies=deps,
                         kind=kind, always=always, environment=env,
                         artifacts=() if always else (str(workspace / (name + '.json')),))
        if operation == 'Test':
            names = ('android-native', 'android-runtime') if target == 'android' else (
                ('iphone', 'duo', 'ipad', 'ios-runtime') if include_ipad else ('iphone', 'duo', 'ios-runtime')) if target == 'ios' else ('desktop',)
            phases = (phase('build', 'build'), *(phase(name, deps=('build',)) for name in names),
                      phase('cleanup', 'cleanup', always=True))
            return Plan('Logistics', 'Test', source, phases, str(workspace), backend=backend)
        if operation == 'Release':
            return Plan('Logistics', operation, source, (phase('release-source-and-gates'),), str(workspace), backend='GitHub', effect='publish')
        return Plan('Logistics', operation, source, (phase('prepare-verified-artifact', 'build'),), str(workspace), backend=backend, effect='build')


class JourneyAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        descriptor = json.loads((ROOT / 'build-project.json').read_text())
        (self.root / 'build-project.json').write_text(json.dumps(descriptor))
        self.values = {'tools.desktop_python': sys.executable, 'tools.mobile_python': sys.executable,
                       'auth.github_reference': 'GH_TOKEN', 'vm.linux_scope': 'both', 'github.repository': 'fixture/repo',
                       'testflight.app_id': 'fixture-ios', 'testflight.external_group': 'Fixture testers',
                       'firebase.app_id': 'fixture-android', 'firebase.group': 'Fixture testers'}
        self.source = dict(logistics_commit='a' * 40, commonUtils_commit='b' * 40, dirty=False, fingerprint='fixture', selection='HEAD')
        for target, options in (
                ('build_manager.test_manifest.discover', {'side_effect': lambda root, group: _discover(ROOT, group)}),
                ('Scripts.build_retention.clean', {'return_value': []}),
                ('Scripts.build_project.identity', {'return_value': self.source}),
                ('Scripts.build_project.manager_settings.settings', {'side_effect': lambda *_, **kwargs: (dict(self.values, **kwargs.get('overrides', {})), {})}),
                ('Scripts.build_project.manager_settings.defaults', {'side_effect': lambda *_: dict(self.values)}),
                ('Scripts.build_project.manager_settings.app_version', {'return_value': '1.2.3'}),
                ('Scripts.build_project.sys.platform', {'new': 'darwin'})):
            patcher = patch(target, **options); patcher.start(); self.addCleanup(patcher.stop)
        # Resolve capability defaults under the same declared host used below.
        # Constructing first captured Linux/Windows backends on those CI hosts.
        self.project = FixtureProject(self.root)

    def make(self, goal='deliver', platforms=None, destinations=None, **options):
        return self.project.make_journey(goal, platforms or ['android', 'ios'],
            destinations if destinations is not None else ['firebase', 'testflight'], revision='HEAD', **options)

    def test_development_device_destination_is_scoped_and_allows_captured_local_edits(self):
        self.source['dirty'] = True
        def device_plan(project, target, recipients, context, revision):
            build = Phase('prepare-device-app', (sys.executable, '-c', 'pass'), str(self.root), effect='build', kind='build')
            install = Phase('install-phone', (sys.executable, '-c', 'pass'), str(self.root), effect='deploy', dependencies=(build.id,))
            return Plan('Logistics', 'Device app', context.source(project, revision), (build, install), str(self.root / 'devices'))
        with patch('Scripts.manager_devices.make_plan', side_effect=device_plan) as make:
            plan = self.make(platforms=['android'], destinations=['android-devices'], run_overrides={'devices.android':'["serial-1"]'})
        self.assertIn('android.validated', ancestors(plan, 'android.devices.install-phone'))
        self.assertEqual(plan.journey['destinations']['android-devices']['platforms'], ['android'])
        self.assertEqual(make.call_args.args[2][0]['id'], 'serial-1')
        self.assertTrue(plan.source['dirty'])
        self.assertNotIn('android.validation.release-acceptance', {phase.id for phase in plan.phases})
        validate_plan(plan)

    def test_shared_tester_message_maps_to_both_owned_service_fields(self):
        from Scripts.manager_journeys import run_values
        self.assertEqual(run_values({'testers.message': 'Try search'}),
            {'firebase.release_notes': 'Try search', 'testflight.what_to_test': 'Try search'})
        self.assertEqual(run_values({'testers.message': ''}),
            {'firebase.release_notes': '', 'testflight.what_to_test': ''})

    def test_shared_capture_and_destination_platform_gates_precede_their_delivery(self):
        plan = self.make()
        validate_plan(plan)
        contexts = [call[2] for call in self.project.calls]
        self.assertTrue(all(context is contexts[0] for context in contexts))
        self.assertIsInstance(contexts[0], PlanningContext)
        self.assertTrue(next(call[3] for call in self.project.calls if call[:2] == ('Test', 'ios')))
        names = {phase.id for phase in plan.phases}
        self.assertIn('ios.validation.ipad', names)
        for target in ('ios', 'android'):
            for consumer in ('portable-contracts', 'desktop-ui', 'mobile-host'):
                self.assertIn(target + '.validation.commonutils', ancestors(plan, target + '.validation.' + consumer))
            self.assertIn(target + '.validation.commonutils', ancestors(plan, target + '.validated'))
        self.assertIn('android.validation.release-acceptance', names)
        self.assertIn('ios.validation.release-acceptance', names)
        for name, target in (('firebase.upload', 'android'), ('testflight.upload', 'ios')):
            self.assertIn(target + '.validated', ancestors(plan, name))
            other = 'ios' if target == 'android' else 'android'
            self.assertNotIn(other + '.validated', ancestors(plan, name))
        self.assertEqual(sum(phase.id.endswith('.prepare-verified-artifact') for phase in plan.phases), 2)
        for phase in plan.phases:
            if '.preparation.' in phase.id:
                target = phase.id.split('.')[0]
                self.assertIn(target + '.validated', ancestors(plan, phase.id))
        self.assertNotIn('android.validated', ancestors(plan, 'ios.validation.build'))
        admission = next(p for p in plan.phases if p.id == 'ios.admit-validation')
        self.assertEqual(admission.waits_for, ('android.validated',))
        self.assertTrue(admission.always)
        self.assertIn(str(self.project.private / 'workspaces/android/operation.lock'), plan.resource_locks)

    def test_validation_has_no_preparation_or_external_effects_and_no_cleanup_deadlock(self):
        plan = self.make('validate', destinations=[])
        self.assertEqual(plan.journey['destinations'], {})
        self.assertFalse(any(p.effect in {'publish', 'upload', 'deploy'} for p in plan.phases))
        self.assertFalse(any('.preparation.' in p.id for p in plan.phases))
        self.assertTrue(next(p for p in plan.phases if p.id == 'android.validation.cleanup').dependencies)
        self.assertFalse(any(call[0] != 'Test' for call in self.project.calls))

    def test_actual_dependency_graph_pauses_and_reuses_preparation_for_reviewed_delivery(self):
        plan = self.make()
        # Exercise the real produced graph/scheduler with harmless commands,
        # removing native expected reports rather than fabricating native evidence.
        def command(phase):
            if phase.effect == 'upload':
                target = self.root / (phase.id + '.json')
                # Both uploads must enter before either can finish. A fixed
                # sleep can miss overlap when a busy host delays child startup.
                ready = [self.root / (name + '.ready') for name in ('firebase', 'testflight')]
                own = ready[0 if phase.id == 'firebase.upload' else 1]
                script = ('import json,time\nfrom pathlib import Path\n'
                    # Windows wall-clock timestamps can share a coarse tick.
                    # QPC-backed integer intervals retain the strict overlap check.
                    'start=time.perf_counter_ns()\ndeadline=time.monotonic()+30\n'
                    f'Path({str(own)!r}).touch()\n'
                    f'while not all(Path(p).exists() for p in {[str(p) for p in ready]!r}):\n'
                    '    assert time.monotonic()<deadline, "Uploads did not execute concurrently"\n'
                    '    time.sleep(.01)\n'
                    f'Path({str(target)!r}).write_text(json.dumps([start,time.perf_counter_ns()]))')
                return (sys.executable, '-c', script)
            return (sys.executable, '-c', 'pass')
        phases = tuple(replace(p, argv=command(p), artifacts=(), artifact_types={}, environment={}) for p in plan.phases)
        plan = replace(plan, phases=phases)
        executor = Executor(resource_directory=self.root / 'resources')
        first = executor.run(plan, self.root / 'result')
        self.assertEqual(first['status'], 'awaiting_review')
        self.assertEqual(first['phases'][-1]['status'], 'awaiting_review')
        approvals = tuple(approve(plan, name, first) for name in ('firebase.upload', 'testflight.upload'))
        last = executor.run(plan, self.root / 'result', resume=True, approvals=approvals)
        self.assertEqual(last['status'], 'passed')
        a, b = [json.loads((self.root / (name + '.upload.json')).read_text()) for name in ('firebase', 'testflight')]
        self.assertLess(max(a[0], b[0]), min(a[1], b[1]))
        retained = {row['id']: row for row in first['phases'] if row['status'] == 'passed'}
        self.assertTrue(all(row['started_at'] == retained[row['id']]['started_at'] for row in last['phases'] if row['id'] in retained))

    def test_failed_android_blocks_firebase_but_ios_can_prepare_and_deliver(self):
        plan = self.make()
        phases = tuple(replace(p, argv=(sys.executable, '-c', 'raise SystemExit(1)' if p.id == 'android.validation.android-native' else 'pass'),
                               artifacts=(), artifact_types={}, environment={}) for p in plan.phases)
        report = Executor(resource_directory=self.root / 'resources').run(replace(plan, phases=phases), self.root / 'result')
        states = {row['id']: row['status'] for row in report['phases']}
        self.assertEqual(states['android.validation.cleanup'], 'passed')
        self.assertEqual(states['ios.validated'], 'passed')
        self.assertEqual(states['firebase.upload'], 'skipped')
        self.assertEqual(states['testflight.upload'], 'awaiting_review')
        scoped_plan = replace(plan, phases=phases)
        approval = approve(scoped_plan, 'testflight.upload', report)
        final = Executor(resource_directory=self.root / 'resources').run(scoped_plan, self.root / 'result',
            resume=True, approvals=(approval,))
        self.assertEqual(next(row['status'] for row in final['phases'] if row['id'] == 'testflight.upload'), 'passed')

    def test_github_publication_requires_desktop_platforms_and_has_exact_tag(self):
        with patch('Scripts.build_snapshots.git', side_effect=lambda _, *args: '' if args[0] == 'status' else self.source['logistics_commit']):
            plan = self.make(platforms=['macos', 'linux', 'windows', 'android', 'ios'],
                destinations=['github', 'firebase', 'testflight'], release_tag='v1.2.3-alpha.1')
        self.assertEqual(set(plan.journey['destinations']), {'github', 'firebase', 'testflight'})
        step = next(p for p in plan.phases if p.id == 'github.delivery.release-source-and-gates')
        self.assertEqual(step.effect, 'publish')
        required = {gate for target in ('macos', 'linux', 'windows') for gate in plan.journey['platforms'][target]}
        self.assertTrue(required.issubset(ancestors(plan, step.id)))
        self.assertNotIn('ios.validated', ancestors(plan, step.id))
        self.assertNotIn('android.validated', ancestors(plan, step.id))
        self.assertIn('v1.2.3-alpha.1', plan.journey['destinations']['github']['identity'])

    def test_dirty_source_missing_platform_focused_tests_and_changed_settings_fail_before_delivery(self):
        with self.assertRaisesRegex(ValueError, 'requires: android'):
            self.make(platforms=['ios'], destinations=['firebase'])
        with self.assertRaisesRegex(ValueError, 'complete project suites'):
            self.make(pattern='test_example.py')
        with patch('Scripts.build_project.identity', return_value=dict(self.source, dirty=True)):
            with self.assertRaisesRegex(ValueError, 'committed source'):
                self.make()
        with patch('Scripts.release_naming.suggest_tag', return_value='v1.2.3-alpha.7'), patch('Scripts.build_snapshots.git', side_effect=['','a'*40]):
            automatic = self.make(platforms=['macos', 'linux', 'windows'], destinations=['github'])
            self.assertIn('v1.2.3-alpha.7',automatic.journey['destinations']['github']['identity'])
        with patch('Scripts.manager_journeys.capture') as captured:
            baseline = dict(self.source, app_version='1.2.3', effective_settings=dict(values=self.values, origins={}))
            changed = dict(baseline, app_version='2.0.0')
            captured.side_effect = [PlanningContext(str(self.root), 'HEAD', json.dumps(value)) for value in (baseline, changed)]
            with self.assertRaisesRegex(ValueError, 'changed during combined planning'):
                self.make('validate', destinations=[])

    def test_direct_adapter_and_registered_descriptor_share_explicit_host_mapping(self):
        descriptor = json.loads((ROOT / 'build-project.json').read_text())
        linux = for_host(descriptor['journey'], 'linux')
        self.assertEqual(linux['platforms']['linux']['backend'], 'This Linux host')
        self.assertEqual(linux['platforms']['windows']['backend'], 'Local Parallels VM')
        with patch('Scripts.build_project.sys.platform', 'linux'):
            project = LogisticsProject(self.root)
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                project.make_journey('validate', ['windows'], [], revision='HEAD')

    def test_context_rejects_cross_checkout_reuse_and_external_material_in_settings(self):
        context = PlanningContext('/another/checkout', 'HEAD', '{}')
        with self.assertRaisesRegex(ValueError, 'different source'):
            context.source(self.project, 'HEAD')
        self.values['auth.password'] = 'synthetic'
        with self.assertRaisesRegex(ValueError, 'secret values'):
            self.make('validate', destinations=[])

    def test_actual_source_planner_uses_shared_context_without_recapturing(self):
        project = LogisticsProject(self.root)
        source = dict(self.source, app_version='1.2.3', effective_settings=dict(values=self.values, origins={}))
        context = PlanningContext(str(self.root), 'HEAD', json.dumps(source))
        expected = Plan('Logistics', 'Test', source,
            (Phase('fixture', (sys.executable, '-c', 'pass'), str(self.root)),), str(self.root / 'workspace'))
        with patch('Scripts.build_project.identity', side_effect=AssertionError('must use shared context')), \
                patch('Scripts.build_project.manager_settings.settings', side_effect=AssertionError('must use frozen settings')), \
                patch('Scripts.build_project.materialize') as materialize, \
                patch.object(project, 'mobile_plan', return_value=expected) as mobile:
            result = project._make_plan('Test', 'android', 'This Mac — Android Emulator', revision='HEAD', _context=context)
        self.assertEqual(result.source['fingerprint'], source['fingerprint'])
        self.assertEqual(mobile.call_args.args[2], source)
        self.assertEqual(mobile.call_args.args[5], self.values)
        materialize.assert_called_once()

    def test_real_bridge_action_serializes_the_integrated_plan_without_native_commands(self):
        import subprocess
        driver = '''import runpy,sys
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path.cwd()),str(Path.cwd()/'Python/tests/tooling')]
from test_manager_journeys import JourneyAdapterTests
case=JourneyAdapterTests();case.setUp()
try:
 with patch('Scripts.build_project.LogisticsProject',return_value=case.project):
  runpy.run_path(str(Path.cwd()/'Scripts/manager_bridge.py'),run_name='__main__')
finally:
 case.doCleanups()
'''
        payload = dict(schema=1, action='journey_plan', values=dict(revision='HEAD',
            intent=dict(schema=1, goal='validate', platforms=['android', 'ios'], destinations=[])))
        result = subprocess.run([sys.executable, '-c', driver], cwd=ROOT, input=json.dumps(payload),
            text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertEqual(response['schema'], 1)
        plan = Plan.from_data(response['result'])
        self.assertEqual(set(plan.journey['platforms']), {'android', 'ios'})
        self.assertEqual(plan.journey['destinations'], {})

    def test_unknown_declared_destination_cannot_fall_back_to_firebase(self):
        self.project.journey_capability['destinations']['new-provider'] = dict(label='Future provider', platforms=['android'])
        with self.assertRaisesRegex(ValueError, 'no reviewed integrated delivery'):
            self.make(destinations=['new-provider'])
        self.assertEqual(self.project.calls, [])

    def test_older_manager_retains_legacy_operations_and_explains_missing_journey_support(self):
        with patch.dict(sys.modules, {'build_manager.journeys': None}):
            project = LogisticsProject(self.root)
        self.assertIsNone(project.journey_capability)
        self.assertIn('Test', project.operations_for('android'))
        with self.assertRaisesRegex(RuntimeError, 'Install the reviewed local'):
            project.make_journey('validate', ['android'], [], revision='HEAD')
