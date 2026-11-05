"""Native prerequisites fail before host work without installing any tooling."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import zipfile
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from build_manager import Phase, Plan
from build_manager.executor import Executor
from build_manager.workflows import require_build_only
from logistics_build import native_prerequisites as owner

ROOT = Path(__file__).resolve().parents[3]


class NativePrerequisiteTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.go = self.root / 'go'; self.go.touch()
        from logistics_build.native_tooling import declared, digest
        self.wheelhouse=self.root/'wheelhouse';self.wheelhouse.mkdir()
        wheel=self.wheelhouse/'langdetect-1.0.9-py3-none-any.whl'
        with zipfile.ZipFile(wheel,'w') as archive:
            archive.writestr('langdetect/__init__.py','# fixture')
            archive.writestr('langdetect-1.0.9.dist-info/METADATA','Name: langdetect\nVersion: 1.0.9\n')
            archive.writestr('langdetect-1.0.9.dist-info/WHEEL','Root-Is-Purelib: true\nTag: py3-none-any\n')
        (self.wheelhouse/'langdetect-receipt.json').write_text(json.dumps(dict(schema=1,
            filename=wheel.name,source_sha256=declared()['langdetect']['sha256'],wheel_sha256=digest(wheel))))
        self.enterContext(patch('logistics_build.native_tooling.wheel_status', return_value=dict(ready=True, filename='langdetect-1.0.9-py3-none-any.whl')))

    def fixture_plan(self, ids=('ios-build',), backend='This Mac', effect='build'):
        phases = tuple(Phase(name, (sys.executable, '-c', 'pass'), str(ROOT), kind='build' if name in owner.BUILD_PHASES else 'test', effect=effect) for name in ids)
        return Plan('Fixture','Native prerequisites',{},phases,str(self.root/'workspace'),backend=backend,effect=effect)

    def version_command(self, argv, **kwargs):
        self.assertEqual(kwargs['timeout'], 10)
        self.assertTrue(kwargs['capture_output']); self.assertTrue(kwargs['text'])
        self.assertEqual(kwargs['env']['GOTOOLCHAIN'], 'local')
        self.assertEqual(kwargs['env']['GOTELEMETRY'], 'off')
        self.assertEqual(kwargs['env']['PIP_NO_INDEX'], '1')
        if argv[1:] == ['version']:
            output='go version go1.26.9 darwin/arm64'
        elif argv[1:] == ['-m','briefcase','--version']:
            output='0.4.5'
        elif argv[1:] == ['-m','pip','--version']:
            output='pip 26.3 from fixture (python 3.12)'
        else:
            self.fail('Inspection attempted a non-version command: '+repr(argv))
        return NS(returncode=0,stdout=output,stderr='')

    def test_native_probe_versions_paths_and_no_download_environment(self):
        with patch.object(owner.shutil,'which',return_value=str(self.go)), \
                patch.object(owner.subprocess,'run',side_effect=self.version_command) as run:
            result=owner.inspect(sys.executable,'native',environment={'PATH':'fixture-path'})
        self.assertTrue(result['ready']); self.assertEqual(len(run.call_args_list),3)
        self.assertEqual({row['tool'] for row in result['tools']},{'briefcase','pip','go','langdetect-wheel'})
        self.assertTrue(all(row['executable'] and row['resolved_executable'] for row in result['tools'] if row['tool'] != 'langdetect-wheel'))

    def test_runtime_only_probes_pip_without_go_or_briefcase(self):
        with patch.object(owner.shutil,'which',side_effect=AssertionError('Unexpected Go requirement')), \
                patch.object(owner.subprocess,'run',side_effect=self.version_command) as run:
            result=owner.inspect(sys.executable,'runtime')
        self.assertTrue(result['ready']); self.assertEqual(len(run.call_args_list),1)
        self.assertEqual(run.call_args.args[0][1:],['-m','pip','--version'])
        plan=owner.with_prerequisites(self.fixture_plan(('ios-runtime',),effect='test'),'ios',sys.executable)
        gate=next(p for p in plan.phases if p.id=='native-prerequisites')
        self.assertEqual(gate.argv[gate.argv.index('--capability')+1],'runtime')

    def test_host_desktop_and_hosted_plans_are_unchanged(self):
        for target,ids,backend in [('ios',('portable-contracts',),'This Mac'),
                ('macos',('ios-build',),'This Mac'),('ios',('ios-build',),'GitHub')]:
            with self.subTest(target=target,ids=ids,backend=backend):
                plan=self.fixture_plan(ids,backend)
                self.assertIs(owner.with_prerequisites(plan,target,sys.executable),plan)

    def test_build_only_has_inspection_and_cleanup_dependency_is_unchanged(self):
        plan=self.fixture_plan()
        cleanup=Phase('cleanup',(sys.executable,'-c','pass'),str(ROOT),always=True,kind='cleanup',effect='inspect',dependencies=('ios-build',))
        plan=replace(plan,phases=(*plan.phases,cleanup))
        checked=owner.with_prerequisites(plan,'ios',sys.executable)
        require_build_only(checked)
        self.assertEqual(checked.phases[-1],cleanup)
        self.assertEqual(checked.phases[0].effect,'inspect')
        self.assertIn('native-prerequisites',checked.phases[1].dependencies)

    def test_real_normal_android_plan_missing_go_blocks_host_work_but_preserves_cleanup(self):
        from logistics_build.build_project import LogisticsProject
        binary=self.root/'bin';binary.mkdir()
        (binary/'briefcase.py').write_text('print("0.4.5")\n')
        (binary/'pip.py').write_text('print("pip 26.3 from fixture")\n')
        marker=self.root/'host-ran'; cleaned=self.root/'cleanup-ran'
        env=dict(PATH=str(binary),PYTHONPATH=os.pathsep.join((str(binary),str(ROOT/'Python'),str(ROOT))),PIP_FIND_LINKS=str(self.wheelhouse),PYTHONDONTWRITEBYTECODE='1')
        phases=(Phase('host-contracts',(sys.executable,'-c','from pathlib import Path;Path('+repr(str(marker))+').touch()'),str(ROOT),environment=env,effect='test'),
                Phase('android-native',(sys.executable,'-c','pass'),str(ROOT),environment=env,effect='test',dependencies=('host-contracts',),artifacts=(str(self.root/'native.json'),)),
                Phase('android-runtime',(sys.executable,'-c','pass'),str(ROOT),environment=env,effect='test',dependencies=('host-contracts',),artifacts=(str(self.root/'runtime.json'),)),
                Phase('cleanup',(sys.executable,'-c','from pathlib import Path;Path('+repr(str(cleaned))+').touch()'),str(ROOT),kind='cleanup',effect='inspect',always=True,dependencies=('android-native',)))
        base=Plan('Fixture','Read-only admission',{},phases,str(self.root/'workspace'),backend='This Mac — Android Emulator',effect='test')
        project=LogisticsProject(ROOT);project.private=self.root/'private'
        # This fixture executes in the current hosted test interpreter; an
        # operator's checkout-local .venv need not exist on a CI runner.
        project.interpreter=Path(sys.executable)
        with patch.object(project,'_make_plan',return_value=base), \
                patch('logistics_build.build_retention.clean',return_value=[]):
            plan=project.make_plan('Test','android','This Mac — Android Emulator')
        # Exercise the real normal plan's dependency graph and inspection CLI.
        # Every other command is harmless even if the gate regresses.
        safe=[]
        for phase in plan.phases:
            if phase.id in {'test-structure','native-prerequisites','cleanup'}:
                safe.append(phase)
            else:
                safe.append(replace(phase,argv=(sys.executable,'-c',
                    'from pathlib import Path;Path('+repr(str(marker))+').touch()'),
                    artifacts=(),artifact_types={},reuse_key='',reuse_probe=(),infrastructure_recovery={}))
        plan=replace(plan,phases=tuple(safe))
        gate=next(p for p in plan.phases if p.id=='native-prerequisites')
        self.assertEqual(gate.argv[gate.argv.index('--capability')+1],'native')
        report=Executor(resource_directory=self.root/'resources',evidence_directory=self.root/'evidence').run(plan,self.root/'run')
        self.assertEqual(report['status'],'failed',report.get('error'))
        self.assertFalse(marker.exists());self.assertTrue(cleaned.is_file())
        rows={row['id']:row for row in report['phases']}
        self.assertEqual(rows['native-prerequisites']['status'],'failed')
        self.assertEqual(rows['cleanup']['status'],'passed')
        result=json.loads(Path(next(p for p in plan.phases if p.id=='native-prerequisites').artifacts[0]).read_text())
        go=next(r for r in result['tools'] if r['tool']=='go')
        self.assertIn('Update project tooling',go['error']);self.assertIn('Go 1.26.9',go['error'])
        self.assertTrue(all(row['ready'] for row in result['tools'] if row['tool']!='go'),result)

    def test_normal_project_plan_places_gate_before_full_host_contracts(self):
        from logistics_build.build_project import LogisticsProject
        project=LogisticsProject(ROOT);project.private=self.root/'private'
        # This fixture executes in the current hosted test interpreter; an
        # operator's checkout-local .venv need not exist on a CI runner.
        project.interpreter=Path(sys.executable)
        native=self.fixture_plan(backend='This Mac — iOS Simulators',effect='test')
        with patch.object(project,'_make_plan',return_value=native), \
                patch('logistics_build.build_retention.clean',return_value=[]):
            plan=project.make_plan('Test','ios','This Mac — iOS Simulators')
        gate=next(p for p in plan.phases if p.id=='native-prerequisites')
        self.assertEqual(gate.dependencies,('test-structure',))
        hosts=[p for p in plan.phases if p.kind=='test' and p.id!='ios-build']
        self.assertTrue(hosts)
        self.assertTrue(all(gate.id in p.dependencies for p in hosts))
        self.assertIn(gate.id,next(p for p in plan.phases if p.id=='ios-build').dependencies)

    def test_wrong_version_timeout_and_oversize_are_not_ready(self):
        failures=[NS(returncode=0,stdout='pip 26.2 from fixture',stderr=''),
                  subprocess.TimeoutExpired('version',10),NS(returncode=0,stdout='x'*8193,stderr='')]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__),patch.object(owner.subprocess,'run',side_effect=failure if isinstance(failure,Exception) else None,return_value=failure):
                result=owner.inspect(sys.executable,'runtime')
                self.assertFalse(result['ready']);self.assertIn('dev.py setup mobile',result['tools'][0]['error'])
                self.assertLess(len(json.dumps(result)),8192)

    def test_each_native_tool_requires_its_exact_declared_version(self):
        wrong={'briefcase':'0.4.4','pip':'26.2','go':'1.26.8'}
        for tool,version in wrong.items():
            with self.subTest(tool=tool):
                def command(argv,**kwargs):
                    result=self.version_command(argv,**kwargs)
                    name='go' if argv[1:]==['version'] else argv[2]
                    if name==tool:
                        result.stdout=('go version go'+version+' darwin/arm64' if tool=='go'
                                       else 'pip '+version+' from fixture' if tool=='pip' else version)
                    return result
                with patch.object(owner.shutil,'which',return_value=str(self.go)), \
                        patch.object(owner.subprocess,'run',side_effect=command):
                    report=owner.inspect(sys.executable,'native')
                self.assertFalse(report['ready'])
                self.assertEqual(next(row for row in report['tools'] if row['tool']==tool)['version'],version)

    def test_python_environment_path_is_not_resolved_before_launch(self):
        python=self.root/'venv/bin/python';python.parent.mkdir(parents=True);python.touch()
        resolved=Path(sys.executable).resolve()
        with patch.object(Path,'resolve',return_value=resolved), \
                patch.object(owner.subprocess,'run',side_effect=self.version_command) as run:
            result=owner.inspect(python,'runtime')
        self.assertEqual(run.call_args.args[0][0],str(python))
        self.assertEqual(result['tools'][0]['resolved_executable'],str(resolved))

    def test_expected_versions_match_declared_host_and_ci_pins(self):
        requirements=(ROOT/'mobile_build/requirements-host.in').read_text()
        for name in ('briefcase','pip'):self.assertIn(name+'=='+owner.EXPECTED[name],requirements)
        self.assertIn("go-version: '"+owner.EXPECTED['go']+"'",(ROOT/'.github/workflows/mobile-build.yml').read_text())

    def test_missing_verified_wheel_blocks_real_executor_before_host_effect(self):
        binary=self.root/'tools';binary.mkdir()
        (binary/'briefcase.py').write_text('print("0.4.5")\n')
        (binary/'pip.py').write_text('print("pip 26.3 from fixture")\n')
        go=binary/('go.cmd' if os.name == 'nt' else 'go')
        go.write_text('@echo go version go1.26.9 fixture/fixture\n' if os.name == 'nt' else
                      '#!/bin/sh\necho "go version go1.26.9 fixture/fixture"\n')
        go.chmod(0o755)
        marker=self.root/'host-effect'
        env=dict(PATH=str(binary),PYTHONPATH=os.pathsep.join((str(binary),str(ROOT),str(ROOT/'Python'))),
                 PIP_FIND_LINKS=str(self.root/'missing-wheelhouse'),PYTHONDONTWRITEBYTECODE='1')
        host=Phase('host-contracts',(sys.executable,'-c','from pathlib import Path;Path('+repr(str(marker))+').touch()'),
                   str(ROOT),environment=env,effect='test')
        native=Phase('android-native',(sys.executable,'-c','pass'),str(ROOT),environment=env,effect='test',dependencies=(host.id,))
        plan=Plan('Fixture','Missing app wheel',{},(host,native),str(self.root/'workspace'),backend='This Mac',effect='test')
        plan=owner.with_prerequisites(plan,'android',sys.executable)
        result=Executor(resource_directory=self.root/'resources',evidence_directory=self.root/'evidence').run(plan,self.root/'run')
        self.assertEqual(result['status'],'failed')
        self.assertFalse(marker.exists())
        gate=next(p for p in plan.phases if p.id=='native-prerequisites')
        proof=json.loads(Path(gate.artifacts[0]).read_text())
        self.assertTrue(all(row['ready'] for row in proof['tools'] if row['tool']!='langdetect-wheel'))
        self.assertFalse(next(row for row in proof['tools'] if row['tool']=='langdetect-wheel')['ready'])
