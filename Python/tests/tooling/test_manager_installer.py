"""Pinned read retries are narrow, staged, bounded and never touch existing checkouts."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('project_manager_installer', ROOT/'logistics_build/install_build_manager.py')
installer = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(installer)
SHA = 'a'*40


class ManagerInstallerTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(TemporaryDirectory())).resolve()
        (self.root/'logistics_build').mkdir()
        (self.root/'build-manager-dependency.json').write_text(json.dumps(dict(schema=1,adapter_api=1,
            repository='https://github.com/fixture/manager.git',revision=SHA)))
        self.destination=self.root/'tools/manager'
        self.clones=[];self.commands=[];self.failures=[];self.installs=[]
        self.enterContext(patch.object(installer,'__file__',str(self.root/'logistics_build/install_build_manager.py')))

    def command(self,argv,**kwargs):
        argv=[str(part) for part in argv];self.commands.append((argv,kwargs))
        if argv[:2]==['git','clone']:
            path=Path(argv[-1]);self.clones.append(path);path.mkdir(parents=True)
            (path/'partial').write_text('owned partial clone')
            if self.failures:
                failure=self.failures.pop(0)
                if failure:raise subprocess.CalledProcessError(128,argv,stderr=failure)
            (path/'Python').mkdir()
            (path/'Python/pyproject.toml').write_text('[project]\nname="build-deployment-manager"\n')
            return subprocess.CompletedProcess(argv,0,'','')
        if argv[:2]==['git','-C']:
            if 'rev-parse' in argv:return subprocess.CompletedProcess(argv,0,SHA+'\n','')
            return subprocess.CompletedProcess(argv,0,'','')
        self.installs.append(argv)
        return subprocess.CompletedProcess(argv,0,'','')

    def execute(self, *, command=None):
        with patch.object(sys,'argv',['installer','--from-pin',str(self.destination)]), \
                patch.object(installer.subprocess,'run',side_effect=command or self.command), \
                patch.object(installer.importlib.util,'find_spec',return_value=object()):
            return installer.main()

    def test_transport_reset_retries_once_in_fresh_owned_stage_and_publishes_exact_pin(self):
        self.failures=['fatal: Recv failure: Connection reset by peer',None]
        self.assertEqual(self.execute(),0)
        self.assertEqual(len(self.clones),2);self.assertNotEqual(*self.clones)
        self.assertTrue(all(path!=self.destination for path in self.clones))
        self.assertTrue((self.destination/'Python/pyproject.toml').is_file())
        self.assertTrue(all(not path.parent.exists() for path in self.clones))
        self.assertEqual(len(self.installs),1)
        self.assertTrue(all(0<kw['timeout']<=45 for argv,kw in self.commands if argv[0]=='git'))
        checkouts=[argv for argv,_ in self.commands if 'checkout' in argv]
        self.assertTrue(all(argv[-2:]==['--detach',SHA] for argv in checkouts))

    def test_auth_unknown_and_invalid_reference_fail_without_retry_or_install(self):
        for failure in ('fatal: Authentication failed','fatal: repository not found','fatal: not a valid object name',
                        'fatal: unexplained failure','fatal: Authentication failed; Connection reset by peer'):
            with self.subTest(failure=failure):
                self.clones.clear();self.commands.clear();self.failures=[failure]
                with self.assertRaises(subprocess.CalledProcessError):self.execute()
                self.assertEqual(len(self.clones),1)
                self.assertFalse(self.destination.exists());self.assertFalse(self.installs)
                self.assertTrue(all(not path.parent.exists() for path in self.clones))

    def test_two_transport_failures_stop_without_publishing_or_leaving_partial_stage(self):
        self.failures=['Recv failure: Connection reset by peer']*2
        with self.assertRaises(subprocess.CalledProcessError):self.execute()
        self.assertEqual(len(self.clones),2)
        self.assertFalse(self.destination.exists());self.assertFalse(self.installs)
        self.assertTrue(all(not path.parent.exists() for path in self.clones))

    def test_existing_checkout_and_link_are_preserved_without_any_git_command(self):
        self.destination.mkdir(parents=True);(self.destination/'personal').write_text('preserve')
        with self.assertRaises(SystemExit):self.execute()
        self.assertEqual((self.destination/'personal').read_text(),'preserve');self.assertFalse(self.commands)

    def test_invalid_pin_is_rejected_before_clone(self):
        path=self.root/'build-manager-dependency.json';data=json.loads(path.read_text());data['revision']='not-a-sha'
        path.write_text(json.dumps(data))
        with self.assertRaises(SystemExit):self.execute()
        self.assertFalse(self.commands)

    def test_timeout_and_total_budget_never_retry_or_leave_stage(self):
        def timeout(argv,**kwargs):
            self.commands.append((argv,kwargs))
            raise subprocess.TimeoutExpired(argv,kwargs['timeout'])
        with self.assertRaises(subprocess.TimeoutExpired):self.execute(command=timeout)
        self.assertEqual(len(self.commands),1)
        self.assertFalse(list(self.destination.parent.glob('.manager-clone-*')))
        self.assertFalse(self.destination.exists())
        self.commands.clear()
        with patch.object(installer.time,'monotonic',side_effect=[0,111]):
            with self.assertRaises(subprocess.TimeoutExpired):self.execute()
        self.assertFalse(self.commands);self.assertFalse(self.installs)

    def test_wrong_head_and_uninitialized_submodule_fail_before_atomic_publication(self):
        original=self.command
        for stage in ('head','submodule'):
            with self.subTest(stage=stage):
                self.clones.clear()
                def altered(argv,**kwargs):
                    result=original(argv,**kwargs)
                    if stage=='head' and 'rev-parse' in argv:result.stdout='b'*40
                    if stage=='submodule' and 'submodule' in argv and 'status' in argv:result.stdout='-'+SHA+' Python/commonUtils\n'
                    return result
                with self.assertRaises(SystemExit):self.execute(command=altered)
                self.assertEqual(len(self.clones),1)
                self.assertFalse(self.destination.exists());self.assertFalse(self.installs)
                self.assertTrue(all(not path.parent.exists() for path in self.clones))

    def test_destination_appearing_before_publish_is_preserved(self):
        original=self.command
        def appeared(argv,**kwargs):
            result=original(argv,**kwargs)
            if '--porcelain' in argv:
                self.destination.mkdir();(self.destination/'personal').write_text('keep')
            return result
        with self.assertRaises(SystemExit):self.execute(command=appeared)
        self.assertEqual((self.destination/'personal').read_text(),'keep')
        self.assertFalse(self.installs)
        self.assertTrue(all(not path.parent.exists() for path in self.clones))

    def test_dangling_selector_and_credential_bearing_repository_are_not_touched(self):
        self.destination.parent.mkdir()
        self.destination.symlink_to(self.root/'absent',target_is_directory=True)
        with self.assertRaises(SystemExit):self.execute()
        self.assertTrue(self.destination.is_symlink());self.assertFalse(self.commands)
        self.destination.unlink()
        path=self.root/'build-manager-dependency.json';data=json.loads(path.read_text())
        data['repository']='https://example:secret@github.com/fixture/manager.git';path.write_text(json.dumps(data))
        with self.assertRaises(SystemExit):self.execute()
        self.assertFalse(self.commands)

    def test_malformed_pin_types_do_not_start_a_transport_operation(self):
        path=self.root/'build-manager-dependency.json'
        valid=json.loads(path.read_text())
        for value in ([],dict(valid,schema=True),dict(valid,revision=None),dict(valid,repository=None)):
            with self.subTest(value=value):
                path.write_text(json.dumps(value))
                with self.assertRaises(SystemExit):self.execute()
                self.assertFalse(self.commands)

    def test_failure_diagnostics_keep_reset_auth_and_unknown_context_but_redact_secrets(self):
        import io
        from contextlib import redirect_stderr
        for message in ('fatal: Recv failure: Connection reset by peer',
                        'fatal: Authentication failed', 'fatal: unknown protocol diagnostic marker'):
            stream=io.StringIO()
            secret='sensitive-fixture-value'
            stderr=message+'\nhttps://user:credential@github.com/repo?token=querysecret\nAuthorization: Bearer headersecret\ntoken=assignmentsecret\n'+secret
            error=subprocess.CalledProcessError(128,['git'],stderr=stderr)
            with patch.dict(installer.os.environ,GH_TOKEN=secret),redirect_stderr(stream):
                installer.failure_evidence(error,attempt=1,step='clone',retry=False,classification='fixture')
            tail=json.loads(stream.getvalue())['diagnostic_tail']
            self.assertIn(message,tail)
            for value in ('credential','querysecret','headersecret','assignmentsecret',secret):
                self.assertNotIn(value,tail.replace('[credentials]',''))
            self.assertLessEqual(len(tail),2048)

    def test_diagnostic_fallback_without_commonutils_is_bounded_and_redacts_private_data(self):
        import builtins
        original=builtins.__import__
        def no_shared(name,*args,**kwargs):
            if name.startswith('commonUtils'):raise ImportError('not initialized')
            return original(name,*args,**kwargs)
        text='fatal: unknown diagnostic marker\nhttps://u:secret@host/x?token=unsafe\nAuthorization: Basic abc123\n-----BEGIN PRIVATE KEY-----\nprivatekeybody'
        with patch('builtins.__import__',side_effect=no_shared):
            tail=installer.diagnostic_tail(text)
        self.assertIn('unknown diagnostic marker',tail)
        for value in ('unsafe','abc123','privatekeybody','u:secret'):self.assertNotIn(value,tail)
        self.assertLessEqual(len(installer.diagnostic_tail('x'*10000)),2048)

    def test_failed_diagnostic_output_does_not_replace_primary_git_failure(self):
        self.failures=['fatal: unknown transport marker']
        with patch.object(installer,'print',side_effect=OSError('unavailable log stream'),create=True):
            with self.assertRaises(subprocess.CalledProcessError) as failure:self.execute()
        self.assertEqual(failure.exception.returncode,128)
        self.assertEqual(len(self.clones),1)
