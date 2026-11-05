"""Retain tested APK bytes before a later recipe cleans its Gradle output.

Pure plan/SDK artifact transport proof; this does not build or validate an app.
"""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.testing.stages import TestStage
from build_manager import Phase
from build_manager.executor import Executor
from logistics_build.build_project import LogisticsProject

TEST_STAGE=TestStage.REGRESSION
ROOT=Path(__file__).resolve().parents[3]


class AndroidApkRetentionTests(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.snapshot=self.root/'source';self.snapshot.mkdir()
        (self.snapshot/'test-environments.json').write_bytes((ROOT/'test-environments.json').read_bytes())
        java=self.root/'java/bin/java';java.parent.mkdir(parents=True);java.touch()
        self.project=LogisticsProject(ROOT)
        options={'android.avd':'','tools.android_sdk':str(self.root/'sdk'),'tools.java':str(java.parent.parent),
                 'tools.mobile_python':sys.executable,'tools.xcode':''}
        with patch('build_manager.hosts.android_abi',return_value='arm64-v8a'), \
                patch.object(self.project,'backend_options',return_value=('This Mac — Android Emulator',)):
            self.plan=self.project.android_emulator_plan('Build',{},self.snapshot,self.root/'workspace',options,{},None)
        self.build=self.plan.phases[0]

    def test_original_json_stays_artifact_zero_and_exact_debug_apk_is_second(self):
        self.assertEqual(len(self.build.artifacts),2)
        self.assertEqual(self.build.artifacts[0],self.build.argv[self.build.argv.index('--result')+1])
        self.assertEqual(Path(self.build.artifacts[1]),self.snapshot/'mobile_build/build/logisticsmobile/android/gradle/app/build/outputs/apk/debug/app-debug.apk')

    def test_real_executor_copies_exact_apk_before_later_recipe_unlinks_original(self):
        apk=self.snapshot/'mobile_build/build/logisticsmobile/android/gradle/app/build/outputs/apk/debug/app-debug.apk'
        report=Path(self.build.artifacts[0])
        payload=b'unit-only synthetic APK artifact transport bytes\x00\xff'
        command='from pathlib import Path;import json,hashlib;'
        command+='apk=Path('+repr(str(apk))+');apk.parent.mkdir(parents=True,exist_ok=True);'
        command+='data='+repr(payload)+';apk.write_bytes(data);'
        command+='report=Path('+repr(str(report))+');report.parent.mkdir(parents=True,exist_ok=True);'
        command+='report.write_text(json.dumps({"apk":str(apk),"apk_sha256":hashlib.sha256(data).hexdigest()}))'
        build=replace(self.build,argv=(sys.executable,'-c',command))
        clean=Phase('recipe-clean',(sys.executable,'-c','from pathlib import Path;Path('+repr(str(apk))+').unlink()'),
                    str(self.snapshot),dependencies=(build.id,),kind='setup',effect='inspect')
        plan=replace(self.plan,phases=(build,clean))
        result=Executor(resource_directory=self.root/'resources',evidence_directory=self.root/'evidence').run(plan,self.root/'run')
        self.assertEqual(result['status'],'passed',result.get('error'))
        self.assertFalse(apk.exists())
        records=next(row for row in result['phases'] if row['id']==build.id)['artifacts']
        self.assertEqual(len(records),2)
        self.assertEqual(records[1]['original_path'],str(apk.resolve()))
        self.assertEqual(Path(records[1]['path']).read_bytes(),payload)
        self.assertEqual(records[1]['sha256'],sha256(payload).hexdigest())
        self.assertEqual(json.loads(Path(records[0]['path']).read_text())['apk_sha256'],records[1]['sha256'])
