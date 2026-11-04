"""Accepted GitHub validation is observed on resume without another dispatch."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
from dataclasses import replace
import json
import os
from pathlib import Path
import signal
import sys
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import build_manager
from build_manager import Phase
from build_manager.executor import Executor
from build_manager.workflows import approve
from logistics_build import build_project as owner

ROOT = Path(__file__).resolve().parents[3]
SHA = 'a' * 40

TRANSPORT = r'''
import json,os
from pathlib import Path
from build_manager import github
from mobile_build.deployment import manager_settings
state_path=Path(os.environ['FIXTURE_GITHUB_STATE'])
manager_settings.settings=lambda root: ({'github.repository':'fixture/repo',
 'github.token_environment':'FIXTURE_TOKEN','github.authentication':'existing git credential helper'}, {})
github.credential_token=lambda **kw:'fixture-no-network-token'
def request(self,method,path,body=None):
 state=json.loads(state_path.read_text())
 if '/git/ref/' in path:return {'object':{'type':'commit','sha':'a'*40}}
 if method=='POST' and path.endswith('/dispatches'):
  state['posts']=state.get('posts',0)+1;state_path.write_text(json.dumps(state))
  return {} if state.get('without_id') else {'workflow_run_id':777}
 if method=='GET' and path.endswith('/actions/runs/777'):
  state.setdefault('observed',[]).append(777);state_path.write_text(json.dumps(state))
  if state['outcome']=='network':raise RuntimeError('Fixture transport unavailable')
  return {'id':777,'head_sha':'a'*40,'path':'.github/workflows/archive-platform-checks.yml',
   'repository':{'full_name':'fixture/repo'},'head_branch':'alpha','event':'workflow_dispatch',
   'status':'completed','conclusion':state['outcome']}
 raise AssertionError('Unexpected transport operation: '+method+' '+path)
github.GitHub.request=request
'''


class HostedObservationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.state = self.root / 'transport.json'
        self.site = self.root / 'fixture-imports'; self.site.mkdir()
        (self.site / 'sitecustomize.py').write_text(TRANSPORT)
        self.project = owner.LogisticsProject(ROOT)
        self.project.interpreter = Path(sys.executable)
        self.values = {'github.repository': 'fixture/repo'}

    def plan(self, outcome='failure', *, without_id=False, review=False):
        self.state.write_text(json.dumps(dict(posts=0, outcome=outcome, without_id=without_id)))
        plan = self.project.github_plan('Test', 'linux', dict(dirty=False, logistics_commit=SHA),
            self.root / 'workspace', {}, 'alpha', '')
        env = dict(FIXTURE_GITHUB_STATE=str(self.state), PYTHONDONTWRITEBYTECODE='1',
                   PYTHONPATH=os.pathsep.join(dict.fromkeys((str(self.site), str(ROOT / 'Python'),
                       str(ROOT), str(Path(build_manager.__file__).resolve().parents[1]),
                       *[str(Path(p).resolve()) for p in os.environ.get('PYTHONPATH', '').split(os.pathsep) if p]))))
        phases = tuple(replace(p, environment=dict(p.environment, **env)) for p in plan.phases)
        if review:
            phases += (Phase('delivery', (sys.executable, '-c', 'raise AssertionError("unapproved effect")'),
                str(ROOT), dependencies=(phases[-1].id,), approval_required=True, effect='deploy'),)
        return replace(plan, phases=phases)

    def execute(self, plan, *, resume=False):
        runner = Executor(resource_directory=self.root / 'resources', evidence_directory=self.root / 'evidence')
        if not resume:
            review = runner.run(plan, self.root / 'run', confirmed=True)
            self.assertEqual(review['status'], 'awaiting_review')
            self.assertFalse(any(row['status'] == 'passed' for row in review['phases']))
            return runner.run(plan, self.root / 'run', confirmed=True, resume=True,
                              approvals=(approve(plan, plan.phases[0].id, review),))
        return runner.run(plan, self.root / 'run', confirmed=True, resume=True)

    def test_terminal_remote_failure_is_failed_and_resume_observes_same_run(self):
        for outcome in ('failure', 'network'):
            with self.subTest(outcome=outcome):
                # Each scenario owns independent persisted history and transport.
                scenario = self.root / outcome; scenario.mkdir()
                previous = self.root; self.root = scenario
                self.state = scenario / 'transport.json'
                try:
                    plan = self.plan(outcome)
                    failed = self.execute(plan)
                    self.assertEqual(failed['status'], 'failed', failed.get('error'))
                    self.assertEqual([r['status'] for r in failed['phases']], ['passed', 'failed'])
                    accepted = Path(plan.phases[0].artifacts[0]).read_bytes()
                    state = json.loads(self.state.read_text()); self.assertEqual(state['posts'], 1)
                    if outcome == 'network':
                        state['outcome'] = 'success'; self.state.write_text(json.dumps(state))
                    resumed = self.execute(plan, resume=True)
                    self.assertEqual(resumed['status'], 'passed' if outcome == 'network' else 'failed',
                                     resumed.get('error'))
                    state = json.loads(self.state.read_text()); self.assertEqual(state['posts'], 1)
                    self.assertTrue(state['observed']); self.assertEqual(set(state['observed']), {777})
                    self.assertEqual(Path(plan.phases[0].artifacts[0]).read_bytes(), accepted)
                finally:
                    self.root = previous

    def test_accepted_without_identity_stays_unknown_without_automatic_repost(self):
        plan = self.plan(without_id=True)
        first = self.execute(plan)
        self.assertEqual(first['status'], 'unknown')
        self.assertEqual(first['phases'][0]['status'], 'unknown')
        again = self.execute(plan, resume=True)
        self.assertEqual(again['status'], 'unknown')
        self.assertEqual(json.loads(self.state.read_text())['posts'], 1)
        self.assertFalse(Path(plan.phases[0].artifacts[0]).exists())

    def test_delivery_review_waits_for_observation_success(self):
        plan = self.plan('network', review=True)
        failed = self.execute(plan)
        self.assertEqual(failed['status'], 'failed')
        self.assertNotEqual(failed['phases'][-1]['status'], 'awaiting_review')
        state = json.loads(self.state.read_text()); state['outcome'] = 'success'
        self.state.write_text(json.dumps(state))
        waiting = self.execute(plan, resume=True)
        self.assertEqual(waiting['status'], 'awaiting_review')
        self.assertEqual(waiting['phases'][-1]['status'], 'awaiting_review')
        self.assertEqual(json.loads(self.state.read_text())['posts'], 1)

    def arguments(self):
        return SimpleNamespace(command='github-observe', operation_receipt=self.root / 'accepted.json',
            observation_receipt=self.root / 'observation.json', ref='alpha', workflow='mobile-runtime.yml',
            platform='android', commit=SHA, no_test_reuse=False)

    def test_published_ref_named_github_dispatch_is_not_rewritten(self):
        plan = self.project.github_plan('Test', 'linux', dict(dirty=False, logistics_commit=SHA),
            self.root / 'workspace', {}, 'github-dispatch', '')
        self.assertEqual([phase.argv[3] for phase in plan.phases], ['github-dispatch', 'github-observe'])
        self.assertTrue(all(phase.argv[phase.argv.index('--ref') + 1] == 'github-dispatch'
                            for phase in plan.phases))

    def accepted(self):
        return dict(schema=1, provider='github', repository='fixture/repo', expected_commit=SHA,
            workflow='mobile-runtime.yml', ref='alpha', platform='android', run_id=777,
            status='queued', operation_id='fixture-operation', inputs={'target':'android'})

    def test_wrong_receipt_binding_stops_before_any_observation(self):
        for key, value in dict(repository='other/repo', expected_commit='b'*40, workflow='other.yml',
                ref='other', platform='ios', inputs={'target':'ios'}, run_id=True, operation_id='').items():
            with self.subTest(key=key):
                args = self.arguments(); accepted = self.accepted(); accepted[key] = value
                args.operation_receipt.write_text(json.dumps(accepted))
                client = Mock(base='/repos/fixture/repo')
                with self.assertRaises(ValueError):owner.hosted_validation(client, self.values, args, Event())
                client.request.assert_not_called(); client.wait.assert_not_called()

    def test_wrong_remote_identity_stops_before_wait_or_cancellation(self):
        valid = dict(id=777, head_sha=SHA, path='.github/workflows/mobile-runtime.yml',
            repository={'full_name':'fixture/repo'}, event='workflow_dispatch', head_branch='alpha')
        for key, value in dict(id=778, head_sha='b'*40, path='.github/workflows/other.yml',
                repository={'full_name':'other/repo'}, head_branch='other', event='push').items():
            with self.subTest(key=key):
                args = self.arguments(); args.operation_receipt.write_text(json.dumps(self.accepted()))
                client = Mock(base='/repos/fixture/repo'); client.request.return_value = dict(valid, **{key:value})
                with self.assertRaises(ValueError):owner.hosted_validation(client, self.values, args, Event())
                client.wait.assert_not_called()
                self.assertTrue(all(c.args[0]=='GET' for c in client.request.call_args_list))

    def test_observation_cannot_overwrite_acceptance_through_path_alias(self):
        args = self.arguments(); args.operation_receipt.write_text(json.dumps(self.accepted()))
        args.observation_receipt = self.root / 'unused' / '..' / 'accepted.json'
        client = Mock(base='/repos/fixture/repo')
        before = args.operation_receipt.read_bytes()
        with self.assertRaises(ValueError):owner.hosted_validation(client, self.values, args, Event())
        client.request.assert_not_called(); client.wait.assert_not_called()
        self.assertEqual(args.operation_receipt.read_bytes(), before)

    def test_normal_cancellation_targets_only_verified_recorded_run(self):
        from build_manager.github import GitHub
        args = self.arguments(); args.operation_receipt.write_text(json.dumps(self.accepted()))
        calls = []
        def transport(method, path, body=None):
            calls.append((method,path))
            if method == 'GET':
                return dict(id=777, head_sha=SHA, path='.github/workflows/mobile-runtime.yml',
                    repository={'full_name':'fixture/repo'}, event='workflow_dispatch', head_branch='alpha')
            self.assertEqual((method,path), ('POST','/repos/fixture/repo/actions/runs/777/cancel'))
            return {}
        cancelled = Event(); cancelled.set()
        with self.assertRaises(RuntimeError):
            owner.hosted_validation(GitHub('fixture/repo', transport=transport), self.values, args, cancelled)
        self.assertEqual(calls, [('GET','/repos/fixture/repo/actions/runs/777'),
                                ('POST','/repos/fixture/repo/actions/runs/777/cancel')])
        self.assertFalse(args.observation_receipt.exists())

    def test_legacy_github_command_still_dispatches_and_waits(self):
        client = Mock(); client.dispatch.return_value = 777
        client.wait.return_value = dict(status='completed', conclusion='success')
        argv = ['build_project.py','github','--root',str(ROOT),'--platform','android',
                '--workflow','mobile-runtime.yml','--ref','alpha','--commit',SHA]
        with patch.object(sys,'argv',argv), patch.object(owner.manager_settings,'settings',return_value=(self.values,{})), \
                patch.object(owner,'github_client',return_value=client), patch.object(signal,'signal'):
            self.assertEqual(owner.main(),0)
        client.dispatch.assert_called_once();client.wait.assert_called_once()
