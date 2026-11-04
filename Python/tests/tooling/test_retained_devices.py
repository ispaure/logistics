"""Retained delivery preserves source/evidence and separately reviews device effects."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from build_manager import Phase, Plan
from commonUtils.runtime.streams import file_sha256
from logistics_build import manager_devices as devices
from logistics_build import retained_devices as retained


class RetainedDeviceTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = (Path(self.directory.name) / 'project').resolve(); self.root.mkdir()
        self.mobile = self.root / 'mobile_build'; self.mobile.mkdir()
        self.private = self.mobile / '.tools/build-manager'; self.private.mkdir(parents=True)
        self.run = self.root / 'original-run'; self.run.mkdir()
        self.source = dict(logistics_commit='1' * 40, commonUtils_commit='2' * 40,
            dirty=True, commonUtils_dirty=False, fingerprint='a' * 64, selection='working-tree',
            effective_settings={'values': {'tools.mobile_python': '/expired/old/python'}},
            run_overrides={'devices.ios': '["old-recipient"]', 'devices.ios_provisioning': 'existing'})
        self.snapshot = self.private / 'snapshots' / self.source['fingerprint']; self.snapshot.mkdir(parents=True)
        self.descriptor = {'schema': 1, 'adapter_api': 1, 'project_id': 'io.github.ispaure.logistics', 'name': 'Logistics'}
        (self.snapshot / 'build-project.json').write_text(json.dumps(self.descriptor))
        (self.root / 'build-project.json').write_text(json.dumps(dict(self.descriptor, current=True)))
        (self.snapshot / '.manager-source.json').write_text(json.dumps(dict(source=self.source, snapshot_fingerprint='snapshot-bytes')))
        self.project = NS(root=self.root, mobile=self.mobile, private=self.private, descriptor=self.descriptor)
        self.identity = self.enterContext(patch('logistics_build.build_snapshots.identity', return_value={'fingerprint': 'snapshot-bytes'}))
        registry = self.enterContext(patch.object(retained, 'Registry')).return_value
        registry.project_key.return_value = 'registered'
        registry.resolve.return_value = (dict(root=str(self.root), project_id=self.descriptor['project_id'],
            descriptor=file_sha256(self.root / 'build-project.json'), trusted=True), self.descriptor)
        self.settings = {'tools.mobile_python': sys.executable, 'tools.xcode': '/reviewed/Xcode',
                         'tools.android_sdk': '/reviewed/SDK', 'tools.java': '/reviewed/Java',
                         'auth.testflight_reference': '/protected/API-reference.json'}
        self.resolve_execution_settings = retained.execution_settings
        self.enterContext(patch.object(retained, 'execution_settings', return_value=self.settings))
        (self.mobile / '.device.json').write_text(json.dumps(dict(bundle_id=devices.BUNDLE, team_id='TEAM000001',
            device_ids=['ios-a', 'ios-b'], signing_identity={'application_identifier': 'TEAM000001.' + devices.BUNDLE})))
        self.certificate = 'c' * 64
        self.saved = [dict(platform='iOS', id='ios-a', name='Saved phone'),
                      dict(platform='iOS', id='ios-b', name='Saved tablet'),
                      dict(platform='Android', id='android-a', name='Saved Android',
                           android_signing={'mode': 'beta', 'certificate': self.certificate})]
        (self.mobile / '.tools/test-devices.json').write_text(json.dumps(self.saved))
        self.manifest = dict(logistics_commit=self.source['logistics_commit'], commonUtils_commit=self.source['commonUtils_commit'],
            dirty=True, manager_source_fingerprint=self.source['fingerprint'], source_sha256='8' * 64)
        old_helpers = self.snapshot / 'mobile_build/deployment'; old_helpers.mkdir(parents=True)
        (old_helpers / 'device_tools.py').write_text('def provisioning_auth_args(): return []\n'
            'def validate_app(app, team, udid, *, build_number=None): return True\n')
        self.archive_state = {'build_number': '202611045', 'archive_sha256': '9' * 64, 'release_sha256': '7' * 64}
        self.archive_record = {'source': self.manifest, 'build': {'version': '0.1.0', 'build_number': '202611045'}}
        self.archive = self.enterContext(patch('logistics_build.manager_packages.checked_archive',
            side_effect=lambda path: (self.archive_state, self.archive_record)))
        self.apk = self.root / 'retained.apk'; self.apk.write_bytes(b'previously verified signed APK')
        self.phases = []; self.rows = []
        for platform in ('ios', 'android'):
            ui = Phase(platform + '.validation.ui', ('python', '-c', 'pass'), str(self.snapshot), effect='test')
            cleanup = Phase(platform + '.validation.cleanup', ('python', '-c', 'pass'), str(self.snapshot),
                            dependencies=(ui.id,), always=True, effect='inspect')
            gate = Phase(platform + '.validated', ('python', '-c', 'pass'), str(self.snapshot),
                         dependencies=(ui.id, cleanup.id), effect='test')
            original = self.root / (platform + '-original.json'); copied = self.run / (platform + '-copy.json')
            data = self.archive_state if platform == 'ios' else dict(provider='Firebase', source=self.manifest,
                bundle_id=devices.BUNDLE, apk=str(self.apk), apk_sha256=file_sha256(self.apk), certificate=self.certificate)
            original.write_text(json.dumps(data)); copied.write_bytes(original.read_bytes())
            name = platform + ('.preparation.build-release-archive' if platform == 'ios' else '.preparation.prepare-verified-artifact')
            shared = Phase(name, ('python', '-c', 'pass'), str(self.snapshot), dependencies=(gate.id,),
                           effect='build', artifacts=(str(original),))
            self.phases.extend((ui, cleanup, gate, shared))
            self.rows.extend([dict(id=item.id, status='passed', artifacts=[]) for item in (ui, cleanup, gate)])
            self.rows.append(dict(id=shared.id, status='passed', artifacts=[dict(path=str(copied),
                original_path=str(original), sha256=file_sha256(original))]))
        self.plan = Plan('Logistics', 'Validate and deliver', self.source, tuple(self.phases), str(self.run / 'old-workspace'),
            adapter=dict(api=1, checkout=str(self.root), project_id=self.descriptor['project_id'],
                         descriptor_sha256=file_sha256(self.snapshot / 'build-project.json')), max_workers=4)
        self.save_run()

    def save_run(self):
        self.plan.save(self.run / 'plan.json')
        self.report = dict(schema=1, status='failed', project='Logistics', plan_identity=self.plan.identity,
                           source=self.source, phases=self.rows)
        (self.run / 'result.json').write_text(json.dumps(self.report))

    def make(self, destinations=None, overrides=None):
        return retained.make_plan(self.project, self.run, destinations or ['ios-devices'],
            overrides if overrides is not None else {'devices.ios': '["ios-a"]'})

    def test_passed_ios_survives_other_platform_failure_and_keeps_dirty_source(self):
        self.rows[4]['status'] = 'failed'; self.rows[5]['status'] = 'failed'; self.save_run()
        before = (self.run / 'result.json').read_bytes()
        plan = self.make()
        self.assertEqual(plan.source, self.source)
        self.assertNotEqual(plan.workspace, self.plan.workspace)
        self.assertFalse(plan.journey)
        self.assertTrue(all('android.' not in phase.id for phase in plan.phases))
        self.assertEqual((self.run / 'result.json').read_bytes(), before)
        self.assertIn('Try once', next(p.description for p in plan.phases if p.kind == 'connection'))
        self.assertFalse(self.identity.call_args_list[0].args[0] == self.root)

    def test_multiple_platforms_and_recipients_use_exact_saved_metadata(self):
        plan = self.make(['ios-devices', 'android-devices'], {'devices.ios': '["ios-a","ios-b"]',
            'devices.android': '["android-a"]', 'devices.availability': 'wait'})
        installs = [p for p in plan.phases if p.effect == 'deploy']
        self.assertEqual(len(installs), 3)
        self.assertTrue(all(p.approval_required for p in installs))
        self.assertEqual(len({p.artifacts[0] for p in installs}), 3)
        self.assertTrue(all(p.retry_exit_codes == (75,) for p in plan.phases if p.kind == 'connection'))
        self.assertTrue(all('--receipt' in p.argv and p.artifacts[0] in p.argv for p in installs))

    def test_real_executor_owns_primary_lock_and_protects_secondary_workspace(self):
        from build_manager.executor import Executor
        from build_manager.locking import workspace_lock
        plan = self.make(['ios-devices', 'android-devices'],
                         {'devices.ios': '["ios-a"]', 'devices.android': '["android-a"]'})
        primary = Path(plan.workspace)
        self.assertNotIn(str(primary / 'operation.lock'), plan.resource_locks)
        proof = json.loads(Path(plan.settings['retained_delivery']['proof']).read_text())
        secondary = next(Path(recipe).parent for recipe in proof['recipes'] if Path(recipe).parent != primary)
        secondary_lock = str(secondary / 'operation.lock')
        self.assertIn(secondary_lock, plan.resource_locks)
        ran = self.root / 'harmless-phase-ran'
        stub = Phase('harmless-lock-probe', (sys.executable, '-c',
            'from pathlib import Path; Path(' + repr(str(ran)) + ').touch()'), str(primary), effect='inspect')
        executable = replace(plan, phases=(stub,), effect='inspect')
        runner = Executor(resource_directory=self.root / 'resource-slots', evidence_directory=self.root / 'evidence')
        with workspace_lock(secondary / 'operation.lock'):
            blocked = runner.run(executable, self.root / 'blocked-run')
        self.assertEqual(blocked['status'], 'failed')
        self.assertIn('Another operation owns this workspace', blocked['error'])
        self.assertFalse(ran.exists())
        completed = runner.run(executable, self.root / 'successful-run')
        self.assertEqual(completed['status'], 'passed', completed.get('error'))
        self.assertTrue(ran.is_file())

    def test_failed_applicable_gate_or_cleanup_is_rejected_before_workspace_creation(self):
        for index in (0, 1, 2, 3):
            with self.subTest(index=index):
                self.rows[index]['status'] = 'failed'; self.save_run()
                with self.assertRaisesRegex(ValueError, 'did not pass'): self.make()
                self.rows[index]['status'] = 'passed'
        self.assertFalse((self.private / 'workspaces').exists())

    def test_changed_original_or_retained_copy_hash_stops_preparation(self):
        for key in ('path', 'original_path'):
            artifact = self.rows[3]['artifacts'][0]; path = Path(artifact[key]); before = path.read_bytes()
            path.write_bytes(before + b'changed')
            with self.assertRaisesRegex(ValueError, 'artifact.*changed|missing or changed'): self.make()
            path.write_bytes(before)

    def test_expired_snapshot_does_not_materialize_or_rebuild(self):
        (self.snapshot / '.manager-source.json').unlink()
        with patch('logistics_build.build_snapshots.materialize') as materialize:
            with self.assertRaisesRegex(ValueError, 'Rebuild'): self.make()
            materialize.assert_not_called()

    def test_unknown_recipients_destinations_and_undeclared_choices_rejected(self):
        for destinations, choices in ((['github'], {}), (['ios-devices', 'ios-devices'], {}),
                (['ios-devices'], {'devices.ios': '["not-saved"]'}),
                (['ios-devices'], {'devices.ios': '["ios-a"]', 'testflight.app_id': 'changed'})):
            with self.subTest(destinations=destinations, choices=choices), self.assertRaises(ValueError):
                self.make(destinations, choices)

    def test_android_debug_or_wrong_saved_certificate_never_falls_back_to_compilation(self):
        for policy in ({'mode': 'debug', 'certificate': self.certificate}, {'mode': 'beta', 'certificate': 'f' * 64}):
            self.saved[-1]['android_signing'] = policy
            (self.mobile / '.tools/test-devices.json').write_text(json.dumps(self.saved))
            with self.assertRaisesRegex(ValueError, 'signing policy differs'):
                self.make(['android-devices'], {'devices.android': '["android-a"]'})

    def test_current_runner_and_verifier_are_copied_and_old_metadata_namespace_is_retained(self):
        # A pure fixture import proves newer checkout app metadata is not used.
        for root, version in ((self.root, '0.2.0'), (self.snapshot, '0.1.0')):
            package = root / 'mobile_build/deployment'; package.mkdir(parents=True, exist_ok=True)
            (package / '__init__.py').touch(); (package.parent / '__init__.py').touch()
            (package / 'device_tools.py').write_text('VERSION = ' + repr(version) + '\n'
                'def validate_app(app, team, udid, **kwargs): return VERSION\n')
        plan = self.make(); proof = json.loads(Path(plan.settings['retained_delivery']['proof']).read_text())
        self.assertEqual(Path(proof['runner']).read_bytes(), Path(devices.__file__).read_bytes())
        self.assertEqual(Path(proof['verifier']).read_bytes(), Path(retained.__file__).read_bytes())
        for phase in plan.phases:
            self.assertIn(str(self.snapshot), phase.environment['PYTHONPATH'])
            self.assertNotIn(str(self.root / 'Python'), phase.environment['PYTHONPATH'].split(os.pathsep))
        phase = plan.phases[1]
        env = dict(os.environ, **phase.environment)
        value = subprocess.check_output([sys.executable, '-c',
            'from mobile_build.deployment.device_tools import VERSION;print(VERSION)'], cwd=phase.cwd, env=env, text=True)
        self.assertEqual(value.strip(), '0.1.0')

    def test_explicit_provisioning_choices_separate_from_original_artifact_source(self):
        plan = self.make(overrides={'devices.ios': '["ios-b"]', 'devices.ios_provisioning': 'update'})
        proof = json.loads(Path(plan.settings['retained_delivery']['proof']).read_text())
        recipe = json.loads(Path(next(iter(proof['recipes']))).read_text())
        self.assertEqual(recipe['source'], self.source)
        self.assertEqual(recipe['execution_choices']['devices.ios_provisioning'], 'update')
        prepare = next(phase for phase in plan.phases if phase.kind == 'build')
        self.assertIn('explicitly allow Apple profile/capability updates', prepare.description)
        ios = NS(provisioning_auth_args=lambda: ['--reviewed-api-reference'])
        self.assertEqual(devices.ios_provisioning_args(self.source, ios, recipe['execution_choices']),
                         ['-allowProvisioningUpdates', '--reviewed-api-reference'])
        self.assertEqual(devices.ios_provisioning_args(self.source, ios), [])

    def test_legacy_helper_without_provisioning_references_gives_explicit_choice(self):
        (self.snapshot / 'mobile_build/deployment/device_tools.py').write_text(
            'def validate_app(app, team, udid, *, build_number=None): return True\n')
        with self.assertRaisesRegex(ValueError, 'Choose existing signing assets or rebuild'):
            self.make(overrides={'devices.ios': '["ios-a"]', 'devices.ios_provisioning': 'update'})

    def test_current_execution_reference_resolution_does_not_discover_hardware(self):
        from mobile_build.deployment import manager_settings as owner
        with patch.object(owner, 'defaults', return_value=self.settings), \
                patch.object(owner, 'loaded_profile', return_value=self.settings), \
                patch.dict(os.environ, {'LOGISTICS_MANAGER_CHECKOUT': '/never-discover'}), \
                patch.object(retained.subprocess, 'run', side_effect=AssertionError('Hardware query')):
            values = self.resolve_execution_settings(self.mobile)
        self.assertEqual(values['auth.testflight_reference'], '/protected/API-reference.json')
        self.assertEqual(values['tools.mobile_python'], sys.executable)
        self.assertTrue(all(key.startswith(('tools.', 'auth.')) for key in values))

    def test_apple_configuration_change_is_rejected_before_readiness_or_install(self):
        plan = self.make(); proof = Path(plan.settings['retained_delivery']['proof'])
        config = self.mobile / '.device.json'; config.write_text(config.read_text() + ' ')
        with patch.object(retained.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'Apple team/recipient configuration changed'):
                retained.verify_inputs(proof, file_sha256(proof))
            run.assert_not_called()

    def test_captured_snapshot_descriptor_change_is_not_replaced_by_current_checkout(self):
        (self.snapshot / 'build-project.json').write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError, 'Original captured adapter descriptor changed'):
            self.make()

    def test_legacy_archive_build_validation_requires_explicit_keyword_or_kwargs(self):
        helper = self.snapshot / 'mobile_build/deployment/device_tools.py'
        helper.write_text('def validate_app(app, team, udid): return True\n')
        with self.assertRaisesRegex(ValueError, 'cannot validate the archive build number.*Rebuild'):
            self.make()
        self.assertFalse((self.private / 'workspaces').exists())
        for signature in ('app, team, udid, *, build_number=None', 'app, team, udid, **kwargs'):
            helper.write_text('def validate_app(' + signature + '): return True\n')
            self.assertEqual(self.make().source, self.source)

    def test_execution_profile_reference_changes_require_fresh_review(self):
        profile = self.mobile / '.tools/build-manager/profile.json'
        profile.write_text('{"auth.testflight_reference":"first-reference.json"}')
        plan = self.make(); proof = Path(plan.settings['retained_delivery']['proof'])
        profile.write_text('{"auth.testflight_reference":"different-reference.json"}')
        with self.assertRaisesRegex(ValueError, 'execution profile references changed'):
            retained.verify_inputs(proof, file_sha256(proof))

    def test_execution_verifies_original_inputs_before_any_device_command(self):
        plan = self.make(); proof_path = Path(plan.settings['retained_delivery']['proof']); proof = json.loads(proof_path.read_text())
        phase = next(p for p in plan.phases if p.effect == 'deploy'); command = list(phase.argv[phase.argv.index('--') + 1:])
        (self.run / 'result.json').write_text((self.run / 'result.json').read_text() + ' ')
        with patch.object(retained.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'Original retained inputs changed'):
                retained.execute(proof_path, file_sha256(proof_path), phase.id, command)
            run.assert_not_called()
        self.assertNotEqual(proof['original_binding']['original_result_sha256'], file_sha256(self.run / 'result.json'))

    def test_verified_execution_delegates_only_the_reviewed_owning_command(self):
        plan = self.make(); path = Path(plan.settings['retained_delivery']['proof'])
        phase = next(p for p in plan.phases if p.effect == 'deploy')
        command = list(phase.argv[phase.argv.index('--') + 1:])
        with patch.object(retained.subprocess, 'run') as run:
            retained.execute(path, file_sha256(path), phase.id, command)
            run.assert_called_once_with(command, cwd=str(self.snapshot), check=False)

    def test_wait_mode_preserves_owning_unavailable_exit_instead_of_false_success(self):
        plan = self.make(overrides={'devices.ios': '["ios-a"]', 'devices.availability': 'wait'})
        path = Path(plan.settings['retained_delivery']['proof'])
        phase = next(p for p in plan.phases if p.kind == 'connection')
        command = list(phase.argv[phase.argv.index('--') + 1:])
        with patch.object(retained.subprocess, 'run', return_value=NS(returncode=75)):
            self.assertEqual(retained.execute(path, file_sha256(path), phase.id, command), 75)
        with patch.object(retained, 'execute', return_value=75):
            self.assertEqual(retained.main(['execute', '--proof', str(path), '--sha256', file_sha256(path),
                '--step', phase.id, '--', *command]), 75)

    def test_changed_recipe_or_runner_is_rejected_before_effects(self):
        plan = self.make(); path = Path(plan.settings['retained_delivery']['proof']); proof = json.loads(path.read_text())
        for target, message in ((Path(proof['runner']), 'runner changed'),
                                (Path(next(iter(proof['recipes']))), 'recipe changed')):
            original = target.read_bytes(); target.write_bytes(original + b'changed')
            with patch.object(retained.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, message):retained.verify_inputs(path, file_sha256(path))
                run.assert_not_called()
            target.write_bytes(original)

    def test_retry_changes_only_fresh_receipt_not_target_or_prepared_package(self):
        plan = self.make(); path = Path(plan.settings['retained_delivery']['proof']); proof = json.loads(path.read_text())
        phase = next(p for p in plan.phases if p.effect == 'deploy'); command = list(proof['commands'][phase.id]['argv'])
        receipt = Path(plan.workspace) / 'explicit-device-retries' / ('f' * 32) / 'receipt-0.json'
        command[command.index('--receipt') + 1] = str(receipt)
        self.assertEqual(retained._checked_command(proof, phase.id, command), str(self.snapshot))
        second = receipt.parent / 'explicit-device-retries' / ('e' * 32) / 'receipt-0.json'
        command[command.index('--receipt') + 1] = str(second)
        self.assertEqual(retained._checked_command(proof, phase.id, command), str(self.snapshot))
        command[command.index('--device') + 1] = 'another-device'
        with self.assertRaisesRegex(ValueError, 'input command changed'):
            retained._checked_command(proof, phase.id, command)

    def test_default_bounded_and_explicit_legacy_wait_keep_independent_recipient_dependencies(self):
        bounded = devices.availability_policy()
        self.assertEqual((bounded['timeout'], bounded['retry_exit_codes']), (90, ()))
        waiting = devices.availability_policy('wait')
        self.assertEqual((waiting['timeout'], waiting['retry_exit_codes'], waiting['retry_delay']), (120, (75,), 30))
        plan = self.make(overrides={'devices.ios': '["ios-a","ios-b"]'})
        ready = [p for p in plan.phases if p.kind == 'connection']
        self.assertEqual(ready[0].dependencies, ready[1].dependencies)
        self.assertTrue(all(p.timeout == 90 and not p.retry_exit_codes for p in ready))
        self.assertFalse(any(ready[0].id in p.dependencies for p in plan.phases if p.effect == 'deploy' and 'ios-b' in p.argv))

    def test_execution_wrapper_keeps_exact_owner_arguments_visible_for_retry(self):
        command = ['python', 'manager_devices.py', 'install', '--device', 'ios-a', '--receipt', 'fresh.json']
        with patch.object(retained, 'execute') as execute:
            retained.main(['execute', '--proof', 'proof.json', '--sha256', 'reviewed', '--step', 'ios.install', '--', *command])
        execute.assert_called_once_with(Path('proof.json'), 'reviewed', 'ios.install', command)

    def test_planning_does_not_query_devices_export_or_compile(self):
        with patch.object(devices.subprocess, 'run', side_effect=AssertionError('Unexpected command')), \
                patch('logistics_build.build_snapshots.materialize', side_effect=AssertionError('Unexpected materialization')):
            self.make()
