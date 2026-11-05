"""Automatic hosted evidence is bound once and observed without provider mutations."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import build_manager
from build_manager.github import GitHub
from build_manager.executor import Executor
from build_manager.workflows import approve
from logistics_build import build_project
from logistics_build import hosted_run_intake as owner
from logistics_build.hosted_requirements import PUSH_DEFAULTS, REQUIRED

ROOT = Path(__file__).resolve().parents[3]
SHA = subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()

TRANSPORT = r'''
import json,os
from pathlib import Path
from datetime import datetime,timezone
from build_manager import github
from mobile_build.deployment import manager_settings
from logistics_build.hosted_requirements import REQUIRED
state_path=Path(os.environ['FIXTURE_GITHUB_STATE'])
manager_settings.settings=lambda root: ({'github.repository':'fixture/repo',
 'github.token_environment':'FIXTURE_TOKEN','github.authentication':'existing git credential helper'}, {})
github.credential_token=lambda **kw:'fixture-no-network-token'
def request(self,method,path,body=None):
 state=json.loads(state_path.read_text());state.setdefault('requests',[]).append([method,path]);state_path.write_text(json.dumps(state))
 if method!='GET':raise AssertionError('Adoption must never mutate the provider')
 run=dict(id=888,run_attempt=1,workflow_id=42,head_sha=os.environ['FIXTURE_SOURCE_SHA'],
  head_branch='alpha',event='push',path='.github/workflows/archive-platform-checks.yml',
  repository={'full_name':'fixture/repo'},head_repository={'full_name':'fixture/repo'},
  created_at=state['created_at'],html_url='https://github.com/fixture/repo/actions/runs/888',
  status='completed',conclusion=state['outcome'])
 if path.endswith('/actions/workflows/archive-platform-checks.yml'):
  return {'id':42,'path':run['path']}
 if '/actions/workflows/42/runs?' in path:
  return {'workflow_runs':[dict(run,status='in_progress',conclusion=None)],'total_count':1}
 if path.endswith('/actions/runs/888'):
  if state['outcome']=='network':raise RuntimeError('Fixture observation unavailable')
  if state.get('changed_attempt'):run['run_attempt']=2
  return run
 if '/attempts/1/jobs?' in path:
  jobs=[dict(name=name,status='completed',conclusion='success',completed_at=state['created_at']) for name in REQUIRED['validate'][1]]
  if state.get('partial'):jobs.pop()
  return {'jobs':jobs,'total_count':len(jobs)}
 raise AssertionError('Unexpected read-only transport path: '+path)
github.GitHub.request=request
'''


class HostedRunIntakeTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(TemporaryDirectory())).resolve()
        self.now=datetime.now(timezone.utc)
        self.expected=dict(repository='fixture/repo',expected_commit=SHA,
            workflow='archive-platform-checks.yml',ref='alpha',platform='linux',inputs={'target':'linux'})
        self.policy=owner.contract(ROOT,self.expected)
        self.assertIsNotNone(self.policy)
        self.run=dict(id=888,run_attempt=1,workflow_id=42,head_sha=SHA,head_branch='alpha',event='push',
            path='.github/workflows/archive-platform-checks.yml',repository={'full_name':'fixture/repo'},
            head_repository={'full_name':'fixture/repo'},created_at=self.now.isoformat(),
            html_url='https://github.com/fixture/repo/actions/runs/888',status='completed',conclusion='success')
        self.jobs=[dict(name=name,status='completed',conclusion='success',completed_at=self.now.isoformat())
                   for name in REQUIRED['validate'][1]]
        self.calls=[]

    def transport(self,method,path,body=None):
        self.calls.append((method,path))
        if method!='GET':raise AssertionError('An adopted observer must never mutate remote work')
        if path.endswith('/actions/workflows/archive-platform-checks.yml'):
            return dict(id=42,path=self.run['path'])
        if '/actions/workflows/42/runs?' in path:
            return dict(workflow_runs=[self.run],total_count=1)
        if path.endswith('/actions/runs/888'):
            return deepcopy(self.run)
        if '/attempts/1/jobs?' in path:
            return dict(jobs=self.jobs,total_count=len(self.jobs))
        self.fail('Unexpected API path: '+path)

    def adopted(self):
        receipt=owner.intake(GitHub('fixture/repo',transport=self.transport),ROOT,self.expected,now=self.now)
        receipt['operation_id']='fixture-operation'
        return receipt

    def test_adopts_exact_full_scope_source_with_actual_creation_attempt_and_url(self):
        self.run.update(status='in_progress',conclusion=None)
        receipt=self.adopted()
        self.assertEqual(receipt['schema'],2);self.assertEqual(receipt['origin'],'existing-run')
        self.assertEqual(receipt['automatic']['run_attempt'],1)
        self.assertEqual(receipt['automatic']['created_at'],self.run['created_at'])
        self.assertEqual(receipt['automatic']['html_url'],self.run['html_url'])
        self.assertEqual(receipt['policy']['required_jobs'],sorted(REQUIRED['validate'][1]))
        self.assertTrue(all(method=='GET' for method,_ in self.calls))

    def test_wrong_repository_source_event_workflow_branch_attempt_or_age_cannot_adopt(self):
        baseline=deepcopy(self.run)
        cases=dict(head_sha='b'*40,head_branch='other',event='workflow_dispatch',workflow_id=43,
            repository={'full_name':'other/repo'},head_repository={'full_name':'fork/repo'},
            run_attempt=True,created_at=(self.now-timedelta(hours=25)).isoformat(),html_url='https://other.test/888')
        for key,value in cases.items():
            with self.subTest(key=key):
                self.run=deepcopy(baseline);self.run[key]=value
                self.assertIsNone(owner.intake(GitHub('fixture/repo',transport=self.transport),ROOT,self.expected,now=self.now))
        self.assertTrue(all(method=='GET' for method,_ in self.calls))

    def test_changed_workflow_contract_or_nondefault_settings_never_query_or_adopt(self):
        client=Mock()
        for changes in (dict(inputs={'target':'linux','reuse_test_results':'off'}),dict(platform='unknown')):
            with self.assertRaisesRegex(ValueError,'disable reuse'):
                owner.intake(client,ROOT,dict(self.expected,**changes))
        self.assertIsNone(owner.intake(client,ROOT,dict(self.expected,ref='refs/tags/v1.0.0-alpha.1')))
        with patch.object(owner.subprocess,'run',return_value=NS(stdout=b'changed push defaults')):
            with self.assertRaisesRegex(ValueError,'disable reuse'):
                owner.intake(client,ROOT,self.expected)
        client.request.assert_not_called()

    def test_multiple_matching_runs_fail_without_a_provider_write(self):
        def request(method,path,body=None):
            value=self.transport(method,path,body)
            if 'workflow_runs' in value:value=dict(workflow_runs=[self.run,deepcopy(self.run)],total_count=2)
            return value
        with self.assertRaisesRegex(ValueError,'Multiple matching'):
            owner.intake(GitHub('fixture/repo',transport=request),ROOT,self.expected,now=self.now)
        self.assertTrue(all(method=='GET' for method,_ in self.calls))

    def test_full_family_success_passes_but_partial_skipped_failed_or_stale_jobs_fail(self):
        receipt=self.adopted();original=deepcopy(self.jobs)
        result=owner.observe(GitHub('fixture/repo',transport=self.transport),receipt,ROOT,self.expected,Event())
        self.assertEqual(result['status'],'passed')
        self.jobs=original[:-1]
        with self.assertRaises(ValueError):owner.observe(GitHub('fixture/repo',transport=self.transport),receipt,ROOT,self.expected,Event())
        for changes in (dict(conclusion='skipped'),dict(conclusion='failure'),dict(completed_at=(self.now-timedelta(hours=25)).isoformat())):
            self.jobs=deepcopy(original);self.jobs[0].update(changes)
            with self.assertRaises(ValueError):owner.observe(GitHub('fixture/repo',transport=self.transport),receipt,ROOT,self.expected,Event())
        self.assertTrue(all(method=='GET' for method,_ in self.calls))

    def test_changed_attempt_or_identity_rejected_even_during_wait_without_post(self):
        receipt=self.adopted()
        for field,value in (('run_attempt',2),('head_sha','b'*40),('workflow_id',99),
                            ('head_repository',{'full_name':'other/repo'}),('event','workflow_dispatch')):
            saved=deepcopy(self.run);self.run[field]=value
            with self.assertRaises(ValueError):owner.observe(GitHub('fixture/repo',transport=self.transport),receipt,ROOT,self.expected,Event())
            self.run=saved
        self.assertTrue(all(method=='GET' for method,_ in self.calls))

    def test_cancelled_observer_leaves_shared_automatic_run_live_without_any_post(self):
        receipt=self.adopted();self.run.update(status='in_progress',conclusion=None)
        cancelled=Event();cancelled.set()
        with self.assertRaisesRegex(RuntimeError,'stopped locally'):
            owner.observe(GitHub('fixture/repo',transport=self.transport),receipt,ROOT,self.expected,cancelled)
        self.assertEqual(self.run['status'],'in_progress')
        self.assertTrue(all(method=='GET' for method,_ in self.calls))

    def test_terminal_failure_is_a_failed_gate_not_permission_to_dispatch(self):
        self.run.update(conclusion='failure');receipt=self.adopted()
        with self.assertRaisesRegex(RuntimeError,'did not pass'):
            owner.observe(GitHub('fixture/repo',transport=self.transport),receipt,ROOT,self.expected,Event())
        self.assertTrue(all(method=='GET' for method,_ in self.calls))

    def test_receipt_policy_or_expected_source_tampering_stops_before_remote_observation(self):
        receipt=self.adopted();self.calls.clear()
        for changes in (dict(origin='dispatch'),dict(expected_commit='b'*40),dict(policy={}),dict(operation_id='')):
            with self.assertRaises(ValueError):
                owner.observe(GitHub('fixture/repo',transport=self.transport),dict(receipt,**changes),ROOT,self.expected,Event())
        self.assertFalse(self.calls)

    def test_reviewed_push_contract_matches_all_committed_workflow_blobs(self):
        for workflow,policy in PUSH_DEFAULTS.items():
            blob=subprocess.check_output(['git','-C',str(ROOT),'show',SHA+':.github/workflows/'+workflow])
            self.assertEqual(hashlib.sha256(blob).hexdigest(),policy['sha256'])

    def test_crlf_checkout_does_not_change_exact_committed_workflow_contract(self):
        workflow='archive-platform-checks.yml'
        relative='.github/workflows/'+workflow
        blob=subprocess.check_output(['git','-C',str(ROOT),'show',SHA+':'+relative])
        project=self.root/'crlf-checkout'
        file=project/relative
        file.parent.mkdir(parents=True)
        def git(*args):
            return subprocess.check_output(['git','-C',str(project),*args],stderr=subprocess.PIPE)
        git('init','--quiet')
        git('config','core.autocrlf','false')
        file.write_bytes(blob)
        git('add',relative)
        git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--quiet','-m','fixture')
        revision=git('rev-parse','HEAD').decode().strip()
        file.write_bytes(blob.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
        self.assertNotEqual(hashlib.sha256(file.read_bytes()).hexdigest(),PUSH_DEFAULTS[workflow]['sha256'])
        expected=dict(self.expected,expected_commit=revision)
        policy=owner.contract(project,expected)
        self.assertEqual(policy['workflow_sha256'],PUSH_DEFAULTS[workflow]['sha256'])
        # A real source change is still rejected even if the working copy is restored.
        file.write_bytes(blob+b'\n# unreviewed source change\n')
        git('add',relative)
        git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--quiet','-m','changed source')
        changed=git('rev-parse','HEAD').decode().strip()
        file.write_bytes(blob)
        with self.assertRaisesRegex(ValueError,'Automatic push defaults changed'):
            owner.contract(project,dict(expected,expected_commit=changed))

    def test_attempt_change_on_second_sdk_poll_is_rejected_without_mutation(self):
        receipt=self.adopted();observations=[]
        def transport(method,path,body=None):
            row=self.transport(method,path,body)
            if path.endswith('/actions/runs/888'):
                observations.append(1)
                row.update(status='in_progress',conclusion=None) if len(observations)==1 else row.update(run_attempt=2)
            return row
        cancelled=Mock();cancelled.is_set.return_value=False
        with self.assertRaisesRegex(ValueError,'attempt'):
            owner.observe(GitHub('fixture/repo',transport=transport),receipt,ROOT,self.expected,cancelled)
        self.assertEqual(len(observations),2)
        self.assertTrue(all(method=='GET' for method,_ in self.calls))

    def test_timeout_retains_the_run_and_never_issues_a_provider_write(self):
        receipt=self.adopted();self.calls.clear()
        with patch.object(owner,'contract',return_value=self.policy), \
                patch('build_manager.github.time.monotonic',side_effect=[0,14000]):
            with self.assertRaises(TimeoutError):
                owner.observe(GitHub('fixture/repo',transport=self.transport),receipt,ROOT,self.expected,Event())
        self.assertFalse(self.calls)

    def test_native_and_runtime_adoption_require_the_entire_family_not_only_selected_ios(self):
        for workflow in ('mobile-build.yml','mobile-runtime.yml'):
            with self.subTest(workflow=workflow):
                expected=dict(self.expected,workflow=workflow,platform='ios',inputs={'target':'ios'})
                policy=owner.contract(ROOT,expected)
                row=dict(self.run,path=policy['workflow_path'])
                jobs=[dict(name=name,status='completed',conclusion='success',completed_at=self.now.isoformat())
                      for name in REQUIRED[policy['family']][1]]
                calls=[]
                def request(method,path,body=None):
                    calls.append((method,path))
                    if method!='GET':raise AssertionError('No remote mutation')
                    if path.endswith('/actions/workflows/'+workflow):return dict(id=42,path=policy['workflow_path'])
                    if '/actions/workflows/42/runs?' in path:return dict(workflow_runs=[row],total_count=1)
                    if '/attempts/1/jobs?' in path:return dict(jobs=jobs,total_count=len(jobs))
                    if path.endswith('/actions/runs/888'):return row
                    self.fail(path)
                client=GitHub('fixture/repo',transport=request)
                receipt=owner.intake(client,ROOT,expected,now=self.now);receipt['operation_id']='native-fixture'
                proof=owner.observe(client,receipt,ROOT,expected,Event())
                self.assertEqual(proof['jobs'],sorted(REQUIRED[policy['family']][1]))
                missing='Validate Android' if workflow=='mobile-build.yml' else 'android'
                jobs[:]=[job for job in jobs if job['name']!=missing]
                with self.assertRaises(ValueError):owner.observe(client,receipt,ROOT,expected,Event())
                self.assertTrue(all(method=='GET' for method,_ in calls))


class HostedCoalescingExecutorTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(TemporaryDirectory())).resolve()
        self.site=self.root/'site';self.site.mkdir();(self.site/'sitecustomize.py').write_text(TRANSPORT)
        self.state=self.root/'transport.json'
        self.project=build_project.LogisticsProject(ROOT);self.project.interpreter=Path(sys.executable)

    def plan(self,outcome='network',review=False):
        self.state.write_text(json.dumps(dict(outcome=outcome,created_at=datetime.now(timezone.utc).isoformat())))
        plan=self.project.github_plan('Test','linux',dict(dirty=False,logistics_commit=SHA),self.root/'workspace',{},'alpha','')
        env=dict(FIXTURE_GITHUB_STATE=str(self.state),FIXTURE_SOURCE_SHA=SHA,PYTHONDONTWRITEBYTECODE='1',
            PYTHONPATH=os.pathsep.join(dict.fromkeys((str(self.site),str(ROOT),str(ROOT/'Python'),
                str(Path(build_manager.__file__).resolve().parents[1]),
                *[str(Path(p).resolve()) for p in os.environ.get('PYTHONPATH','').split(os.pathsep) if p]))))
        phases=tuple(replace(p,environment=dict(p.environment,**env)) for p in plan.phases)
        if review:
            from build_manager import Phase
            phases+=(Phase('delivery',(sys.executable,'-c','raise AssertionError("unapproved effect")'),str(ROOT),
                           dependencies=(phases[-1].id,),approval_required=True,effect='deploy'),)
        return replace(plan,phases=phases)

    def execute(self,plan,resume=False):
        runner=Executor(resource_directory=self.root/'resources',evidence_directory=self.root/'evidence')
        if not resume:
            review=runner.run(plan,self.root/'run',confirmed=True)
            self.assertEqual(review['status'],'awaiting_review')
            return runner.run(plan,self.root/'run',confirmed=True,resume=True,approvals=(approve(plan,plan.phases[0].id,review),))
        return runner.run(plan,self.root/'run',confirmed=True,resume=True)

    def test_normal_executor_adopts_then_network_resume_never_dispatches_or_mutates_receipt(self):
        plan=self.plan(review=True)
        failed=self.execute(plan);self.assertEqual(failed['status'],'failed',failed.get('error'))
        receipt=Path(plan.phases[0].artifacts[0]).read_bytes()
        self.assertEqual(json.loads(receipt)['origin'],'existing-run')
        self.assertNotEqual(failed['phases'][-1]['status'],'awaiting_review')
        state=json.loads(self.state.read_text());state['outcome']='success';self.state.write_text(json.dumps(state))
        waiting=self.execute(plan,resume=True);self.assertEqual(waiting['status'],'awaiting_review',waiting.get('error'))
        self.assertEqual(waiting['phases'][-1]['status'],'awaiting_review')
        self.assertEqual(Path(plan.phases[0].artifacts[0]).read_bytes(),receipt)
        self.assertTrue(all(method=='GET' for method,_ in json.loads(self.state.read_text())['requests']))

    def test_terminal_failed_automatic_run_remains_failed_on_resume_without_new_post(self):
        plan=self.plan('failure')
        for resume in (False,True):
            result=self.execute(plan,resume=resume)
            self.assertEqual(result['status'],'failed',result.get('error'))
            self.assertEqual([row['status'] for row in result['phases']],['passed','failed'])
        self.assertTrue(all(method=='GET' for method,_ in json.loads(self.state.read_text())['requests']))

    def test_reuse_off_explicitly_dispatches_fresh_without_querying_automatic_inventory(self):
        args=NS(command='github-dispatch',operation_receipt=self.root/'fresh.json',observation_receipt=None,
                root=ROOT,ref='alpha',workflow='archive-platform-checks.yml',platform='linux',commit=SHA,no_test_reuse=True)
        client=Mock();client.dispatch.return_value=999
        with patch.dict(os.environ,BUILD_MANAGER_OPERATION_ID='explicit-fresh'):
            self.assertEqual(build_project.hosted_validation(client,{'github.repository':'fixture/repo'},args,Event()),0)
        client.request.assert_not_called();client.dispatch.assert_called_once()
        self.assertEqual(json.loads(args.operation_receipt.read_text())['schema'],1)
