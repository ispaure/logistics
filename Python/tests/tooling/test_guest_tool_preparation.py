"""Logistics pins feed reusable preparation without changing backend receipts."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
import os
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from build_manager.guest_tools import LINUX_BOOTSTRAP, WINDOWS_PREPARE, linux_parameters
from logistics_build import vm_backend, windows_backend


class GuestToolPreparationTests(unittest.TestCase):
    def test_portable_download_trust_preserves_custom_policy_and_restores_environment(self):
        from logistics_build.notebook_validation import download_certificates
        import certifi
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'failed download'):
                with download_certificates():
                    self.assertEqual(os.environ['SSL_CERT_FILE'], certifi.where())
                    raise RuntimeError('failed download')
            self.assertNotIn('SSL_CERT_FILE', os.environ)
        with patch.dict(os.environ, {'SSL_CERT_FILE': '/custom/roots.pem'}):
            with download_certificates():
                self.assertEqual(os.environ['SSL_CERT_FILE'], '/custom/roots.pem')
            self.assertEqual(os.environ['SSL_CERT_FILE'], '/custom/roots.pem')

    def test_notebook_guest_selection_preserves_full_coverage_and_timeout(self):
        from logistics_build.notebook_validation import arguments, command
        parser = argparse.ArgumentParser()
        arguments(parser, windows=True)
        args = parser.parse_args(['--notebook-profile', 'full', '--notebook-rendering', 'all',
                                  '--notebook-go', 'C:\\Tools\\go.exe'])
        argv, timeout = command(args, 'python.exe', 'reports', windows=True)
        self.assertIn('full', argv)
        self.assertEqual(argv[argv.index('--go') + 1], 'C:\\Tools\\go.exe')
        self.assertEqual(argv[argv.index('--latency-mode') + 1], 'enforce')
        from Python.tests.notebooks.notebook_platform_probe import PROBES
        self.assertEqual(timeout, sum(limit * (4 if renderer else 1)
                                      for _, limit, renderer in PROBES.values()) + 30)

    def test_notebook_linux_focus_forwards_noncore_checks(self):
        from logistics_build.notebook_validation import arguments, command
        parser = argparse.ArgumentParser()
        arguments(parser)
        args = parser.parse_args(['--notebook-probe', 'encrypted-storage',
                                  '--notebook-probe', 'mobile-laptop'])
        argv, timeout = command(args, 'python', 'reports')
        self.assertEqual(argv.count('--probe'), 2)
        self.assertIn('mobile-laptop', argv)
        self.assertEqual(timeout, 510)

    def test_linux_catalog_keeps_existing_runtime_and_uv_pins(self):
        catalog = json.loads(Path(vm_backend.__file__).with_name('build_manager_tools.json').read_text())
        self.assertEqual(linux_parameters(**catalog['linux']), dict(python='3.12.2', uv_version='0.13.4'))
        self.assertEqual(vm_backend.BOOTSTRAP, LINUX_BOOTSTRAP)

    def test_windows_preparation_delegates_with_project_pins_and_keeps_receipt(self):
        with TemporaryDirectory() as directory, patch.object(windows_backend, 'Parallels') as transport:
            client = transport.return_value
            client.start.return_value = dict(uuid='test-vm', status='stopped')
            client.powershell.side_effect = lambda vm, script, parameters, **kwargs: json.dumps(dict(
                token=parameters['token'], workspace='owned', python='python', uv='uv', git='git',
                runtime={'version': '3.12.2'}, guestArchitecture='ARM64', session=1))
            output = Path(directory) / 'prepared.json'
            result = windows_backend.prepare('selected-vm', output)
            client.start.assert_called_once_with('selected-vm')
            vm, script, parameters = client.powershell.call_args.args
            self.assertEqual((vm, script), ('test-vm', WINDOWS_PREPARE))
            self.assertEqual(parameters['python'], 'cpython-3.12.2-windows-x86_64')
            self.assertEqual(parameters['guest_architecture'], 'ARM64')
            self.assertEqual(parameters['python_architecture'], 'x86_64')
            self.assertEqual(parameters['tools']['uv']['version'], '0.13.4')
            self.assertEqual(result, json.loads(output.read_text()))
            self.assertEqual(result['status'], 'prepared')
            self.assertEqual(result['original_state'], 'stopped')
            self.assertFalse(result['tests_run'])

    def test_failed_preparation_retains_owned_recovery_identity(self):
        with TemporaryDirectory() as directory, patch.object(windows_backend, 'Parallels') as transport:
            client = transport.return_value
            client.start.return_value = dict(uuid='test-vm', status='stopped')
            client.powershell.side_effect = RuntimeError('download failed')
            output = Path(directory) / 'prepared.json'
            with self.assertRaisesRegex(RuntimeError, 'download failed'):
                windows_backend.prepare('selected-vm', output)
            result = json.loads(output.read_text())
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['vm'], 'test-vm')
            self.assertEqual(result['token'], client.powershell.call_args.args[2]['token'])
            self.assertFalse(result['tests_run'])

    def test_fedora_validation_failure_stops_only_the_vm_started_by_the_opted_in_run(self):
        for initial, shutdown, stops in (('stopped', True, True), ('stopped', False, False),
                                         ('running', True, False), ('suspended', True, False)):
            with self.subTest(initial=initial, shutdown=shutdown), TemporaryDirectory() as directory, \
                    patch.object(vm_backend, 'Parallels') as transport, patch.object(vm_backend.signal, 'signal'):
                results = Path(directory) / 'results'
                args = argparse.Namespace(vm='fedora-vm', results=results, source_identity={'commit': 'fixture'},
                                          distribution='fedora', container_image='', shutdown=shutdown)
                client = transport.return_value
                client.start.return_value = dict(uuid='fedora-vm', status=initial)
                client.execute.return_value = b'{"system":"Other OS"}'
                client.selected.return_value = dict(uuid='fedora-vm', status='stopped')
                with self.assertRaisesRegex(ValueError, 'requested Linux distribution'):
                    vm_backend.run(args)
                result = json.loads((results / 'result.json').read_text())
                self.assertEqual(result['status'], 'failed')
                self.assertEqual(result['stage'], 'guest-setup')
                self.assertEqual(result['original_state'], initial)
                self.assertIn('requested Linux distribution', result['error'])
                if stops:
                    client.shutdown.assert_called_once_with('fedora-vm')
                    self.assertEqual(result['vm_shutdown'],
                                     dict(command='succeeded', observed_state='stopped', state_verified=True))
                else:
                    client.shutdown.assert_not_called()
                    client.selected.assert_not_called()
                    self.assertNotIn('vm_shutdown', result)

    def test_shutdown_does_not_assume_an_ambiguous_start_changed_vm_power(self):
        with TemporaryDirectory() as directory, patch.object(vm_backend, 'Parallels') as transport, \
                patch.object(vm_backend.signal, 'signal'):
            results = Path(directory) / 'results'
            args = argparse.Namespace(vm='fedora-vm', results=results, source_identity={'commit': 'fixture'},
                                      distribution='fedora', shutdown=True)
            client = transport.return_value
            client.start.side_effect = RuntimeError('start acknowledgement lost')
            with self.assertRaisesRegex(RuntimeError, 'start acknowledgement lost'):
                vm_backend.run(args)
            client.shutdown.assert_not_called()
            client.selected.assert_not_called()
            result = json.loads((results / 'result.json').read_text())
            self.assertEqual((result['status'], result['stage']), ('failed', 'vm-start'))
            self.assertIn('start acknowledgement lost', result['error'])

    def test_fedora_cancellation_skips_guest_access_and_stops_only_after_an_acknowledged_start(self):
        from threading import Event
        for cancellation, stop_fails in (('before-start', False), ('after-start', False), ('after-start', True)):
            with self.subTest(cancellation=cancellation, stop_fails=stop_fails), TemporaryDirectory() as directory, \
                    patch.object(vm_backend, 'Parallels') as transport, patch.object(vm_backend.signal, 'signal'), \
                    patch.object(vm_backend, 'Event', return_value=Event()) as events:
                results = Path(directory) / 'results'
                args = argparse.Namespace(vm='fedora-vm', results=results, source_identity={'commit': 'fixture'},
                                          distribution='fedora', shutdown=True)
                client = transport.return_value
                cancelled = events.return_value
                client.selected.return_value = dict(uuid='fedora-vm', status='stopped')
                if cancellation == 'before-start':
                    cancelled.set()
                if stop_fails:
                    client.shutdown.side_effect = OSError('stop failed after cancellation')

                def start(vm):
                    cancelled.set()
                    return dict(uuid=vm, status='stopped')

                client.start.side_effect = start
                self.assertEqual(vm_backend.run(args), 1)
                client.execute.assert_not_called()
                result = json.loads((results / 'result.json').read_text())
                if cancellation == 'before-start':
                    client.start.assert_not_called()
                    client.shutdown.assert_not_called()
                    self.assertEqual((result['status'], result['stage']), ('cancelled', 'vm-start'))
                else:
                    client.shutdown.assert_called_once_with('fedora-vm')
                    if stop_fails:
                        self.assertEqual(result['status'], 'failed')
                        self.assertEqual(result['vm_shutdown']['prior_status'], 'cancelled')
                    else:
                        self.assertEqual(result['status'], 'cancelled')
                        self.assertTrue(result['vm_shutdown']['state_verified'])

    def test_fedora_shutdown_follows_guest_result_collection_and_workspace_removal(self):
        with TemporaryDirectory() as directory, patch.object(vm_backend, 'Parallels') as transport, \
                patch.object(vm_backend.signal, 'signal'), patch.object(vm_backend, 'source_members', return_value=()):
            root = Path(directory)
            source = {'commit': 'fixture'}
            args = argparse.Namespace(vm='fedora-vm', results=root / 'results', source_identity=source,
                                      distribution='fedora', container_image='', shutdown=True,
                                      snapshot=Path(vm_backend.__file__).resolve().parents[1], manager_checkout=None,
                                      pattern='')
            client = transport.return_value
            client.start.return_value = dict(uuid='fedora-vm', status='stopped')
            client.selected.return_value = dict(uuid='fedora-vm', status='stopped')
            client.execute.return_value = json.dumps(dict(system='Linux', os_release='ID=fedora\nVERSION_ID=44',
                                                          users=[dict(uid=1000, gid=1000)])).encode()
            client.execute_idempotent.return_value = b'True'
            client.stage.return_value = 'staged-source'
            client.run_owned.return_value = 0

            def collect(vm, workspace, token, destination):
                report = destination / 'reports/manager/result.json'
                report.parent.mkdir(parents=True)
                report.write_text(json.dumps(dict(source=source, backend='Parallels fedora',
                                                  status='passed', phases=[dict(id='release-tooling', status='passed')])))

            def remove(vm, workspace, token):
                client.collect.assert_called_once()

            def shutdown(vm):
                client.remove.assert_called_once()

            client.collect.side_effect = collect
            client.remove.side_effect = remove
            client.shutdown.side_effect = shutdown
            self.assertEqual(vm_backend.run(args), 0)
            client.shutdown.assert_called_once_with('fedora-vm')
            result = json.loads((args.results / 'result.json').read_text())
            self.assertEqual(result['status'], 'passed')
            self.assertEqual(result['phases'], [dict(id='release-tooling', status='passed')])
            self.assertTrue(result['guest_workspace_removed'])
            self.assertTrue(result['vm_shutdown']['state_verified'])

    def test_windows_preparation_failure_remains_primary_when_shutdown_also_fails(self):
        from logistics_build.guest_attempts import reconcile_setup, result_attempt
        with TemporaryDirectory() as directory, patch.object(windows_backend, 'Parallels') as transport, \
                patch.object(windows_backend.signal, 'signal'):
            results = Path(directory) / 'results'
            source = {'commit': 'fixture'}
            args = argparse.Namespace(vm='windows-vm', results=results, source_identity=source,
                                      prepared=None, shutdown=True)
            client = transport.return_value
            client.start.side_effect = [dict(uuid='windows-vm', status='stopped'),
                                        dict(uuid='windows-vm', status='running')]
            client.powershell.side_effect = RuntimeError('Windows preparation failed')
            client.shutdown.side_effect = RuntimeError('shutdown command failed')
            with self.assertRaisesRegex(RuntimeError, '^Windows preparation failed$'):
                windows_backend.run(args)
            client.shutdown.assert_called_once_with('windows-vm')
            client.selected.assert_not_called()
            report_path = results / 'result.json'
            original = report_path.read_bytes()
            report = json.loads(original)
            self.assertEqual((report['status'], report['stage']), ('failed', 'guest-setup'))
            self.assertEqual(report['error'], 'Windows preparation failed')
            self.assertEqual(report['vm_shutdown'],
                             dict(command='failed', state_verified=False, error='shutdown command failed'))
            self.assertEqual(json.loads((Path(report['attempt_directory']) / 'result.json').read_text()),
                             {key: value for key, value in report.items() if key != 'attempt_directory'})
            with self.assertRaisesRegex(ValueError, 'reconciliation'):
                with result_attempt(results, source, 'Parallels Windows'):
                    self.fail('Failed setup was replayed without an absence receipt')
            proof = reconcile_setup(results, lambda vm, token: dict(vm=vm, token=token, exists=False))
            self.assertTrue(proof.is_file())
            self.assertEqual(report_path.read_bytes(), original)
            with result_attempt(results, source, 'Parallels Windows') as retry:
                self.assertNotEqual(retry, Path(report['attempt_directory']))

    def test_windows_attempt_reclaims_only_disposable_tools_after_evidence_transfer(self):
        tool_paths = {'environment', 'cache', 'python', 'tools', 'downloads'}
        for reuse, transfer_fails, cleanup_fails, shutdown_fails, observed in (
            (False, False, False, False, 'stopped'), (True, False, False, False, 'stopped'),
            (False, True, False, False, 'stopped'), (False, False, True, False, 'stopped'),
            (False, False, False, True, None),
        ):
            with self.subTest(reuse=reuse, transfer_fails=transfer_fails, cleanup_fails=cleanup_fails,
                              shutdown_fails=shutdown_fails, observed=observed), \
                    TemporaryDirectory() as directory:
                root = Path(directory)
                source = {'commit': 'fixture'}
                prepared = dict(vm='test-vm', status='prepared', token='a' * 32, workspace=r'C:\bm\fixture',
                                python='python', git='git', runtime={}, guestArchitecture='ARM64')
                reference = root / 'prepared.json' if reuse else None
                if reference:
                    reference.write_text(json.dumps(prepared))
                args = argparse.Namespace(vm='test-vm', prepared=reference, results=root / 'attempt',
                                          snapshot=root, source_identity=source, manager_checkout=None,
                                          pattern='', shutdown=True)
                with patch.object(windows_backend, 'Parallels') as transport, \
                        patch.object(windows_backend, 'prepare', return_value=prepared) as prepare, \
                        patch.object(windows_backend, 'WindowsGuest') as guest_class, \
                        patch.object(windows_backend, 'source_zip', return_value=b'source'), \
                        patch.object(windows_backend.signal, 'signal'):
                    client = transport.return_value
                    client.start.return_value = dict(uuid='test-vm', status='stopped')
                    client.selected.return_value = dict(uuid='test-vm', status=observed)
                    guest = guest_class.return_value
                    guest.call_idempotent.return_value = json.dumps(dict(runtime={}, git='git', path=''))
                    guest.run.return_value = 0
                    evidence = []

                    def collect(paths, destination):
                        if transfer_fails:
                            raise OSError('evidence transfer failed')
                        report = destination / paths[0] / 'manager/result.json'
                        report.parent.mkdir(parents=True)
                        report.write_text(json.dumps(dict(source=source, backend='Parallels Windows',
                                                          status='passed', phases=[])))
                        evidence.append(report)

                    def remove(paths):
                        self.assertTrue(evidence[0].is_file())
                        self.assertEqual(tool_paths.intersection(paths), set() if reuse else tool_paths)
                        if cleanup_fails:
                            raise OSError('cleanup failed')

                    def shutdown(vm):
                        guest.collect.assert_called_once()
                        if not transfer_fails:
                            guest.remove_paths.assert_called_once()
                        if shutdown_fails:
                            raise OSError('stop failed')

                    guest.collect.side_effect = collect
                    guest.remove_paths.side_effect = remove
                    client.shutdown.side_effect = shutdown
                    expected_failure = transfer_fails or cleanup_fails or shutdown_fails
                    self.assertEqual(windows_backend._run_attempt(args), int(expected_failure))
                    client.shutdown.assert_called_once_with('test-vm')
                    if reuse:
                        prepare.assert_not_called()
                    else:
                        prepare.assert_called_once_with('test-vm', args.results / 'prepared.json')
                    if transfer_fails:
                        guest.remove_paths.assert_not_called()
                    else:
                        guest.remove_paths.assert_called_once()
                    result = json.loads((args.results / 'result.json').read_text())
                    self.assertEqual(result['public_tool_cache_retained'], reuse or transfer_fails or cleanup_fails)
                    if shutdown_fails:
                        self.assertEqual(result['status'], 'failed')
                        self.assertEqual(result['vm_shutdown']['error'], 'stop failed')
                        self.assertEqual(result['vm_shutdown']['prior_status'], 'passed')
                        client.selected.assert_not_called()
                    else:
                        client.selected.assert_called_once_with('test-vm')
                        self.assertEqual(result['vm_shutdown'], dict(command='succeeded', observed_state=observed,
                                                                     state_verified=observed == 'stopped'))

    def test_shutdown_rechecks_a_stopping_guest(self):
        from logistics_build import guest_results

        with patch.object(guest_results.time, 'sleep') as wait:
            client = Mock()
            client.selected.side_effect = [
                dict(uuid='owned-vm', status='stopping'),
                dict(uuid='owned-vm', status='stopped'),
            ]
            result = dict(status='passed')
            guest_results._stop_started_guest(client, 'owned-vm', result)

        client.shutdown.assert_called_once_with('owned-vm')
        self.assertEqual([entry.args for entry in client.selected.call_args_list], [('owned-vm',), ('owned-vm',)])
        wait.assert_called_once_with(5)
        self.assertEqual(result, dict(status='passed', vm_shutdown=dict(
            command='succeeded', observed_state='stopped', state_verified=True)))

    def test_acknowledged_shutdown_requires_the_exact_guest_to_be_stopped(self):
        from logistics_build import guest_results

        cases = (
            (dict(uuid='owned-vm', status='running'), 'observed_state', 'running'),
            (dict(uuid='other-vm', status='stopped'), 'observation_error', 'different guest UUID'),
            (RuntimeError('inventory unavailable'), 'observation_error', 'inventory unavailable'),
        )
        for observation, field, detail in cases:
            with self.subTest(detail=detail), patch.object(guest_results.time, 'sleep') as wait:
                client = Mock()
                client.selected.side_effect = [observation]
                result = dict(status='cancelled', error='primary result preserved')
                guest_results._stop_started_guest(client, 'owned-vm', result)
                client.shutdown.assert_called_once_with('owned-vm')
                client.selected.assert_called_once_with('owned-vm')
                wait.assert_not_called()
                self.assertEqual(result['status'], 'failed')
                self.assertEqual(result['error'], 'primary result preserved')
                teardown = result['vm_shutdown']
                self.assertEqual(teardown['command'], 'succeeded')
                self.assertFalse(teardown['state_verified'])
                self.assertEqual(teardown['prior_status'], 'cancelled')
                self.assertIn('stop could not be verified', teardown['error'])
                self.assertIn(detail, teardown[field])
