"""Retain tested APK bytes before a later recipe cleans its Gradle output.

Pure plan/SDK artifact transport proof; this does not build or validate an app.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.testing.stages import TestStage
from build_manager import Phase, Plan
from build_manager.executor import Executor
from logistics_build.build_project import LogisticsProject
from logistics_build import android_backend, test_apk_storage
from build_manager.workflows import verify_artifacts

TEST_STAGE=TestStage.REGRESSION
ROOT=Path(__file__).resolve().parents[3]


class AndroidApkStorageTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'darwin', 'macOS copy-on-write')
    def test_completed_run_keeps_both_paths_and_protects_reviewable_runs(self):
        from build_manager.retention import durable_hold

        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for folder in test_apk_storage.APK_ROOTS:
                (root / folder).mkdir(parents=True, exist_ok=True)
            source = root / 'tmp/test-results' / ('emulator-' + 'a' * 32) / 'validated-test.apk'
            run = root / 'tmp/test-results/build-manager/finished'
            target = run / 'artifacts/android-build-0.apk'
            for path in (source, target):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'original test package')
            digest = sha256(source.read_bytes()).hexdigest()
            phase = Phase('android-build', ('python',), str(root), artifacts=(str(source),))
            plan = Plan('Logistics', 'Test', {}, (phase,), str(root))
            plan.save(run / 'plan.json')
            report = dict(schema=1, status='awaiting_review', plan_identity=plan.identity,
                          phases=[dict(id=phase.id, status='passed', artifacts=[
                              dict(path=str(target), original_path=str(source), sha256=digest)])])
            receipt = run / 'result.json'
            receipt.write_text(json.dumps(report))
            self.assertEqual(test_apk_storage.coalesce_test_apks(root, apply=True), [])
            report['status'] = 'passed'
            receipt.write_text(json.dumps(report))
            durable_hold(run, 'review')
            self.assertEqual(test_apk_storage.coalesce_test_apks(root, apply=True), [])
            durable_hold(run, 'review', release=True)
            expected = [dict(path=str(target), bytes=target.stat().st_size)]
            self.assertEqual(test_apk_storage.coalesce_test_apks(root), expected)
            target.write_bytes(b'changed')
            self.assertEqual(test_apk_storage.coalesce_test_apks(root, apply=True), [])
            target.write_bytes(source.read_bytes())
            self.assertEqual(test_apk_storage.coalesce_test_apks(root, apply=True), expected)
            self.assertEqual(test_apk_storage.coalesce_test_apks(root), [])
            source.write_bytes(b'rebuilt')
            self.assertEqual(target.read_bytes(), b'original test package')
            self.assertEqual(json.loads(receipt.read_text()), report)


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
        self.assertEqual(Path(self.build.artifacts[1]),Path(self.build.artifacts[0]).parent/'validated-test.apk')

    def test_real_executor_copies_exact_apk_before_later_recipe_unlinks_original(self):
        apk=self.snapshot/'mobile_build/build/logisticsmobile/android/gradle/app/build/outputs/apk/debug/app-debug.apk'
        report=Path(self.build.artifacts[0])
        payload=b'unit-only synthetic APK artifact transport bytes\x00\xff'
        retained=Path(self.build.artifacts[1])
        command='from pathlib import Path;import json,hashlib,importlib.util;'
        command+='spec=importlib.util.spec_from_file_location("apk_backend",'+repr(android_backend.__file__)+');owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner);'
        command+='apk=Path('+repr(str(apk))+');apk.parent.mkdir(parents=True,exist_ok=True);'
        command+='data='+repr(payload)+';apk.write_bytes(data);'
        command+='report=Path('+repr(str(report))+');report.parent.mkdir(parents=True,exist_ok=True);'
        command+='retained=owner.retain_test_apk(apk,Path('+repr(str(retained))+'),hashlib.sha256(data).hexdigest());'
        command+='report.write_text(json.dumps({"apk":str(retained),"apk_sha256":hashlib.sha256(data).hexdigest()}));'
        command+='owner.verify_test_apk(Path('+repr(str(self.snapshot))+'),json.loads(report.read_text()))'
        build=replace(self.build,argv=(sys.executable,'-c',command), environment=dict(self.build.environment,
            PYTHONPATH=os.pathsep.join((str(ROOT),str(ROOT/'Python')))))
        clean=Phase('recipe-clean',(sys.executable,'-c','from pathlib import Path;Path('+repr(str(apk))+').unlink()'),
                    str(self.snapshot),dependencies=(build.id,),kind='setup',effect='inspect')
        plan=replace(self.plan,phases=(build,clean))
        result=Executor(resource_directory=self.root/'resources',evidence_directory=self.root/'evidence').run(plan,self.root/'run')
        self.assertEqual(result['status'],'passed',[(row['id'],row['status'],row.get('error'), (self.root/'run'/row['log']).read_text() if row.get('log') and (self.root/'run'/row['log']).exists() else '') for row in result['phases']])
        self.assertFalse(apk.exists())
        records=next(row for row in result['phases'] if row['id']==build.id)['artifacts']
        self.assertEqual(len(records),2)
        self.assertEqual(records[1]['original_path'],str(retained.resolve()))
        verify_artifacts(dict(artifacts=records))  # The upload review verifies BOTH original and copied bytes.
        self.assertEqual(Path(records[1]['path']).read_bytes(),payload)
        self.assertEqual(records[1]['sha256'],sha256(payload).hexdigest())
        self.assertEqual(json.loads(Path(records[0]['path']).read_text())['apk_sha256'],records[1]['sha256'])

    def test_native_consumption_rejects_replaced_debug_bytes(self):
        apk=self.snapshot/'mobile_build/build/logisticsmobile/android/gradle/app/build/outputs/apk/debug/app-debug.apk'
        apk.parent.mkdir(parents=True);apk.write_bytes(b'validated native test bytes')
        digest=sha256(apk.read_bytes()).hexdigest()
        retained=android_backend.retain_test_apk(apk,Path(self.build.artifacts[1]),digest)
        report=dict(apk=str(retained),apk_sha256=digest)
        self.assertEqual(android_backend.verify_test_apk(self.snapshot,report),digest)
        apk.write_bytes(b'different package')
        with self.assertRaisesRegex(ValueError,'differs from retained'):
            android_backend.verify_test_apk(self.snapshot,report)
        self.assertEqual(retained.read_bytes(),b'validated native test bytes')

    def test_failed_copy_verification_does_not_publish_partial_or_replace_retained_bytes(self):
        apk=self.root/'source.apk';apk.write_bytes(b'new bytes')
        retained=self.root/'retained.apk'
        digest=sha256(apk.read_bytes()).hexdigest()
        with patch.object(android_backend,'checksum',return_value='mismatch'), \
                self.assertRaisesRegex(ValueError,'changed while retaining'):
            android_backend.retain_test_apk(apk,retained,digest)
        self.assertFalse(retained.exists())
        self.assertEqual(list(self.root.glob('.test-apk-*')),[])
        retained.write_bytes(b'previous proof')
        with self.assertRaisesRegex(ValueError,'differs from this build'):
            android_backend.retain_test_apk(apk,retained,digest)
        self.assertEqual(retained.read_bytes(),b'previous proof')

    def test_native_entry_consumes_exact_bytes_and_records_proof_after_success(self):
        apk=self.snapshot/'mobile_build/build/logisticsmobile/android/gradle/app/build/outputs/apk/debug/app-debug.apk'
        apk.parent.mkdir(parents=True);apk.write_bytes(b'exact native bytes')
        retained=Path(self.build.artifacts[1]);digest=sha256(apk.read_bytes()).hexdigest()
        android_backend.retain_test_apk(apk,retained,digest)
        result=retained.parent/'native.json'
        (result.parent/'build.json').write_text(json.dumps(dict(apk=str(retained),apk_sha256=digest)))
        marker=result.parent/'emulator.json';marker.write_text(json.dumps(dict(serial='owned-fixture')))
        def consume(*args,**kwargs):
            self.assertEqual(apk.read_bytes(),retained.read_bytes())
            self.assertTrue(kwargs['no_update'])
            (kwargs['logs'] / 'android-native-ui.log').write_text('owned native attempt')
            return dict(status='passed')
        argv=['android_backend','native','--root',str(self.snapshot),'--workspace',str(result.parent/'device'),'--result',str(result)]
        with patch.object(android_backend,'AndroidEmulator') as emulator, \
                patch.object(android_backend.signal,'signal'),patch.object(android_backend.os,'chdir'), \
                patch.dict(os.environ,{'ANDROID_HOME':str(self.root/'sdk')}),patch.object(sys,'argv',argv), \
                patch('mobile_build.validation.ui_tools.run',side_effect=consume) as run:
            emulator.return_value.marker=marker
            android_backend.main()
            run.assert_called_once()
            passed = json.loads(result.read_text())
            run.side_effect = RuntimeError('controlled native failure')
            with self.assertRaisesRegex(RuntimeError, 'controlled native failure'):
                android_backend.main()
        self.assertEqual(passed['tested_apk_sha256'],digest)
        original = Path(passed['diagnostics'])
        failed = json.loads(result.read_text())
        self.assertEqual(failed['status'], 'failed')
        self.assertNotEqual(Path(failed['diagnostics']), original)
        self.assertEqual((original / 'android-native-ui.log').read_text(), 'owned native attempt')
        self.assertFalse((self.snapshot / 'mobile_build/logs').exists())
