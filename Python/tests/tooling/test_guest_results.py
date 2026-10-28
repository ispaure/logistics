"""Collect evidence before conditional cleanup on either guest backend."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from logistics_build.guest_results import GuestResultLifecycle


class GuestResultTests(unittest.TestCase):
    def test_interrupted_wrapper_retains_ownership_before_guest_work(self):
        with TemporaryDirectory() as folder:
            result = dict(source={'commit': 'fixed'}, status='running', vm='owned-vm',
                          workspace='/var/tmp/owned-token', workspace_token='owned-token',
                          operation='exact-worker')
            GuestResultLifecycle(result, folder, 'fixture', 'guest_workspace')
            # Simulate abrupt wrapper termination: neither collect nor finish runs.
            saved = json.loads((Path(folder) / 'result.json').read_text())
            self.assertEqual(saved, result)
            self.assertEqual(saved['status'], 'running')
            self.assertNotIn('guest_workspace_removed', saved)

    def test_collection_failure_preserves_remote_workspace(self):
        with TemporaryDirectory() as folder:
            result = dict(source={'commit': 'fixed'}, status='passed')
            lifecycle = GuestResultLifecycle(result, folder, 'fixture', 'guest_workspace')
            cleanup = Mock()
            lifecycle.collect(Mock(side_effect=OSError('transfer lost')), Path(folder) / 'missing', cleanup)
            cleanup.assert_not_called()
            self.assertEqual(result['status'], 'failed')
            self.assertTrue(result['guest_workspace_preserved_for_recovery'])
            lifecycle.finish()
            self.assertEqual(json.loads((Path(folder) / 'result.json').read_text())['retrieval_error'], 'transfer lost')

    def test_collected_invalid_report_is_retained_and_remote_copy_cleaned(self):
        with TemporaryDirectory() as folder:
            evidence = Path(folder) / 'guest.json'
            evidence.write_text(json.dumps(dict(source={'commit': 'other'}, backend='fixture', phases=[])))
            result = dict(source={'commit': 'fixed'}, status='passed')
            cleanup = Mock()
            lifecycle = GuestResultLifecycle(result, folder, 'fixture', 'test_workspace')
            lifecycle.collect(Mock(), evidence, cleanup)
            cleanup.assert_called_once()
            self.assertTrue(evidence.exists())
            self.assertTrue(result['test_workspace_removed'])
            self.assertEqual(result['status'], 'failed')

    def test_cleanup_failure_and_cancelled_outcome_remain_explicit(self):
        for status, cleanup_error in (('cancelled', None), ('passed', OSError('cleanup denied'))):
            with self.subTest(status=status), TemporaryDirectory() as folder:
                evidence = Path(folder) / 'guest.json'
                evidence.write_text(json.dumps(dict(source={'commit': 'fixed'}, backend='fixture',
                                                    status=status, phases=[dict(id='one', status=status)])))
                result = dict(source={'commit': 'fixed'}, status=status)
                lifecycle = GuestResultLifecycle(result, folder, 'fixture', 'test_workspace')
                lifecycle.collect(Mock(), evidence, Mock(side_effect=cleanup_error))
                self.assertEqual(result['phases'][0]['status'], status)
                self.assertEqual(result['status'], 'failed' if cleanup_error else status)
                self.assertEqual('cleanup_error' in result, bool(cleanup_error))

    def test_passing_exit_requires_matching_passing_evidence(self):
        for report in (None, dict(source={'commit': 'fixed'}, backend='fixture', status='failed', phases=[])):
            with self.subTest(report=report), TemporaryDirectory() as folder:
                evidence = Path(folder) / 'guest.json'
                if report:
                    evidence.write_text(json.dumps(report))
                result = dict(source={'commit': 'fixed'}, status='passed')
                lifecycle = GuestResultLifecycle(result, folder, 'fixture', 'guest_workspace')
                lifecycle.collect(Mock(), evidence, Mock())
                self.assertEqual(result['status'], 'failed')
                self.assertIn('retrieval_error', result)


    def test_headless_wait_labels_advisory_state_without_inventing_test_results(self):
        from contextlib import redirect_stdout
        import io
        from logistics_build.guest_results import waiting_progress
        output = io.StringIO()
        with redirect_stdout(output):
            progress = waiting_progress('Windows', 'selected checks')
            progress(dict(state='waiting', seconds=30))
            progress(dict(state='reconciling', seconds=31))
        text = output.getvalue()
        self.assertIn('waiting for worker result', text)
        self.assertIn('reconciling worker receipt', text)
        self.assertIn('30s (headless)', text)
        self.assertNotIn('passed', text)


class CompletedManagerEvidenceTests(unittest.TestCase):
    def setUp(self):
        from build_manager.models import Phase, Plan
        import hashlib
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manager = 'a'*40
        self.source = dict(logistics_commit='c'*40, commonUtils_commit='b'*40)
        self.backend = 'Parallels fedora'
        self.guest = self.root/'guest/reports/manager'
        self.guest.mkdir(parents=True)
        plan = Plan('Logistics','Focused Linux contracts',self.source,
                    (Phase('focused',('python','-m','unittest','discover','-s',
                                     '/var/tmp/owned/manager/Python/tests','-p','test*.py','-v'),
                           '/var/tmp/owned/source'),),'/var/tmp/owned/operation',backend=self.backend)
        plan.save(self.guest/'plan.json')
        engine = {name:dict(commit=commit,dirty=False,fingerprint=hashlib.sha256(commit.encode()).hexdigest())
                  for name,commit in [('manager',self.manager),('commonUtils','b'*40)]}
        self.report = dict(schema=1,status='passed',source=self.source,backend=self.backend,
                           plan_identity=plan.identity,engine=engine,
                           phases=[dict(id='focused',status='passed',required=True,log='focused.log')])
        (self.guest/'result.json').write_text(json.dumps(self.report))
        (self.guest/'focused.log').write_text('Ran complete manager contracts\nOK\n')
        self.result = dict(schema=1,status='passed',source=self.source,workspace='/var/tmp/owned',
                           guest_result=str(self.guest/'result.json'),guest_workspace_removed=True)
        (self.root/'result.json').write_text(json.dumps(self.result))

    def verify(self):
        from logistics_build.guest_results import verified_manager_completion
        return verified_manager_completion(self.root,self.source,self.backend,self.manager)

    def test_legacy_backend_is_verified_from_guest_plan_without_changing_records(self):
        before=(self.root/'result.json').read_bytes()
        receipt=self.verify()
        self.assertEqual(receipt['status'],'verified-passed')
        self.assertTrue(receipt['legacy_backend_inferred'])
        self.assertFalse(receipt['fresh_execution'])
        self.assertEqual((self.root/'result.json').read_bytes(),before)
        (self.guest/'focused.log').write_text('changed after review')
        self.assertNotEqual(self.verify()['identity'],receipt['identity'])

    def test_incomplete_foreign_or_uncleaned_results_never_certify(self):
        for changes in (dict(status='unknown'),dict(guest_workspace_removed=False),
                        dict(source={'logistics_commit':'foreign'}),dict(backend='Other guest')):
            with self.subTest(changes=changes):
                (self.root/'result.json').write_text(json.dumps(dict(self.result,**changes)))
                with self.assertRaises(ValueError):self.verify()
        (self.root/'result.json').write_text(json.dumps(self.result))
        self.report['phases']=[]
        (self.guest/'result.json').write_text(json.dumps(self.report))
        with self.assertRaisesRegex(ValueError,'Required'):self.verify()

    def test_changed_engine_and_narrowed_suite_are_rejected(self):
        self.report['engine']['manager']['dirty']=True
        (self.guest/'result.json').write_text(json.dumps(self.report))
        with self.assertRaisesRegex(ValueError,'checkout identity'):self.verify()
        self.report['engine']['manager']['dirty']=False
        data=json.loads((self.guest/'plan.json').read_text())
        data['phases'][0]['argv'][-2]='test_one.py'
        from build_manager.models import Plan
        plan=Plan.from_data(data);plan.save(self.guest/'plan.json')
        self.report['plan_identity']=plan.identity
        (self.guest/'result.json').write_text(json.dumps(self.report))
        with self.assertRaisesRegex(ValueError,'complete declared'):self.verify()

    def test_real_lifecycle_and_attempt_owner_agree_on_backend(self):
        from logistics_build.guest_attempts import result_attempt
        from contextlib import redirect_stdout
        import io
        root=self.root/'new-attempts'
        with result_attempt(root,self.source,self.backend) as attempt:
            attempt.mkdir()
            result=dict(source=self.source,status='failed')
            lifecycle=GuestResultLifecycle(result,attempt,self.backend,'guest_workspace')
            self.assertEqual(result['backend'],self.backend)
            result['guest_workspace_removed']=True
            with redirect_stdout(io.StringIO()):lifecycle.finish()
        self.assertEqual(json.loads((root/'result.json').read_text())['backend'],self.backend)


    def test_source_annotations_cannot_substitute_a_different_guest_capture(self):
        from logistics_build.guest_results import retained_guest_source
        from build_manager.models import Plan, Phase
        source=dict(self.source,dirty=False,fingerprint='e'*64)
        root=self.root/'declared-results'
        attempt=root/'attempts'/('f'*32)
        command=('python','-m','logistics_build.vm_backend','--source-identity',json.dumps(source),'--results',str(root))
        plan=Plan('Logistics','Focused',dict(source,destination='display-only'),
                  (Phase('guest',command,str(self.root)),),str(self.root/'workspace'))
        self.assertEqual(retained_guest_source(plan,self.backend,attempt),source)
        with self.assertRaisesRegex(ValueError,'outside'):
            retained_guest_source(plan,self.backend,self.root/('f'*32))
        from dataclasses import replace
        with self.assertRaisesRegex(ValueError,'differs'):
            retained_guest_source(replace(plan,source=dict(plan.source,fingerprint='d'*64)),self.backend,attempt)
