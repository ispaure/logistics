"""Native/preparation planners retain the browser-selected PATH ahead of ambient."""
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock,patch
from commonUtils.testing.stages import TestStage
from logistics_build.browser_tooling import environment as browser_environment
from logistics_build.build_project import LogisticsProject
from logistics_build.test_environments import runtime_id

TEST_STAGE=TestStage.REGRESSION
ROOT=Path(__file__).resolve().parents[3]


class NativeNodePathTests(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name).resolve()
        self.snapshot=self.root/'source';self.snapshot.mkdir();(self.snapshot/'mobile_build').mkdir()
        self.settings=json.loads((ROOT/'test-environments.json').read_text())
        (self.snapshot/'test-environments.json').write_text(json.dumps(self.settings))
        self.project=LogisticsProject(ROOT);self.project.mobile=self.root/'owned-mobile';self.project.private=self.root/'private'
        self.node=self.root/'selected-node/bin'/('node.exe' if os.name=='nt' else 'node')
        self.go=self.project.mobile/'.tools/go/bin'/('go.exe' if os.name=='nt' else 'go')
        for path in (self.node,self.go):path.parent.mkdir(parents=True,exist_ok=True);path.touch();path.chmod(0o700)
        self.ambient=self.root/'ambient-empty';self.ambient.mkdir()
        java=self.root/'java/bin/java';java.parent.mkdir(parents=True);java.touch()
        self.options={'tools.mobile_python':sys.executable,'tools.xcode':'','tools.android_sdk':str(self.root/'sdk'),
                      'tools.java':str(java.parent.parent),'android.avd':'','ios.iphone':'','ios.duo':'','ios.ipad':''}
        self.selected=browser_environment({'tools.node':str(self.node),'tools.node_modules':str(self.root/'modules'),
            'tools.chrome':str(self.root/'existing-browser')},inherited={'PATH':str(self.ambient)},root=self.snapshot)

    def assert_executable(self,found,expected):
        self.assertIsNotNone(found)
        self.assertTrue(Path(found).samefile(expected),(found,str(expected)))

    def assert_tools(self,plan):
        self.assertIsNone(shutil.which('node',path=str(self.ambient)))
        for phase in plan.phases:
            with self.subTest(phase=phase.id):
                selected=phase.environment
                for name,expected in (('node',self.node),('go',self.go)):
                    found=shutil.which(name,path=selected['PATH'])
                    self.assert_executable(found,expected)
                self.assertEqual(selected['LOGISTICS_NODE'],str(self.node))
                self.assertEqual(selected['PATH'].split(os.pathsep)[:2],[str(self.go.parent),str(self.node.parent)])


    def test_case_alias_selects_same_executable_but_other_binary_is_rejected(self):
        # Windows which() can return PATHEXT spelling (.EXE) for an existing
        # .exe. File identity is the contract, including on case-sensitive hosts.
        aliases={}
        for name,expected in (('node',self.node),('go',self.go)):
            alias=expected.with_name(expected.name.upper())
            if not alias.exists(): os.link(expected,alias)
            self.assertTrue(alias.samefile(expected))
            aliases[name]=str(alias)
        plan=Mock(phases=[Mock(id='owned',environment=dict(self.selected))])
        plan.phases[0].environment['PATH']=os.pathsep.join((str(self.go.parent),str(self.node.parent),str(self.ambient)))
        def resolve(name,*,path):
            return None if path==str(self.ambient) else aliases[name]
        with patch.object(shutil,'which',side_effect=resolve): self.assert_tools(plan)
        for name,expected in (('node',self.node),('go',self.go)):
            other=self.root/('unselected-'+name)/expected.name
            other.parent.mkdir();other.touch()
            with self.subTest(unselected=name),self.assertRaises(AssertionError):
                self.assert_executable(str(other),expected)

    def test_actual_android_planning_preserves_node_and_adds_go_without_ambient_node(self):
        with patch.dict(os.environ,PATH=str(self.ambient)),patch('build_manager.hosts.android_abi',return_value='arm64-v8a'),patch.object(self.project,'backend_options',return_value=('This Mac',)):
            plan=self.project.android_emulator_plan('Build',{},self.snapshot,self.root/'android',self.options,dict(self.selected),None)
        self.assert_tools(plan)

    def test_actual_ios_simulator_planning_preserves_node_and_adds_go(self):
        runtime=runtime_id(self.settings,'iphone');device={'udid':'fixture','name':'Fixture','isAvailable':True,'deviceTypeIdentifier':'fixture-model'}
        client=Mock();client.devices.return_value={'devices':{runtime:[device]}};client.toolchain.return_value={}
        with patch.dict(os.environ,PATH=str(self.ambient)),patch('logistics_build.build_project.sys.platform','darwin'), \
                patch('build_manager.apple_simulators.AppleSimulators',return_value=client), \
                patch('mobile_build.validation.ui_tools.select_ios_device',return_value='fixture'), \
                patch('logistics_build.build_project.subprocess.check_output',return_value=self.settings['ios_sdk']+'\n'):
            plan=self.project.ios_simulator_plan({},self.snapshot,self.root/'ios',self.options,dict(self.selected),None,False,runtime_only=True)
        self.assert_tools(plan)

    def test_actual_ios_development_build_planning_preserves_node_and_adds_go(self):
        with patch.dict(os.environ,PATH=str(self.ambient)),patch('logistics_build.build_project.sys.platform','darwin'):
            plan=self.project.mobile_plan('Build','ios',{},self.snapshot,self.root/'ios-build',self.options,dict(self.selected),None,None,False)
        self.assert_tools(plan)

    def test_actual_both_provider_preparation_plans_preserve_node_and_go(self):
        with patch.dict(os.environ,PATH=str(self.ambient)):
            for target,operation in (('ios','Prepare TestFlight'),('android','Prepare Firebase')):
                plan=self.project.mobile_plan(operation,target,{},self.snapshot,self.root/target,self.options,dict(self.selected),None,None,False)
                self.assert_tools(plan)

    def test_missing_incoming_path_keeps_existing_ambient_fallback(self):
        with patch.dict(os.environ,PATH=str(self.ambient)),patch('logistics_build.build_project.sys.platform','darwin'):
            plan=self.project.mobile_plan('Build','ios',{},self.snapshot,self.root/'ios-build',self.options,{},None,None,False)
        self.assertEqual(plan.phases[0].environment['PATH'],str(self.go.parent)+os.pathsep+str(self.ambient))
