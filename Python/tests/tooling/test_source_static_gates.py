"""Actual source gates precede full mobile host/native work; cleanup is retained."""
from dataclasses import replace
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.testing.stages import TestStage
from build_manager import Phase,Plan
from build_manager.executor import Executor
from logistics_build.manager_suites import with_host_gates

TEST_STAGE=TestStage.REGRESSION
STATIC=('source-architecture','source-toolchain','source-hygiene','source-lint')


class SourceStaticGateTests(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.subject=Phase('android-build',(sys.executable,'-c','pass'),str(self.root),environment={'FIXTURE':'value'},kind='build')
        self.cleanup=Phase('android-cleanup',(sys.executable,'-c','pass'),str(self.root),kind='cleanup',always=True,dependencies=('android-build',))
        self.plan=Plan('Fixture','Test',{},(self.subject,self.cleanup),str(self.root/'workspace'),backend='This Mac')
        self.host=Phase('mobile-host',(sys.executable,'-c','pass'),str(self.root))

    def planned(self):
        with patch('build_manager.test_manifest.phases',return_value=(self.host,)):
            return with_host_gates(self.plan,sys.executable)

    def test_same_ci_owner_commands_and_full_dependency_graph(self):
        plan=self.planned();rows={p.id:p for p in plan.phases}
        for name in STATIC:
            phase=rows[name];command=name.removeprefix('source-')
            expected=(sys.executable,'dev.py',command,* (('--python',sys.executable) if command=='lint' else ()))
            self.assertEqual(phase.argv,expected);self.assertEqual(phase.cwd,str(self.root));self.assertEqual(phase.environment,self.subject.environment)
            self.assertEqual(phase.effect,'inspect');self.assertIn(name,rows['mobile-host'].dependencies);self.assertIn(name,rows['android-build'].dependencies)
        self.assertEqual(rows['android-cleanup'],self.cleanup)
        self.assertNotIn('source-architecture',[p.id for p in self.plan.phases])

    def test_real_executor_source_failure_blocks_host_and_build_but_runs_cleanup(self):
        host=self.root/'host';build=self.root/'build';cleanup=self.root/'cleanup'
        def write(path):return (sys.executable,'-c','from pathlib import Path;Path('+repr(str(path))+').touch()')
        plan=self.planned();phases=[]
        for phase in plan.phases:
            argv=(sys.executable,'-c','pass')
            if phase.id=='source-architecture':argv=(sys.executable,'-c','raise SystemExit(1)')
            elif phase.id=='mobile-host':argv=write(host)
            elif phase.id=='android-build':argv=write(build)
            elif phase.id=='android-cleanup':argv=write(cleanup)
            phases.append(replace(phase,argv=argv))
        plan=replace(plan,phases=tuple(phases))
        result=Executor(resource_directory=self.root/'resources',evidence_directory=self.root/'evidence').run(plan,self.root/'run')
        rows={p['id']:p for p in result['phases']}
        self.assertEqual(result['status'],'failed');self.assertEqual(rows['source-architecture']['status'],'failed')
        self.assertFalse(host.exists());self.assertFalse(build.exists());self.assertTrue(cleanup.exists())
        self.assertEqual(rows['android-cleanup']['status'],'passed')

    def test_mobile_smoke_failure_blocks_remaining_and_native_gates_for_each_platform(self):
        for target in ('ios', 'android'):
            with self.subTest(target=target):
                environment = {'MARKER': target}
                command = (sys.executable, 'Python/tests/run_regressions.py', 'suite', '--isolate-modules')
                smoke = replace(self.host, id='mobile-host.smoke', environment=environment,
                                argv=(*command, '--profile', 'smoke', '--mode', 'fast'))
                broad = replace(self.host, argv=command, environment=environment, dependencies=(smoke.id,))
                native = replace(self.subject, id=target + '-native')
                cleanup = replace(self.cleanup, id=target + '-cleanup', dependencies=(native.id,))
                draft = replace(self.plan, phases=(native, cleanup))
                with patch('build_manager.test_manifest.phases', return_value=(smoke, broad)):
                    planned = with_host_gates(draft, sys.executable)
                rows = {phase.id: phase for phase in planned.phases}
                self.assertEqual(rows[broad.id].argv[-4:], ('--stage', 'regression', '--stage', 'extended'))
                self.assertIn(smoke.id, rows[broad.id].dependencies)
                self.assertIn(broad.id, rows[native.id].dependencies)
                planned = replace(planned, phases=tuple(replace(phase, argv=(sys.executable, '-c',
                    'raise SystemExit(1)' if phase.id == smoke.id else 'pass')) for phase in planned.phases))
                result = Executor(resource_directory=self.root/'resources', evidence_directory=self.root/'evidence').run(
                    planned, self.root/target)
                statuses = {phase['id']: phase['status'] for phase in result['phases']}
                self.assertEqual(result['status'], 'failed')
                self.assertEqual([statuses[name] for name in (smoke.id, broad.id, native.id, cleanup.id)],
                                 ['failed', 'skipped', 'skipped', 'passed'])
