"""Exact review and interrupted-attempt guards; no provider request is sent."""
import hashlib
import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from logistics_build.distribute_prepared import reviewed,distribute
from build_manager.providers import ProviderOutcomeUnknown
from mobile_build.deployment import firebase_deploy


class PreparedDistributionTests(unittest.TestCase):
    def firebase_fixture(self, root):
        apk=root/'app.apk';apk.write_bytes(b'synthetic artifact')
        (root/'.tools').mkdir();(root/'.tools/firebase').touch()
        destination=dict(app_id='other-app',group='testers',bundle_id=firebase_deploy.android.BUNDLE)
        data=dict(provider='Firebase',apk=str(apk),apk_sha256=hashlib.sha256(apk.read_bytes()).hexdigest(),destination=destination)
        report=root/'prepared.json';report.write_text(json.dumps(data))
        approval=[dict(original_path=str(report.resolve()),sha256=hashlib.sha256(report.read_bytes()).hexdigest())]
        env=dict(BUILD_MANAGER_APPROVED_PLAN='fixture-plan',BUILD_MANAGER_APPROVED_ARTIFACTS=json.dumps(approval))
        return report,destination,env

    def test_firebase_attempt_precedes_upload_and_keeps_provider_receipt(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);report,destination,env=self.firebase_fixture(root)
            receipt=root/'receipt.json';attempt=receipt.with_suffix('.attempt.json')
            def run(command, **kwargs):
                self.assertTrue(attempt.is_file())
                self.assertEqual(command,[str(root/'.tools/firebase'),'appdistribution:distribute',str(root/'app.apk'),
                    '--app','other-app','--groups','testers','--release-notes-file',str(root/'release-notes.txt'),
                    '--non-interactive','--json'])
                self.assertEqual(kwargs['cwd'],root/'.tools')
                return subprocess.CompletedProcess(command,0,'{"result":{"release":"verified-id"}}')
            with patch.dict(os.environ,env),patch.object(firebase_deploy,'ROOT',root), \
                    patch.object(firebase_deploy,'preflight',return_value=(destination,'testers')), \
                    patch('build_manager.firebase.subprocess.run',side_effect=run) as upload:
                result=distribute(report,receipt)
            self.assertEqual(upload.call_count,1)
            self.assertEqual(result['remote'],{'release':'verified-id'})
            self.assertEqual(json.loads(receipt.read_text())['status'],'completed')

    def test_ambiguous_firebase_upload_preserves_attempt_and_cannot_replay(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);report,destination,env=self.firebase_fixture(root)
            receipt=root/'receipt.json'
            with patch.dict(os.environ,env),patch.object(firebase_deploy,'ROOT',root), \
                    patch.object(firebase_deploy,'preflight',return_value=(destination,'testers')), \
                    patch('build_manager.firebase.subprocess.run',return_value=subprocess.CompletedProcess([],0,'{"result":{}}')) as upload:
                with self.assertRaises(ProviderOutcomeUnknown):distribute(report,receipt)
                self.assertFalse(receipt.exists())
                self.assertTrue(receipt.with_suffix('.attempt.json').exists())
                with self.assertRaisesRegex(ValueError,'Reconcile'):distribute(report,receipt)
                self.assertEqual(upload.call_count,1)

    def test_changed_firebase_destination_stops_before_attempt_or_upload(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);report,destination,env=self.firebase_fixture(root)
            receipt=root/'receipt.json'
            with patch.dict(os.environ,env),patch.object(firebase_deploy,'ROOT',root), \
                    patch.object(firebase_deploy,'preflight',return_value=(dict(destination,group='changed'),'changed')), \
                    patch('build_manager.firebase.subprocess.run') as upload:
                with self.assertRaisesRegex(ValueError,'destination changed'):distribute(report,receipt)
            upload.assert_not_called()
            self.assertFalse(receipt.with_suffix('.attempt.json').exists())

    def test_unreviewed_report_never_executes_provider(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'report.json';path.write_text('{}')
            with patch.dict(os.environ,{},clear=True),patch('logistics_build.distribute_prepared.subprocess.run') as run:
                with self.assertRaisesRegex(ValueError,'review'):distribute(path,Path(directory)/'receipt.json')
            run.assert_not_called()

    def test_testflight_keeps_verified_group_receipt_and_streams_progress(self):
        for group in ('Friends', 'unexpected'):
            with self.subTest(group=group), TemporaryDirectory() as directory:
                root=Path(directory);report=root/'prepared.json';receipt=root/'receipt.json'
                build=dict(version='0.1.16',build_number='7')
                data=dict(provider='TestFlight',workspace=str(root),release=dict(build=build),
                          destination=dict(app_id='app-1',external_group='Friends'))
                report.write_text(json.dumps(data))
                approval=[dict(original_path=str(report.resolve()),sha256=hashlib.sha256(report.read_bytes()).hexdigest())]
                env=dict(BUILD_MANAGER_APPROVED_PLAN='reviewed-plan',BUILD_MANAGER_APPROVED_ARTIFACTS=json.dumps(approval))
                def upload(command, **kwargs):
                    self.assertTrue(kwargs['check'])
                    self.assertNotIn('capture_output',kwargs)
                    (root/'upload-result.json').write_text(json.dumps(dict(status='uploaded',build=build)))
                    (root/'external-distribution.json').write_text(json.dumps(dict(
                        app_id='app-1',group_name=group,group_id='group-1',build_id='build-7',
                        version='0.1.16',build_number='7',status='assigned',external_state='WAITING_FOR_BETA_REVIEW')))
                with patch.dict(os.environ,env),patch('logistics_build.distribute_prepared.subprocess.run',side_effect=upload) as run:
                    if group=='Friends':
                        result=distribute(report,receipt)
                        self.assertEqual(result['remote']['external_distribution']['build_id'],'build-7')
                        self.assertEqual(result['remote']['external_distribution']['external_state'],'WAITING_FOR_BETA_REVIEW')
                        self.assertEqual(json.loads(receipt.read_text())['status'],'completed')
                    else:
                        with self.assertRaisesRegex(ValueError,'assignment is unverified'):distribute(report,receipt)
                        self.assertFalse(receipt.exists())
                    with self.assertRaisesRegex(ValueError,'Reconcile'):distribute(report,receipt)
                    self.assertEqual(run.call_count,1)

    def test_interrupted_attempt_is_not_blindly_repeated(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);report=root/'prepared.json';receipt=root/'receipt.json'
            data=dict(provider='TestFlight',workspace=str(root),release=dict(source=dict(dirty=True),build=dict(build_number='7')),destination={'group':'synthetic'})
            report.write_text(json.dumps(data))
            approval=[dict(original_path=str(report.resolve()),sha256=hashlib.sha256(report.read_bytes()).hexdigest())]
            env=dict(BUILD_MANAGER_APPROVED_PLAN='synthetic-plan',BUILD_MANAGER_APPROVED_ARTIFACTS=json.dumps(approval))
            with patch.dict(os.environ,env),patch('logistics_build.distribute_prepared.subprocess.run',side_effect=ConnectionError('synthetic lost supervision')) as run:
                with self.assertRaises(ConnectionError):distribute(report,receipt)
                with self.assertRaisesRegex(ValueError,'Reconcile'):distribute(report,receipt)
                self.assertEqual(run.call_count,1)
            self.assertEqual(json.loads(receipt.with_suffix('.attempt.json').read_text())['status'],'unknown until reconciled')
