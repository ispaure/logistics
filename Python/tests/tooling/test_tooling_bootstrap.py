"""Explicit pinned SDK repair works before importing the SDK itself."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import signal
import time
import uuid
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import Mock, patch

from logistics_build import tooling_bootstrap as tooling


class ToolingBootstrapTests(TestCase):
    def setUp(self):
        self.temp = self.enterContext(TemporaryDirectory())
        self.root = Path(self.temp).resolve()
        self.declared = dict(schema=1, adapter_api=1,
            repository='https://github.com/ispaure/build-deployment-manager.git', revision='a' * 40)
        (self.root / 'build-manager-dependency.json').write_text(json.dumps(self.declared))

    def target_environments(self):
        for _, _, interpreter in tooling.environments(self.root):
            interpreter.parent.mkdir(parents=True, exist_ok=True)
            interpreter.touch()

    def write_intent(self, **changes):
        value = dict(schema=1, root=str(self.root), nonce=str(uuid.uuid4()),
                     boot_id=str(uuid.uuid4()), mode='sync', groups=[])
        value.update(changes)
        path = tooling.intent_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return value

    @skipUnless(os.name == 'posix', 'POSIX durable mutation recovery')
    def test_healthy_unenrolled_sync_retires_groups_and_clears_its_intent(self):
        with tooling.environment_sync(self.root):
            self.assertEqual(tooling.read_intent(self.root)['mode'], 'sync')
            tooling.run_command([sys.executable, '-c', 'pass'], check=True)
        self.assertFalse(tooling.intent_path(self.root).exists())
        self.assertFalse(tooling.enrolled(self.root))

    @skipUnless(os.name == 'posix', 'POSIX durable mutation recovery')
    def test_nonce_mismatch_or_unverified_operation_cannot_clear_intent(self):
        with self.assertRaises(tooling.BootstrapError):
            with tooling.mutation_guard(self.root), tooling.mutation_intent(self.root, 'sync'):
                current = tooling.read_intent(self.root)
                with self.assertRaises(tooling.BootstrapError):
                    tooling.clear_intent(self.root, current['nonce'])
                replacement = dict(current, nonce=str(uuid.uuid4()))
                tooling.atomic_json(tooling.intent_path(self.root), replacement)
        self.assertEqual(tooling.read_intent(self.root)['nonce'], replacement['nonce'])

    @skipUnless(os.name == 'posix', 'POSIX durable mutation recovery')
    def test_linked_or_malformed_intent_blocks_without_following_or_installing(self):
        path = tooling.intent_path(self.root)
        path.parent.mkdir(parents=True)
        outside = self.root / 'outside'
        outside.write_text('preserve')
        path.symlink_to(outside)
        for linked in (True, False):
            with self.subTest(linked=linked), patch.object(tooling, 'run_command') as run:
                with self.assertRaises(tooling.BootstrapError):
                    with tooling.environment_sync(self.root):
                        run(['uv', 'sync'])
                run.assert_not_called()
            if linked:
                self.assertEqual(outside.read_text(), 'preserve')
                path.unlink()
                path.write_text('{invalid')
        report = tooling.handle(self.root, 'tooling_status', {})
        self.assertEqual(report['reason'], 'unfinished_mutation')
        self.assertNotIn('outside', report['message'])

    @skipUnless(os.name == 'posix', 'POSIX durable mutation recovery')
    def test_only_verified_boot_change_allows_confirmed_repair_to_clear(self):
        self.target_environments()
        previous = self.write_intent()
        with patch.object(tooling, 'boot_identity', return_value=previous['boot_id']), \
                patch.object(tooling, '_repair_locked') as repair:
            with self.assertRaises(tooling.BootstrapError):
                tooling.update(self.root, confirmed=True)
            repair.assert_not_called()
        with patch.object(tooling, 'boot_identity', side_effect=tooling.BootstrapError('boot_identity')), \
                patch.object(tooling, '_repair_locked') as repair:
            with self.assertRaises(tooling.BootstrapError):
                tooling.update(self.root, confirmed=True)
            repair.assert_not_called()
        new_boot = str(uuid.uuid4())
        with patch.object(tooling, 'boot_identity', return_value=new_boot), \
                patch.object(tooling, '_repair_locked', side_effect=tooling.BootstrapError('verification')):
            with self.assertRaises(tooling.BootstrapError):
                tooling.update(self.root, confirmed=True)
        remaining = tooling.read_intent(self.root)
        self.assertEqual(remaining['recovery_nonce'], previous['nonce'])
        self.assertEqual(remaining['boot_id'], new_boot)
        # Failed verification stays unresolved; another boot and successful repair are required.
        with patch.object(tooling, 'boot_identity', return_value=str(uuid.uuid4())), \
                patch.object(tooling, '_repair_locked', return_value=dict(ready=True)) as repair:
            self.assertEqual(tooling.update(self.root, confirmed=True), dict(ready=True))
            repair.assert_called_once()
        self.assertFalse(tooling.intent_path(self.root).exists())

    @skipUnless(os.name == 'posix', 'POSIX durable mutation recovery')
    def test_failed_group_retirement_preserves_intent_even_after_successful_command(self):
        original = tooling._retire
        def retire(process):
            original(process)
            return False
        with patch.object(tooling, '_retire', side_effect=retire):
            with self.assertRaises(tooling.BootstrapError):
                with tooling.environment_sync(self.root):
                    tooling.run_command([sys.executable, '-c', 'pass'], check=True)
        self.assertIsNotNone(tooling.read_intent(self.root))

    @skipUnless(os.name == 'posix', 'POSIX durable mutation recovery')
    def test_failed_uv_with_verified_cleanup_allows_same_boot_explicit_repair(self):
        with self.assertRaises(subprocess.CalledProcessError):
            with tooling.environment_sync(self.root):
                tooling.run_command([sys.executable, '-c', 'raise SystemExit(7)'], check=True)
        previous = tooling.read_intent(self.root)
        self.assertEqual(previous['cleanup'], tooling.cleanup_proof(previous))
        self.target_environments()
        with patch.object(tooling, 'boot_identity', return_value=previous['boot_id']), \
                patch.object(tooling, '_repair_locked', return_value=dict(ready=True)) as repair:
            self.assertEqual(tooling.update(self.root, confirmed=True), dict(ready=True))
            repair.assert_called_once()
        self.assertFalse(tooling.intent_path(self.root).exists())

    @skipUnless(os.name == 'posix', 'POSIX durable mutation recovery')
    def test_uncertain_constructor_never_emits_cleanup_proof(self):
        with patch.object(tooling.subprocess, 'Popen', side_effect=OSError('uncertain launch')), \
                patch.object(tooling, 'boot_identity', return_value=str(uuid.uuid4())):
            with self.assertRaises(OSError):
                with tooling.environment_sync(self.root):
                    tooling.run_command(['fixture-installer'])
        previous = tooling.read_intent(self.root)
        self.assertNotIn('cleanup', previous)
        self.target_environments()
        with patch.object(tooling, 'boot_identity', return_value=previous['boot_id']), \
                patch.object(tooling, '_repair_locked') as repair:
            with self.assertRaises(tooling.BootstrapError):
                tooling.update(self.root, confirmed=True)
            repair.assert_not_called()

    @skipUnless(os.name == 'posix', 'POSIX durable mutation recovery')
    def test_cleanup_exception_cannot_emit_verified_receipt(self):
        original = tooling._retire
        def interrupted_cleanup(process):
            original(process)
            raise subprocess.TimeoutExpired(process.args, 2)
        with patch.object(tooling, '_retire', side_effect=interrupted_cleanup):
            with self.assertRaises(subprocess.TimeoutExpired):
                with tooling.environment_sync(self.root):
                    tooling.run_command([sys.executable, '-c', 'pass'], check=True)
        self.assertNotIn('cleanup', tooling.read_intent(self.root))

    @skipUnless(os.name == 'posix', 'POSIX durable mutation recovery')
    def test_malformed_or_wrong_nonce_cleanup_proof_fails_closed(self):
        previous = self.write_intent()
        previous['cleanup'] = dict(nonce=str(uuid.uuid4()), boot_id=previous['boot_id'], groups=[])
        tooling.intent_path(self.root).write_text(json.dumps(previous))
        with self.assertRaises(tooling.BootstrapError):
            tooling.read_intent(self.root)
        self.assertEqual(tooling.status(self.root)['reason'], 'unfinished_mutation')

    @skipUnless(os.name == 'posix', 'POSIX durable mutation recovery')
    def test_abrupt_kill_leaves_mutating_grandchild_and_blocks_new_updater(self):
        marker, identity = self.root / 'writes', self.root / 'identity'
        grandchild = ('import os,signal,sys,time; from pathlib import Path; '
                      'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                      'Path(sys.argv[2]).write_text(str(os.getpgrp())); '
                      'f=open(sys.argv[1],"a",buffering=1); '
                      '\nwhile True: f.write("x"); f.flush(); time.sleep(.01)')
        installer = ('import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",'
                     + repr(grandchild) + ',sys.argv[1],sys.argv[2]]); time.sleep(60)')
        driver = ('from logistics_build import tooling_bootstrap as t; import sys; from pathlib import Path; '
                  '\nwith t.environment_sync(Path(sys.argv[1])): '
                  't.run_command([sys.executable,"-c",' + repr(installer) + ',sys.argv[2],sys.argv[3]])')
        owner = subprocess.Popen([sys.executable, '-c', driver, str(self.root), str(marker), str(identity)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 5
            while not identity.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(identity.exists())
            owner.kill()  # Only this fixture updater; its independently owned group survives.
            owner.wait(timeout=3)
            count = marker.stat().st_size
            self.assertGreater(count, 0)
            time.sleep(.1)
            self.assertGreater(marker.stat().st_size, count)
            with tooling.file_lock(tooling.lock_path(self.root)):
                pass  # A free advisory lock is deliberately insufficient.
            self.target_environments()
            with patch.object(tooling, '_repair_locked') as repair:
                with self.assertRaises(tooling.BootstrapError):
                    tooling.update(self.root, confirmed=True)
                repair.assert_not_called()
            self.assertEqual(tooling.handle(self.root, 'tooling_status', {})['reason'], 'unfinished_mutation')
        finally:
            if owner.poll() is None:
                owner.kill()
                owner.wait(timeout=3)
            if identity.exists():
                try:
                    os.killpg(int(identity.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.assertTrue(tooling.intent_path(self.root).exists())

    def test_stdlib_bridge_readiness_works_with_no_sdk_and_ignores_gui_checkout(self):
        repo = Path(tooling.__file__).resolve().parents[1]
        package = self.root / 'logistics_build'
        package.mkdir()
        for name in ('manager_bridge.py', 'tooling_bootstrap.py', 'device_workspace_paths.py',
                     'native_tooling.py', 'native_tooling.json'):
            shutil.copy2(repo / 'logistics_build' / name, package / name)
        for action, values in [('tooling_status', {}), ('tooling_update', {'confirmed': False})]:
            with self.subTest(action=action):
                result = subprocess.run([sys.executable, '-I', '-S', str(package / 'manager_bridge.py')],
                    input=json.dumps(dict(schema=1, action=action, values=values,
                                          manager_checkout='/untrusted/private/checkout')),
                    capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)['result']
                self.assertEqual(report['status'], 'blocked')
                self.assertEqual(report['declared_revision'], 'a' * 40)
                self.assertFalse(report['ready'])
                self.assertNotIn('/untrusted/private', result.stdout + result.stderr)
        self.assertFalse(tooling.private(self.root).exists())
        failed = subprocess.run([sys.executable, '-I', '-S', str(package / 'manager_bridge.py')],
            input=json.dumps(dict(schema=1, action='settings')), capture_output=True, text=True, timeout=10)
        self.assertEqual(failed.returncode, 1)
        self.assertNotIn('Traceback', failed.stderr)
        self.assertIn('tooling', failed.stderr)

    def test_direct_script_status_uses_own_checkout_from_foreign_working_directory(self):
        # The documented script entry must reach native readiness without an
        # installed manager, site packages, inherited PYTHONPATH or project cwd.
        result = subprocess.run([sys.executable, '-I', '-S', tooling.__file__,
                                 'status', '--root', str(self.root)],
                                cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual(report['declared_revision'], self.declared['revision'])
        self.assertFalse(report['ready'])
        self.assertFalse(report['native']['applicable'])
        self.assertFalse(tooling.private(self.root).exists())

    def test_confirmation_and_owned_environment_checks_precede_every_effect(self):
        with patch.object(tooling, 'run') as run:
            with self.assertRaises(ValueError):
                tooling.update(self.root, confirmed='yes')
            run.assert_not_called()
            self.target_environments()
            mobile = tooling.environments(self.root)[1][1]
            shutil.rmtree(mobile)
            other = self.root / 'ally-environment'
            other.mkdir()
            try:
                mobile.symlink_to(other, target_is_directory=True)
            except OSError:
                self.skipTest('Creating directory links unavailable')
            with self.assertRaises(ValueError):
                tooling.update(self.root, confirmed=True)
            run.assert_not_called()
        self.assertFalse(tooling.private(self.root).exists())

    def test_explicit_repair_uses_one_owned_pin_and_both_interpreters(self):
        self.target_environments()
        checkout = tooling.private(self.root) / 'tooling' / self.declared['revision']
        def installer(args, **kwargs):
            if '-c' in args:
                return json.dumps(dict(prefix=str(Path(args[0]).parent.parent)))
            if '--from-pin' in args:
                checkout.mkdir()
            return ''
        with patch.object(tooling, 'run', side_effect=installer) as run, \
                patch.object(tooling, 'verify_checkout') as verify, \
                patch.object(tooling, 'status', return_value=dict(ready=True, status='ready')), \
                patch.object(tooling, 'repair_native') as native:
            tooling.update(self.root, confirmed=True)
        calls = [call.args[0] for call in run.call_args_list if '-c' not in call.args[0]]
        native.assert_called_once_with(self.root)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], [tooling.environments(self.root)[0][2],
            self.root / 'logistics_build/install_build_manager.py', '--from-pin', checkout])
        self.assertEqual(calls[1][-1], checkout)
        self.assertEqual(calls[1][0], tooling.environments(self.root)[1][2])
        self.assertGreaterEqual(verify.call_count, 2)
        self.assertTrue(tooling.enrolled(self.root))

    def test_existing_unowned_or_changed_checkout_is_never_reset(self):
        self.target_environments()
        checkout = tooling.private(self.root) / 'tooling' / self.declared['revision']
        checkout.mkdir(parents=True)
        with patch.object(tooling, 'validate_interpreters'), patch.object(tooling, 'run') as run:
            with self.assertRaises(ValueError):
                tooling.update(self.root, confirmed=True)
            run.assert_not_called()
        proof = dict(root=str(self.root.resolve()), **self.declared)
        checkout.with_suffix('.ownership.json').write_text(json.dumps(proof))
        with patch.object(tooling, 'validate_interpreters'), \
                patch.object(tooling, 'verify_checkout', side_effect=ValueError('Dirty')), \
                patch.object(tooling, 'run') as run:
            with self.assertRaises(ValueError):
                tooling.update(self.root, confirmed=True)
            run.assert_not_called()

    def test_real_active_operation_lock_blocks_install_but_stale_file_does_not(self):
        self.target_environments()
        lock = tooling.private(self.root) / 'workspaces' / '.fixture.operation.lock'
        lock.parent.mkdir(parents=True)
        code = ('from logistics_build.tooling_bootstrap import file_lock; import sys; '
                'ctx=file_lock(sys.argv[1],create=True);ctx.__enter__(); '
                'print("ready",flush=True);sys.stdin.read(1);ctx.__exit__(None,None,None)')
        child = subprocess.Popen([sys.executable, '-c', code, str(lock)], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'ready')
            with patch.object(tooling, 'run') as run:
                with self.assertRaises(RuntimeError):
                    tooling.update(self.root, confirmed=True)
                run.assert_not_called()
        finally:
            child.communicate('x', timeout=10)
        with tooling.mutation_guard(self.root):
            pass
        self.assertTrue(lock.exists())

    @skipUnless(os.name == 'posix', 'POSIX tooling mutation guard')
    def test_scratch_lease_blocks_tooling_mutation(self):
        from logistics_build.build_retention import scratch
        with scratch(self.root):
            with self.assertRaises(tooling.ActiveWorkflowError), tooling.mutation_guard(self.root):
                self.fail('Tooling mutation entered while scratch was leased')
        with tooling.mutation_guard(self.root):
            pass

    @skipUnless(os.name == 'posix', 'POSIX tooling mutation guard')
    def test_saved_run_supervisor_locks_block_tooling_mutation_at_both_roots(self):
        from build_manager.locking import workspace_lock

        for base in ('test-results/build-manager', 'tmp/test-results/build-manager'):
            run = self.root / base / 'run'
            run.mkdir(parents=True)
            lock = run / 'supervisor.lock'
            with self.subTest(root=base), workspace_lock(lock):
                self.assertIn(lock, set(tooling.operation_locks(self.root)))
                with self.assertRaises(tooling.ActiveWorkflowError), tooling.mutation_guard(self.root):
                    self.fail('Tooling mutation entered while a saved run was active')
            with tooling.mutation_guard(self.root):
                pass

    @skipUnless(os.name == 'posix', 'POSIX tooling mutation guard')
    def test_device_workspace_locks_block_tooling_mutation_at_both_roots(self):
        from build_manager.locking import operation_lock_path, workspace_lock
        from logistics_build.device_workspace_paths import DEVICE_WORKSPACES, LEGACY_DEVICE_WORKSPACES

        for base in (LEGACY_DEVICE_WORKSPACES, DEVICE_WORKSPACES):
            workspace = self.root / base / 'android' / ('1' * 32)
            workspace.mkdir(parents=True)
            with self.subTest(root=base), workspace_lock(workspace / 'operation.lock'):
                self.assertIn(operation_lock_path(workspace), set(tooling.operation_locks(self.root)))
                with self.assertRaises(tooling.ActiveWorkflowError), tooling.mutation_guard(self.root):
                    self.fail('Tooling mutation entered while a device workspace was leased')
            with tooling.mutation_guard(self.root):
                pass

    def test_post_sync_is_opt_in_and_uses_declared_repair(self):
        with patch.object(tooling, 'update') as update:
            self.assertIsNone(tooling.after_sync(self.root))
            update.assert_not_called()
            marker = tooling.enrollment(self.root)
            marker.parent.mkdir(parents=True)
            marker.write_text(json.dumps(dict(schema=1, root=str(self.root.resolve()))))
            tooling.after_sync(self.root)
            update.assert_called_once_with(self.root, confirmed=True)

    def test_borrowed_or_global_python_is_rejected_before_installer(self):
        self.target_environments()
        with patch.object(tooling, 'run', return_value=json.dumps(dict(prefix='/global/python'))) as run:
            with self.assertRaises(ValueError):
                tooling.update(self.root, confirmed=True)
        self.assertTrue(all('-c' in call.args[0] for call in run.call_args_list))
        self.assertFalse(tooling.enrollment(self.root).exists())

    def test_unenrolled_sync_wrapper_executes_literal_command_only(self):
        command = ['/tool with spaces/uv', 'sync', '--project', 'literal;$value']
        argv = ['tooling_bootstrap.py', 'sync', '--project-root', str(self.root),
                '--venv', str(self.root / '.venv'), '--', *command]
        with patch.object(sys, 'argv', argv), patch.object(tooling, 'run_command', return_value=Mock(returncode=0)) as run, \
                patch.object(tooling, 'update') as update:
            self.assertEqual(tooling.main(), 0)
        run.assert_called_once_with(command, check=True)
        update.assert_not_called()
        self.assertTrue(tooling.lock_path(self.root).is_file())
        self.assertFalse(tooling.enrollment(self.root).exists())

    def test_unenrolled_sync_blocks_active_workflow_before_uv_or_install(self):
        lock = tooling.private(self.root) / 'workspaces' / 'fixture.operation.lock'
        with tooling.file_lock(lock, create=True), patch.object(tooling, 'run_command') as run, \
                patch.object(tooling, '_repair_locked') as repair:
            with self.assertRaises(tooling.ActiveWorkflowError):
                with tooling.environment_sync(self.root):
                    run(['uv', 'sync'])
            run.assert_not_called()
            repair.assert_not_called()
        self.assertFalse(tooling.enrolled(self.root))

    def test_enrolled_sync_restores_only_after_successful_command_and_releases_guard(self):
        self.target_environments()
        marker = tooling.enrollment(self.root)
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps(dict(schema=1, root=str(self.root))))
        events = []
        with patch.object(tooling, '_repair_locked', side_effect=lambda *args: events.append('restore')):
            with tooling.environment_sync(self.root):
                events.append('sync')
            self.assertEqual(events, ['sync', 'restore'])
            with self.assertRaises(RuntimeError):
                with tooling.environment_sync(self.root):
                    raise RuntimeError('uv failed')
        self.assertEqual(events, ['sync', 'restore'])
        with tooling.file_lock(tooling.lock_path(self.root)):
            pass

    def test_update_ignores_arbitrary_gui_manager_checkout(self):
        with patch.object(tooling, 'update', return_value=dict(ready=True)) as update:
            tooling.handle(self.root, 'tooling_update', dict(confirmed=True, manager_checkout='/untrusted'))
        update.assert_called_once_with(self.root, confirmed=True)

    def test_new_plan_bridge_adds_environment_lock_without_sdk_path_injection(self):
        repo = Path(tooling.__file__).resolve().parents[1]
        package = self.root / 'logistics_build'
        package.mkdir()
        for name in ('manager_bridge.py', 'tooling_bootstrap.py', 'device_workspace_paths.py',
                     'native_tooling.py', 'native_tooling.json'):
            shutil.copy2(repo / 'logistics_build' / name, package / name)
        (package / 'build_project.py').write_text(
            'class LogisticsProject:\n'
            ' def __init__(self,root): pass\n'
            ' def make_plan(self,*a,**kw): return self\n'
            ' def data(self): return dict(source={},phases=[],workspace="owned",resource_locks=["existing"])\n')
        request = dict(schema=1, action='plan', values=dict(operation='Test', target='android', backend='Local'))
        result = subprocess.run([sys.executable, '-I', '-S', str(package / 'manager_bridge.py')],
            input=json.dumps(request), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['result']['resource_locks'],
                         ['existing', str(tooling.lock_path(self.root))])

    def test_linked_enrollment_cannot_redirect_installation_writes(self):
        self.target_environments()
        marker = tooling.enrollment(self.root)
        marker.parent.mkdir(parents=True)
        outside = self.root / 'other-file'
        outside.write_text('preserve')
        try:
            marker.symlink_to(outside)
        except OSError:
            self.skipTest('Creating links unavailable')
        with patch.object(tooling, 'run') as run:
            with self.assertRaises(ValueError):
                tooling.update(self.root, confirmed=True)
            run.assert_not_called()
        self.assertEqual(outside.read_text(), 'preserve')

    def test_blockers_are_distinct_actionable_and_never_include_raw_tool_output(self):
        cases = [('active_workflow', tooling.ActiveWorkflowError()),
                 ('environments', tooling.BootstrapError('environments')),
                 ('changed_checkout', tooling.BootstrapError('changed_checkout'))]
        messages = []
        for reason, error in cases:
            with self.subTest(reason=reason), patch.object(tooling, 'update', side_effect=error):
                result = tooling.handle(self.root, 'tooling_update', {'confirmed': True})
                self.assertEqual(result['reason'], reason)
                self.assertEqual(result['status'], 'blocked')
                self.assertTrue(result['message'])
                messages.append(result['message'])
        self.assertEqual(len(set(messages)), 3)
        with patch.object(tooling, 'update', side_effect=subprocess.CalledProcessError(1, 'secret-command', output='secret-token')):
            result = tooling.handle(self.root, 'tooling_update', {'confirmed': True})
        self.assertNotIn('secret', json.dumps(result))
        self.assertEqual(result['reason'], 'install')

    def test_failed_enrolled_setup_does_not_restore_and_preserves_exit_code(self):
        from Scripts import development
        self.target_environments()
        marker = tooling.enrollment(self.root)
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps(dict(schema=1, root=str(self.root))))
        with patch.object(development, 'find_uv', return_value='uv'), \
                patch.object(tooling, 'run_command', return_value=Mock(returncode=7)), \
                patch.object(tooling, '_repair_locked') as repair:
            self.assertEqual(development.setup(self.root, 'desktop', lambda _: None), 7)
            repair.assert_not_called()
        with tooling.file_lock(tooling.lock_path(self.root)):
            pass

    @skipUnless(os.name == 'posix', 'POSIX owned-group lifecycle')
    def test_cancellation_during_launch_is_deferred_until_cleanup_is_registered(self):
        spawned = []
        popen = subprocess.Popen
        def launch(*args, **kwargs):
            child = popen(*args, **kwargs)
            spawned.append(child)
            os.kill(os.getpid(), signal.SIGTERM)
            return child
        with patch.object(tooling.subprocess, 'Popen', side_effect=launch):
            with self.assertRaises(KeyboardInterrupt):
                tooling.run_command([sys.executable, '-c', 'import time; time.sleep(60)'])
        self.assertIsNotNone(spawned[0].poll())
        with self.assertRaises(ProcessLookupError):
            os.killpg(spawned[0].pid, 0)

    @skipUnless(os.name == 'posix', 'POSIX owned-group lifecycle')
    def test_timeout_stops_mutating_grandchild_after_parent_exits_with_inherited_pipe(self):
        marker = self.root / 'writes'
        identity = self.root / 'identity'
        grandchild = ('import os,signal,sys,time; from pathlib import Path; '
                      'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                      'Path(sys.argv[2]).write_text(str(os.getpgrp())+":"+str(os.getsid(0))); '
                      'f=open(sys.argv[1],"a",buffering=1); '
                      '\nwhile True: f.write("x"); f.flush(); time.sleep(.01)')
        parent = ('import subprocess,sys; subprocess.Popen([sys.executable,"-c",'
                  + repr(grandchild) + ',sys.argv[1],sys.argv[2]])')
        started = time.monotonic()
        try:
            with self.assertRaises(subprocess.TimeoutExpired):
                tooling.run_command([sys.executable, '-c', parent, marker, identity],
                                    timeout=.5, capture_output=True)
            self.assertLess(time.monotonic() - started, 10)
            pgid, sid = map(int, identity.read_text().split(':'))
            self.assertEqual(sid, os.getsid(0))  # Never escape the SDK's session.
            self.assertNotEqual(pgid, os.getpgrp())
            count = marker.stat().st_size
            self.assertGreater(count, 0)
            time.sleep(.15)
            self.assertEqual(marker.stat().st_size, count)
        finally:
            if identity.exists():
                try:
                    os.killpg(int(identity.read_text().split(':')[0]), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    @skipUnless(os.name == 'posix', 'POSIX bridge cancellation lifecycle')
    def test_term_retires_installer_before_environment_lease_is_released(self):
        marker = self.root / 'writes'
        identity = self.root / 'identity'
        child = ('import os,signal,sys,time; from pathlib import Path; '
                 'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                 'Path(sys.argv[2]).write_text(str(os.getpgrp())); '
                 'f=open(sys.argv[1],"a",buffering=1); '
                 '\nwhile True: f.write("x"); f.flush(); time.sleep(.01)')
        driver = ('from logistics_build import tooling_bootstrap as t; import sys; '
                  'from pathlib import Path; '
                  '\nwith t.environment_sync(Path(sys.argv[1])): '
                  't.run_command([sys.executable,"-c",' + repr(child) + ',sys.argv[2],sys.argv[3]])')
        owner = subprocess.Popen([sys.executable, '-c', driver, str(self.root), str(marker), str(identity)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 5
            while not identity.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(identity.exists())
            owner.send_signal(signal.SIGTERM)
            # TERM-ignoring installer is still mutating during its bounded grace.
            time.sleep(.1)
            with self.assertRaises(tooling.ActiveWorkflowError):
                with tooling.file_lock(tooling.lock_path(self.root)):
                    pass
            self.assertNotEqual(owner.wait(timeout=10), 0)
            with tooling.file_lock(tooling.lock_path(self.root)):
                count = marker.stat().st_size
                time.sleep(.15)
                self.assertEqual(marker.stat().st_size, count)
            self.assertFalse(tooling.enrolled(self.root))
        finally:
            if owner.poll() is None:
                owner.kill()
                owner.wait(timeout=3)
            if identity.exists():
                try:
                    os.killpg(int(identity.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_exact_clean_manager_and_submodule_provenance_required(self):
        def git(checkout, *args):
            if args == ('rev-parse', 'HEAD'):
                return self.declared['revision']
            if args == ('config', '--get', 'remote.origin.url'):
                return self.declared['repository']
            if args == ('submodule', 'status', '--recursive'):
                return ' ' + 'b' * 40 + ' Python/commonUtils'
            return ''
        with patch.object(tooling, 'git', side_effect=git):
            tooling.verify_checkout(self.root, self.declared)
        with patch.object(tooling, 'git', side_effect=lambda checkout, *args:
                          '+wrong Python/commonUtils' if args == ('submodule', 'status', '--recursive') else git(checkout, *args)):
            with self.assertRaises(ValueError):
                tooling.verify_checkout(self.root, self.declared)

    def test_cold_sdk_status_satisfies_public_manager_validator(self):
        from build_manager.project_tooling import validate_status
        self.target_environments()
        def absent_sdk(root,name,folder,interpreter,declared):
            with patch.object(tooling,'run',return_value=json.dumps(dict(prefix=str(folder),source_checkout=None))):
                return tooling.inspect_environment(root,name,folder,interpreter,declared)
        rows=[absent_sdk(self.root,*target,self.declared) for target in tooling.environments(self.root)]
        with patch.object(tooling,'inspect_environment',side_effect=rows):
            result=tooling.status(self.root)
        self.assertEqual(validate_status(result)['status'],'needs_update')
        self.assertFalse(result['ready'])
        self.assertTrue(all(row['installed_revision']=='' and row['source_checkout']=='' for row in result['environments']))
