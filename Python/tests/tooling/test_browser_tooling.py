"""Release browser readiness is explicit, portable and part of plan identity."""
import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
from commonUtils.testing.stages import TestStage
from build_manager import Phase,Plan
from logistics_build import browser_tooling as browser
from logistics_build.manager_suites import with_host_gates
from mobile_build.deployment import manager_settings

TEST_STAGE=TestStage.REGRESSION


class BrowserToolingTests(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.node=self.root/'runtime with spaces/node.exe';self.node.parent.mkdir();self.node.touch()
        self.modules=self.root/'node modules';(self.modules/'playwright').mkdir(parents=True)
        (self.modules/'playwright/package.json').write_text('{}')
        self.chrome=self.root/'existing chromium';self.chrome.touch()
        self.values={'tools.node':str(self.node),'tools.node_modules':str(self.modules),'tools.chrome':str(self.chrome)}
        self.result=NS(returncode=0,stdout=json.dumps({'node':'24.0.0','browser':str(self.chrome)}),stderr='')

    def test_explicit_browser_is_frozen_without_probe_or_path_splitting(self):
        with patch.object(browser.subprocess,'run') as run:
            selected=browser.environment(self.values,inherited={'PATH':'original'})
        self.assertEqual(selected['LOGISTICS_CHROME'],str(self.chrome));run.assert_not_called()
        self.assertEqual(selected['PATH'],str(self.node.parent)+os.pathsep+'original')
        self.assertEqual(selected['NODE_PATH'],str(self.modules))

    def test_playwright_owned_browser_is_resolved_and_frozen_before_cache_isolation(self):
        values=dict(self.values,**{'tools.chrome':''})
        with patch.object(browser.subprocess,'run',return_value=self.result) as run:
            selected=browser.environment(values,inherited={'PATH':'original','PLAYWRIGHT_BROWSERS_PATH':'explicit-cache'})
        self.assertEqual(selected['LOGISTICS_CHROME'],str(self.chrome))
        self.assertEqual(selected['PLAYWRIGHT_BROWSERS_PATH'],'explicit-cache')
        self.assertEqual(run.call_args.args[0],[str(self.node),'-e',browser.PROBE])
        self.assertEqual(run.call_args.kwargs['timeout'],10)
        self.assertNotIn('shell',run.call_args.kwargs)

    def test_relative_tool_paths_are_frozen_before_snapshot_working_directory(self):
        with patch.object(browser.shutil,'which',return_value=None):
            selected=browser.environment({'tools.node':'runtime/node','tools.node_modules':'modules','tools.chrome':'browser'},inherited={})
        self.assertEqual(selected['LOGISTICS_NODE'],str(Path('runtime/node').absolute()))
        self.assertEqual(selected['NODE_PATH'],str(Path('modules').absolute()))
        self.assertEqual(selected['LOGISTICS_CHROME'],str(Path('browser').absolute()))

    def test_missing_tools_block_release_with_actionable_message_without_install(self):
        for name in ('LOGISTICS_NODE','NODE_PATH','LOGISTICS_CHROME'):
            selected={'LOGISTICS_NODE':str(self.node),'NODE_PATH':str(self.modules),'LOGISTICS_CHROME':str(self.chrome)}
            selected[name]=str(self.root/'missing')
            with patch.object(browser.subprocess,'run') as run:
                value=browser.inspect(selected=selected)
            self.assertFalse(value['ready']);self.assertIn('project settings',value['message']);self.assertIn('never downloads',value['message']);run.assert_not_called()

    def test_bad_node_or_playwright_is_blocked_without_raw_subprocess_output(self):
        selected=browser.environment(self.values,inherited={})
        with patch.object(browser.subprocess,'run',return_value=NS(returncode=1,stdout='',stderr='secret internal output')):
            value=browser.inspect(selected=selected)
        self.assertFalse(value['ready']);self.assertNotIn('secret',json.dumps(value))

    def test_existing_node_on_path_works_without_personal_paths(self):
        with patch.object(browser.shutil,'which',return_value=str(self.node)):
            selected=browser.environment(dict(self.values,**{'tools.node':''}),inherited={'PATH':'system'})
        self.assertEqual(selected['LOGISTICS_NODE'],str(self.node))

    def test_ready_probe_uses_metadata_only(self):
        with patch.object(browser.subprocess,'run',return_value=self.result):
            value=browser.inspect(selected=browser.environment(self.values,inherited={}))
        self.assertTrue(value['ready']);self.assertIn('runtime is tested',value['scope'])
        self.assertNotIn('launch(',browser.PROBE);self.assertNotIn('install',browser.PROBE)

    def test_release_gate_precedes_host_and_native_work_with_cleanup_unchanged(self):
        selected=browser.environment(self.values,inherited={})
        source=Phase('android-build',('python',),str(self.root),environment=selected)
        cleanup=Phase('android-cleanup',('python',),str(self.root),kind='cleanup',always=True)
        plan=Plan('Logistics','Test',{'revision':'source'},(source,cleanup),str(self.root),backend='This Mac')
        hosts=(Phase('mobile-host',('python','test'),str(self.root),environment=selected),)
        with patch('build_manager.test_manifest.phases',return_value=hosts):
            result=with_host_gates(plan,'desktop-python',release=True)
        rows={p.id:p for p in result.phases}
        gate=rows['mobile-browser-prerequisites']
        self.assertEqual(gate.effect,'inspect');self.assertEqual(gate.environment,selected)
        self.assertIn(gate.id,rows['mobile-host'].dependencies)
        self.assertIn('mobile-host',rows['android-build'].dependencies)
        self.assertEqual(rows['android-cleanup'],cleanup)
        # Ordinary developer plans do not opt into with_host_gates.
        self.assertNotIn(gate.id,[p.id for p in plan.phases])
        with patch('build_manager.test_manifest.phases',return_value=hosts):
            ordinary=with_host_gates(plan,'desktop-python')
        self.assertNotIn(gate.id,[p.id for p in ordinary.phases])

    def test_selected_browser_path_changes_retained_plan_identity(self):
        first=browser.environment(self.values,inherited={})
        second=browser.environment(dict(self.values,**{'tools.chrome':str(self.root/'different-browser')}),inherited={})
        def plan(environment):return Plan('Logistics','Test',{},(Phase('host',('python',),str(self.root),environment=environment),),str(self.root),backend='This Mac')
        self.assertNotEqual(plan(first).identity,plan(second).identity)

    def test_existing_environment_names_resolve_through_settings_owner(self):
        self.assertEqual({k:manager_settings.VARIABLES[k] for k in self.values},
            {'tools.node':'LOGISTICS_NODE','tools.node_modules':'NODE_PATH','tools.chrome':'LOGISTICS_CHROME'})

    def test_gui_paths_roundtrip_privately_with_explicit_help_and_file_kinds(self):
        from Python.tests.tooling.test_manager_settings import ManagerSettingsTests
        from logistics_build.build_project import LogisticsProject
        values=dict(self.values)
        ManagerSettingsTests.setUp(self)
        profile=self.root/'private-profile.json'
        with patch.dict(os.environ,{'LOGISTICS_MANAGER_PROFILE':str(profile),
                'LOGISTICS_MANAGER_ACCOUNT_DEFAULTS':'{}'}):
            for key in ('LOGISTICS_NODE','NODE_PATH','LOGISTICS_CHROME'):
                os.environ.pop(key,None)
            manager_settings.save(self.root,values)
            configured,_=manager_settings.settings(self.root)
            self.assertEqual({k:configured[k] for k in values},values)
            project=LogisticsProject(self.root.parent);project.mobile=self.root
            rows=project.settings_view()
        self.assertEqual(rows['tools.node']['kind'],'reference')
        self.assertEqual(rows['tools.chrome']['kind'],'reference')
        self.assertEqual(rows['tools.node_modules']['kind'],'directory')
        self.assertIn('no browser is downloaded',rows['tools.chrome']['description'])

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the actual CommonJS resolution regression')
    def test_actual_fixture_resolution_rejects_nearer_shadowed_playwright(self):
        node=shutil.which('node')
        package=self.modules/'playwright'
        (package/'package.json').write_text('{"main":"index.js"}')
        (package/'index.js').write_text("module.exports={chromium:{executablePath:()=>'/synthetic/browser'}}")
        fixture=self.root/'project/mobile_build/tests/chat';fixture.mkdir(parents=True)
        selected=dict(os.environ,NODE_PATH=str(self.modules),LOGISTICS_BROWSER_FIXTURE_DIRS=json.dumps([str(fixture)]))
        self.assertEqual(browser.probe(node,selected)['browser'],'/synthetic/browser')
        shadow=fixture.parent/'node_modules/playwright';shadow.mkdir(parents=True)
        (shadow/'package.json').write_text('{"main":"index.js"}')
        (shadow/'index.js').write_text("module.exports={chromium:{executablePath:()=>'/different/browser'}}")
        with self.assertRaises(ValueError):browser.probe(node,selected)
