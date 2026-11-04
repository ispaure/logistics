"""Original native process evidence must never replay a failing application."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from mobile_build.validation import ios_failure_diagnostics as diagnostics


class OriginalProcessTests(unittest.TestCase):
    def fixture(self, root):
        source = dict(logistics_commit='a', commonUtils_commit='b', source_sha256='c')
        marker = dict(pid=123, started_ns=5_000_000_000, source=source)
        (root / 'ios-native-ui-owned.json').write_text(json.dumps(dict(device='owned', name='Logistics Native Gate unit')))
        (root / 'ios-native-ui-device.json').write_text(json.dumps(dict(device='owned', started_ns=4_000_000_000, source=source)))
        return marker, dict(started_ns=4_000_000_000, executable='/owned/App.app/Logistics Mobile')

    def record(self, root, marker, identity):
        with patch.object(diagnostics, 'process_identity', return_value=identity), patch.object(
                diagnostics.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='/owned/App.app\n')) as run:
            diagnostics.record_process(root, marker)
            self.assertEqual(run.call_args.args[0], ['xcrun', 'simctl', 'get_app_container', 'owned', diagnostics.BUNDLE, 'app'])

    def test_live_original_sampled_once_and_ownership_unchanged(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);marker,identity=self.fixture(root);self.record(root,marker,identity)
            owner=(root/'ios-native-ui-owned.json').read_bytes()
            def sample(command, **kwargs):
                self.assertEqual(command[:3], ['sample','123','3'])
                Path(command[-1]).write_text('original process stacks')
                return SimpleNamespace(returncode=0)
            with patch.object(diagnostics, 'process_identity', return_value=identity), patch.object(diagnostics.subprocess,'run',side_effect=sample) as run:
                self.assertTrue(diagnostics.sample_original(root)['sampled'])
                self.assertFalse(diagnostics.sample_original(root)['sampled'])
                run.assert_called_once()
            self.assertEqual((root/'ios-native-ui-owned.json').read_bytes(),owner)

    def test_dead_or_reused_pid_is_not_sampled(self):
        for current,status in ((None,'original-process-dead'),(dict(started_ns=6_000_000_000,executable='/owned/App.app/Logistics Mobile'),'original-process-identity-changed'),(dict(started_ns=4_000_000_000,executable='/other/App.app/Logistics Mobile'),'original-process-identity-changed')):
            with self.subTest(status=status),TemporaryDirectory() as directory:
                root=Path(directory);marker,identity=self.fixture(root);self.record(root,marker,identity)
                with patch.object(diagnostics,'process_identity',return_value=current),patch.object(diagnostics.subprocess,'run') as run:
                    self.assertEqual(diagnostics.sample_original(root)['status'],status)
                    run.assert_not_called()

    def test_foreign_source_and_unowned_device_cannot_establish_identity(self):
        for change in ('source','owner','start'):
            with self.subTest(change=change),TemporaryDirectory() as directory:
                root=Path(directory);marker,_=self.fixture(root)
                if change=='source':marker['source']['source_sha256']='foreign'
                if change=='owner':(root/'ios-native-ui-owned.json').unlink()
                if change=='start':marker['started_ns']=1
                with patch.object(diagnostics.subprocess,'run') as run:
                    diagnostics.record_process(root,marker)
                    self.assertFalse(diagnostics.sample_original(root)['sampled'])
                    run.assert_not_called()

    def test_later_startup_cannot_replace_original_identity(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);marker,identity=self.fixture(root);self.record(root,marker,identity)
            before=(root/'ios-native-ui-process.json').read_bytes()
            with patch.object(diagnostics.subprocess,'run') as run:
                diagnostics.record_process(root,dict(marker,pid=456))
                run.assert_not_called()
            self.assertEqual((root/'ios-native-ui-process.json').read_bytes(),before)

    def test_unverified_identity_cannot_sample(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);self.fixture(root)
            with patch.object(diagnostics.subprocess,'run') as run:
                self.assertEqual(diagnostics.sample_original(root)['status'],'identity-unverified')
                run.assert_not_called()

    def test_process_identity_uses_executable_and_start_time(self):
        with patch.object(diagnostics.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='Wed Nov  4 15:09:10 2026 /owned/App.app/Logistics Mobile\n')) as run:
            result=diagnostics.process_identity(123)
            self.assertEqual(result['executable'],'/owned/App.app/Logistics Mobile')
            self.assertGreater(result['started_ns'],0)
            self.assertNotIn('launch',run.call_args.args[0])

    def test_progress_binds_startup_marker_without_launch_or_restart(self):
        from threading import Event
        from mobile_build.validation import ui_tools
        with TemporaryDirectory() as directory:
            root=Path(directory);marker,_=self.fixture(root)
            path=root/'ios-native-ui.log';path.write_text('LOGISTICS_NATIVE_PROCESS='+json.dumps(marker)+'\n')
            stopped=Event();stopped.set()
            with patch.object(diagnostics,'record_process') as record,patch.object(ui_tools,'record_host_memory'),patch.object(ui_tools.subprocess,'run') as run:
                ui_tools._progress(path,stopped)
                record.assert_called_once_with(root,marker)
                run.assert_not_called()

    def test_dead_original_preserves_matching_fresh_ips_without_replay(self):
        import os
        from mobile_build.validation import ui_tools
        with TemporaryDirectory() as directory:
            base=Path(directory);root=base/'logs';root.mkdir();marker,identity=self.fixture(root);self.record(root,marker,identity)
            reports=base/'Library/Logs/DiagnosticReports';reports.mkdir(parents=True)
            report=reports/'original.ips';report.write_text('{"app_name":"Logistics Mobile"}\n'+json.dumps(dict(pid=123)))
            other=reports/'other.ips';other.write_text('{"app_name":"Logistics Mobile"}\n'+json.dumps(dict(pid=456)))
            def command(argv,**kwargs):
                self.assertNotIn('launch',argv)
                if argv[0]=='ps':return SimpleNamespace(returncode=0,stdout='',stderr='')
                kwargs['stdout'].write('retained host evidence\n')
                return SimpleNamespace(returncode=0)
            previous=Path.cwd();os.chdir(base)
            try:
                with patch.object(ui_tools,'simulator_report'),patch.object(ui_tools.Path,'home',return_value=base),patch.object(diagnostics,'process_identity',return_value=None),patch.object(ui_tools.subprocess,'run',side_effect=command):
                    ui_tools.ios_diagnostics()
                self.assertTrue((root/'original.ips').exists())
                self.assertFalse((root/'other.ips').exists())
                self.assertEqual(json.loads((root/'ios-original-process-diagnostics.json').read_text())['status'],'original-process-dead')
            finally:os.chdir(previous)

    def test_rotation_failure_cache_is_retained_read_only(self):
        from mobile_build.validation import ui_tools
        with TemporaryDirectory() as directory:
            root=Path(directory);cache=root/'Library/Caches';cache.mkdir(parents=True)
            snapshot=cache/'logistics-native-ui-rotation-failure.json';snapshot.write_text('{"panel":"folder"}')
            with patch.object(ui_tools.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=str(root))):
                ui_tools.simulator_report('owned',1,diagnostics=root/'logs')
            self.assertEqual((root/'logs/ios-native-ui-rotation-failure.json').read_bytes(),snapshot.read_bytes())

    def test_invalid_owner_name_is_unavailable_without_process_inspection(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);marker,_=self.fixture(root)
            (root/'ios-native-ui-owned.json').write_text(json.dumps(dict(device='owned',name=123)))
            with patch.object(diagnostics.subprocess,'run') as run:
                diagnostics.record_process(root,marker)
                self.assertFalse(diagnostics.sample_original(root)['sampled'])
                run.assert_not_called()

    def test_broken_identity_observer_does_not_stop_later_checkpoints(self):
        from threading import Event
        from mobile_build.validation import ui_tools
        with TemporaryDirectory() as directory:
            path=Path(directory)/'ios-native-ui.log'
            path.write_text('LOGISTICS_NATIVE_PROCESS={}\nLOGISTICS_NATIVE_CASE=native_hub\n')
            stopped=Event();stopped.set()
            with patch.object(diagnostics,'record_process',side_effect=RuntimeError('observer')),patch.object(ui_tools,'record_host_memory'),patch.object(ui_tools,'log') as log:
                ui_tools._progress(path,stopped)
            self.assertTrue(any(call.args[1:] == ('Native checkpoint','native_hub') for call in log.call_args_list))

    def test_corrupt_missing_or_partial_receipt_preserves_host_evidence_without_device_fallback(self):
        import os
        from mobile_build.validation import ui_tools
        for raw in (None,'{','[]','{}'):
            with self.subTest(raw=raw),TemporaryDirectory() as directory:
                base=Path(directory);logs=base/'logs';logs.mkdir()
                if raw is not None:(logs/'ios-native-ui-device.json').write_text(raw)
                commands=[]
                def command(argv,**kwargs):
                    commands.append(argv)
                    self.assertNotIn('simctl',argv)
                    if argv[0]=='ps':return SimpleNamespace(returncode=0,stdout='',stderr='')
                    kwargs['stdout'].write('host evidence\n');return SimpleNamespace(returncode=0)
                previous=Path.cwd();os.chdir(base)
                try:
                    with patch.object(ui_tools.Path,'home',return_value=base),patch.object(ui_tools,'ios_device',side_effect=AssertionError('No fallback')),patch.object(ui_tools.subprocess,'run',side_effect=command):
                        ui_tools.ios_diagnostics()
                    self.assertEqual(json.loads((logs/'ios-original-process-diagnostics.json').read_text())['status'],'identity-unverified')
                    for name in ('host-memory.txt','host-vm.txt','host-webkit-processes.txt'):self.assertTrue((logs/name).exists())
                    self.assertFalse(any('launch' in argv for argv in commands))
                finally:os.chdir(previous)
