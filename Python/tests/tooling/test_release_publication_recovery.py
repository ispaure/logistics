"""Owned immutable publication recovery; provider effects are scripted only."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from logistics_build import build_project as owner


class Missing(RuntimeError):
    status = 404


class Provider:
    repository = 'owner/project'
    base = '/repos/owner/project'

    def __init__(self, case):
        self.case = case
        self.tag_exists = True
        self.number = 1
        self.posts = []
        self.reconciles = []
        self.asset_reads = 0
        self.partial = 0
        self.unknown = False
        self.jobs = self.success_jobs()
        self.release = dict(id=42, tag_name=case.tag, draft=False, prerelease=True,
            html_url='https://example.invalid/release', name='Reviewed', body='Reviewed notes',
            assets=[dict(id=4, name='release.zip', digest='sha256:' + 'a' * 64, size=123)])

    @staticmethod
    def success_jobs():
        return [dict(id=i + 1, name=name, status='completed', conclusion='success' if name in {'evidence', 'package', 'publish'} else 'skipped')
                for i, name in enumerate(('evidence', 'validate', 'mobile-build', 'mobile-runtime', 'package', 'publish'))]

    def get(self, path, **kwargs):
        if '/git/ref/tags/' in path:
            if not self.tag_exists:
                raise Missing()
            return dict(object=dict(type='tag', sha=self.case.tag_object))
        if '/git/tags/' in path:
            return dict(object=dict(type='commit', sha=self.case.commit))
        if '/commits/' in path:
            return dict(sha=self.case.commit)
        if '/releases/' in path:
            self.asset_reads += 1
            if self.partial:
                self.partial -= 1
                result = copy.deepcopy(self.release)
                result['assets'] = []
                return result
            return copy.deepcopy(self.release)
        if '/attempts/' in path and '/jobs?' in path:
            return dict(jobs=copy.deepcopy(self.jobs))
        if '/actions/runs?' in path:
            return dict(workflow_runs=[dict(id=77, run_attempt=self.number, head_sha=self.case.commit,
                head_branch=self.case.tag, path='.github/workflows/release.yml')])
        raise AssertionError(path)

    def resolve_ref(self, tag):
        return self.case.commit

    def attempt(self, run, attempt, commit, **kwargs):
        assert (run, attempt, commit) == (77, self.number, self.case.commit)
        return dict(id=run, run_attempt=attempt, head_sha=commit, status='queued', conclusion=None)

    def job_log(self, job, **kwargs):
        return 'Finalizing artifact upload\nUnexpected token <, <!DOCTYPE html> is not valid JSON'

    def rerun_failed(self, run, commit, **kwargs):
        record = json.loads(self.case.receipt.read_text())
        assert record['reruns'][-1]['status'] == 'intent'
        self.posts.append((run, kwargs['expected_attempt']))
        self.number += 1
        self.jobs = self.success_jobs()
        if self.unknown:
            raise RuntimeError('Provider response unknown after accepted POST')
        return dict(status='accepted', run_id=run, run_attempt=self.number)

    def reconcile_rerun(self, run, commit, **kwargs):
        self.reconciles.append(kwargs['expected_attempt'])
        return dict(status='accepted', run_id=run, run_attempt=self.number)

    def request(self, method, path, body=None):
        assert method == 'PATCH'
        self.posts.append((method, body))
        self.release.update(body)
        return copy.deepcopy(self.release)


class PublicationRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.receipt = self.root / 'publication.json'
        self.tag = 'v0.2.0-alpha.99'
        self.token = 'b' * 32
        self.dependency = 'c' * 40
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.PIPE, text=True).strip()
        self.git = git
        git('init', '-q')
        git('config', 'user.name', 'Publication fixture')
        git('config', 'user.email', 'fixture@example.invalid')
        git('config', 'commit.gpgsign', 'false')
        git('config', 'tag.gpgsign', 'false')
        workflow = self.root / '.github/workflows/release.yml'
        workflow.parent.mkdir(parents=True)
        shutil.copyfile(Path(owner.__file__).parents[1] / '.github/workflows/release.yml', workflow)
        git('add', '.')
        git('update-index', '--add', '--cacheinfo', '160000,' + self.dependency + ',Python/commonUtils')
        git('commit', '-qm', 'Synthetic release DAG')
        self.commit = git('rev-parse', 'HEAD')
        self.message = 'Logistics source release\n\nBuild-Manager-Publication: ' + self.token
        git('tag', '-a', self.tag, self.commit, '-m', self.message)
        self.tag_object = git('rev-parse', 'refs/tags/' + self.tag)
        self.client = Provider(self)
        self.verified = []
        def verify(asset, commit, dependency, cancelled, **kwargs):
            self.verified.append((commit, dependency))
            return dict(sha256='a' * 64, bytes=123, logistics_commit=commit, commonUtils_commit=dependency)
        self.addCleanup(patch.stopall)
        patch('logistics_build.release_verification.verify_asset', side_effect=verify).start()
        self.real_metadata = owner._publication_metadata
        patch.object(owner, '_publication_metadata', side_effect=lambda root, commit, tag, release, client, cancelled: release).start()
        patch('builtins.print').start()
        self.seed()

    def seed(self, **changes):
        binding = dict(repository=self.client.repository, root=str(self.root.resolve()), tag=self.tag,
            commit=self.commit, commonUtils_commit=self.dependency, owner=self.token,
            reuse_test_results=True, github_validation='on', workflow='.github/workflows/release.yml')
        value = dict(schema=1, binding=binding, status='tag-pushed', tag_object=self.tag_object, reruns=[], run_id=77, attempt=1)
        value.update(changes)
        self.receipt.write_text(json.dumps(value))
        return value

    def run_owned(self, **kwargs):
        return owner._owned_release_source(self.root, self.client, self.tag, self.commit, Event(),
            receipt=self.receipt, owner=self.token, reuse_test_results=True,
            published_commit=True, timeout=.2, poll=.001, **kwargs)

    def test_release_plan_hosted_policy_defaults_on_and_off_is_explicit(self):
        from logistics_build.manager_journeys import run_values
        project = object.__new__(owner.LogisticsProject)
        project.root, project.interpreter = self.root, Path(sys.executable)
        for choice in (None, 'on', 'off'):
            with self.subTest(choice=choice):
                overrides = {} if choice is None else run_values({'testing.github_validation': choice})
                source = dict(dirty=False, logistics_commit=self.commit, run_overrides=overrides)
                plan = project.github_plan('Release', 'macos', source, self.root / 'plan', {}, 'HEAD', self.tag)
                self.assertEqual(len(plan.phases), 1)  # Advanced Release has no local test phases.
                self.assertEqual(plan.source['github_validation'], choice or 'on')
                self.assertEqual('--skip-hosted-validation' in plan.phases[0].argv, choice == 'off')
                self.assertIn('--operation-receipt', plan.phases[0].argv)
                self.assertIn('--publication-owner', plan.phases[0].argv)
        with self.assertRaisesRegex(ValueError, 'GitHub release validation'):
            run_values({'testing.github_validation': 'skip'})
        descriptor = json.loads((Path(owner.__file__).parents[1] / 'build-project.json').read_text())
        field = next(row for row in descriptor['run_fields'] if row['id'] == 'testing.github_validation')
        self.assertEqual(field['default'], 'on')
        self.assertEqual(set(field['options']), {'on', 'off'})

    def test_policy_cannot_change_on_owned_resume_and_legacy_bypass_needs_journal(self):
        with self.assertRaisesRegex(ValueError, 'differs'):
            self.run_owned(github_validation='off')
        with self.assertRaisesRegex(ValueError, 'requires its reviewed publication journal'):
            owner.release_source(self.root, self.client, self.tag, self.commit, Event(), skip_hosted_validation=True)
        self.assertFalse(self.client.posts)

    def test_fresh_off_tag_records_marker_and_receipt_mode(self):
        self.receipt.unlink()
        self.git('tag', '-d', self.tag)
        self.client.tag_exists = False
        run = subprocess.run
        def command(argv, **kwargs):
            if argv[:2] == ['git', 'push']:
                record = json.loads(self.receipt.read_text())
                self.assertEqual(record['binding']['github_validation'], 'off')
                self.tag_object = self.git('rev-parse', 'refs/tags/' + self.tag)
                contents = self.git('for-each-ref', '--format=%(contents)', 'refs/tags/' + self.tag)
                self.assertIn('Build-Manager-Hosted-Validation: off', contents)
                self.assertIn('Build-Manager-Publication: ' + self.token, contents)
                self.client.tag_exists = True
                return subprocess.CompletedProcess(argv, 0)
            return run(argv, **kwargs)
        with patch.object(owner.subprocess, 'run', side_effect=command):
            self.assertEqual(self.run_owned(github_validation='off'), 0)
        self.assertFalse(self.client.posts)

    def test_cli_capability_preflight_also_precedes_optional_evidence_publish(self):
        argv = ['build_project', 'release', '--root', str(self.root), '--tag', self.tag,
            '--commit', self.commit, '--operation-receipt', str(self.receipt),
            '--publication-owner', self.token, '--test-evidence-request', str(self.root / 'request.json')]
        with patch('sys.argv', argv), patch.object(owner.manager_settings, 'settings', return_value=({}, {})), \
                patch.object(owner, 'github_client', return_value=object()), \
                patch.object(owner.signal, 'signal'), \
                patch('logistics_build.release_test_evidence.publish_note') as publish, \
                patch.object(owner.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'lacks owned publication recovery'):
                owner.main()
        publish.assert_not_called()
        run.assert_not_called()

    def test_cli_owned_resume_skips_newer_tree_guard_and_evidence_republication(self):
        argv = ['build_project', 'release', '--root', str(self.root), '--tag', self.tag,
            '--commit', self.commit, '--operation-receipt', str(self.receipt),
            '--publication-owner', self.token, '--test-evidence-request', str(self.root / 'request.json')]
        with patch('sys.argv', argv), patch.object(owner.manager_settings, 'settings', return_value=({}, {})), \
                patch.object(owner, 'github_client', return_value=self.client), \
                patch.object(owner.signal, 'signal'), \
                patch('logistics_build.release_test_evidence.publish_note') as publish, \
                patch.object(owner, 'git', side_effect=AssertionError('Old immutable receipt is checked by its owning helper')), \
                patch.object(owner, 'release_source', return_value=0) as release:
            self.assertEqual(owner.main(), 0)
        publish.assert_not_called()
        self.assertEqual(release.call_args.kwargs['operation_receipt'], self.receipt)

    def test_real_sdk_paired_transport_or_old_pin_preflight(self):
        from build_manager.github import GitHub
        calls = []
        def transport(method, path, body):
            calls.append(method)
            self.assertEqual(method, 'GET')
            if path.endswith('/attempts/1'):
                return dict(id=77, run_attempt=1, head_sha=self.commit, head_branch=self.tag,
                    path='.github/workflows/release.yml', repository=dict(full_name='owner/project'),
                    status='queued', conclusion=None)
            return self.client.get(path)
        client = GitHub('owner/project', transport=transport)
        if not all(callable(getattr(client, name, None)) for name in ('get', 'attempt', 'rerun_failed', 'reconcile_rerun', 'job_log')):
            with self.assertRaisesRegex(RuntimeError, 'lacks owned publication recovery'):
                owner._owned_release_source(self.root, client, self.tag, self.commit, Event(),
                    receipt=self.receipt, owner=self.token, reuse_test_results=True, published_commit=True)
            self.assertEqual(calls, [])
            return
        self.assertEqual(owner._owned_release_source(self.root, client, self.tag, self.commit, Event(),
            receipt=self.receipt, owner=self.token, reuse_test_results=True, published_commit=True, timeout=.2, poll=.001), 0)
        self.assertTrue(calls)
        self.assertEqual(set(calls), {'GET'})

    def test_fresh_tag_persists_owner_intent_before_push(self):
        self.receipt.unlink()
        self.git('tag', '-d', self.tag)
        self.client.tag_exists = False
        run = subprocess.run
        pushes = []
        def command(argv, **kwargs):
            if argv[:2] == ['git', 'push']:
                record = json.loads(self.receipt.read_text())
                self.assertEqual(record['status'], 'tag-push-intent')
                self.tag_object = self.git('rev-parse', 'refs/tags/' + self.tag)
                self.assertEqual(record['tag_object'], self.tag_object)
                self.assertEqual(record['binding']['github_validation'], 'on')
                self.assertNotIn('Build-Manager-Hosted-Validation:', self.git('for-each-ref', '--format=%(contents)', 'refs/tags/' + self.tag))
                self.client.tag_exists = True
                pushes.append(argv)
                return subprocess.CompletedProcess(argv, 0)
            return run(argv, **kwargs)
        with patch.object(owner.subprocess, 'run', side_effect=command):
            self.assertEqual(self.run_owned(), 0)
        self.assertEqual(len(pushes), 1)

    def test_accepted_tag_push_unknown_resumes_without_second_push(self):
        self.receipt.unlink()
        self.git('tag', '-d', self.tag)
        self.client.tag_exists = False
        run = subprocess.run
        pushes = []
        def command(argv, **kwargs):
            if argv[:2] == ['git', 'push']:
                pushes.append(argv)
                self.tag_object = self.git('rev-parse', 'refs/tags/' + self.tag)
                self.client.tag_exists = True
                raise subprocess.CalledProcessError(1, argv)
            return run(argv, **kwargs)
        with patch.object(owner.subprocess, 'run', side_effect=command):
            with self.assertRaises(subprocess.CalledProcessError):
                self.run_owned()
            self.assertEqual(self.run_owned(), 0)
        self.assertEqual(len(pushes), 1)

    def test_metadata_repair_reads_captured_notes_and_preserves_state_and_assets(self):
        script = self.root / '.github/scripts/publish_release.py'
        script.parent.mkdir(parents=True)
        shutil.copyfile(Path(owner.__file__).parents[1] / '.github/scripts/publish_release.py', script)
        notes = self.root / '.github/release-notes/v0.2.0-alpha.1.md'
        notes.parent.mkdir()
        notes.write_text('# Old title\n\nReviewed exact description.\n')
        self.git('add', '.github')
        self.git('commit', '-qm', 'Captured reviewed notes')
        source = self.git('rev-parse', 'HEAD')
        release = copy.deepcopy(self.client.release)
        before = copy.deepcopy(release['assets'])
        actual = self.real_metadata(self.root, source, self.tag, release, self.client, Event())
        self.assertEqual(actual['name'], 'Logistics 0.2.0-alpha.99')
        self.assertEqual(actual['body'], '# Logistics 0.2.0-alpha.99\n\nReviewed exact description.\n')
        self.assertEqual(actual['assets'], before)
        self.assertFalse(actual['draft'])
        self.assertTrue(actual['prerelease'])
        self.assertEqual(self.client.posts, [('PATCH', dict(name=actual['name'], body=actual['body']))])
        self.real_metadata(self.root, source, self.tag, actual, self.client, Event())
        self.assertEqual(len(self.client.posts), 1)

    def test_owned_existing_asset_and_exact_terminal_jobs_rescue_stale_aggregate(self):
        with patch.object(owner.subprocess, 'run', wraps=subprocess.run) as run:
            self.assertEqual(self.run_owned(), 0)
        self.assertTrue(self.verified)
        self.assertFalse(self.client.posts)
        self.assertFalse(any(call.args[0][:2] == ['git', 'push'] for call in run.call_args_list))
        proof = json.loads(self.receipt.read_text())['proof']
        self.assertEqual(proof['aggregate_status'], 'queued')
        self.assertEqual(proof['run_attempt'], 1)

    def test_unowned_existing_tag_is_not_adopted(self):
        self.receipt.unlink()
        with self.assertRaisesRegex(ValueError, 'without this operation'):
            self.run_owned()
        self.assertFalse(self.receipt.exists())

    def test_owner_source_and_dependency_mismatch_are_rejected(self):
        for field, value in (('owner', 'd' * 32), ('commit', 'e' * 40), ('commonUtils_commit', 'f' * 40)):
            with self.subTest(field=field):
                saved = self.seed()
                saved['binding'][field] = value
                self.receipt.write_text(json.dumps(saved))
                with self.assertRaisesRegex(ValueError, 'differs'):
                    self.run_owned()
        self.assertFalse(self.client.posts)

    def test_moved_tag_is_rejected(self):
        self.tag_object = 'f' * 40
        with self.assertRaisesRegex(ValueError, 'unowned, moved'):
            self.run_owned()

    def test_missing_new_sdk_apis_fail_before_any_source_or_provider_effect(self):
        with patch.object(owner.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'lacks owned publication recovery'):
                owner._owned_release_source(self.root, object(), self.tag, self.commit, Event(),
                    receipt=self.receipt, owner=self.token, reuse_test_results=True, published_commit=True)
        run.assert_not_called()

    def test_pre_cancelled_or_invalid_budget_or_commit_has_no_provider_effect(self):
        for change in ({'timeout': 0}, {'poll': float('inf')}, {'commit': 'HEAD'}, {'cancelled': True}):
            event = Event()
            if change.get('cancelled'):
                event.set()
            with self.subTest(change=change), patch.object(self.client, 'get') as read:
                with self.assertRaises((ValueError, RuntimeError)):
                    owner._owned_release_source(self.root, self.client, self.tag, change.get('commit', self.commit), event,
                        receipt=self.receipt, owner=self.token, reuse_test_results=True, published_commit=True,
                        timeout=change.get('timeout', .2), poll=change.get('poll', .001))
                read.assert_not_called()

    def failed(self, conclusion='failure', artifact=False):
        self.client.jobs[0].update(conclusion=conclusion, steps=[
            dict(number=1, name='Verify recent exact-source workflow evidence', conclusion='success'),
            dict(number=2, name='Run actions/upload-artifact@verified', conclusion=conclusion)] if artifact else
            [dict(number=1, name='Run application tests', conclusion='failure')])
        self.client.jobs[-2]['conclusion'] = self.client.jobs[-1]['conclusion'] = 'skipped'

    def test_valid_zip_never_overrides_product_gate_failure(self):
        self.failed()
        with self.assertRaisesRegex(RuntimeError, 'Required release jobs failed'):
            self.run_owned()
        self.assertTrue(self.verified)
        self.assertFalse(self.client.posts)
        self.assertNotEqual(json.loads(self.receipt.read_text())['status'], 'verified')

    def test_cancelled_artifact_finalization_html_permits_one_failed_jobs_rerun(self):
        self.failed('cancelled', artifact=True)
        self.assertEqual(self.run_owned(), 0)
        self.assertEqual(self.client.posts, [(77, 1)])
        self.assertEqual(json.loads(self.receipt.read_text())['attempt'], 2)

    def test_user_cancellation_without_finalization_proof_is_not_retried(self):
        self.failed('cancelled', artifact=True)
        self.client.job_log = lambda *args, **kwargs: 'User cancelled this job'
        with self.assertRaisesRegex(RuntimeError, 'Required release jobs failed'):
            self.run_owned()
        self.assertFalse(self.client.posts)

    def test_unknown_post_is_reconciled_read_only_on_resume(self):
        self.failed('timed_out', artifact=True)
        self.client.unknown = True
        with self.assertRaisesRegex(RuntimeError, 'response unknown'):
            self.run_owned()
        self.assertEqual(self.client.posts, [(77, 1)])
        self.assertEqual(json.loads(self.receipt.read_text())['reruns'][-1]['status'], 'intent')
        self.assertEqual(self.run_owned(), 0)
        self.assertEqual(self.client.posts, [(77, 1)])
        self.assertEqual(self.client.reconciles, [1])

    def test_partial_release_is_observed_without_upload_or_metadata_patch(self):
        self.client.partial = 2
        self.assertEqual(self.run_owned(), 0)
        self.assertGreaterEqual(self.client.asset_reads, 3)
        self.assertFalse(self.client.posts)

    def test_asset_deleted_or_replaced_before_terminal_witness_never_passes(self):
        terminal = owner._publication_terminal
        original = copy.deepcopy(self.client.release)
        for replaced in (False, True):
            with self.subTest(replaced=replaced):
                self.seed()
                self.client.release = copy.deepcopy(original)
                def observe(root, commit, jobs):
                    if replaced:
                        self.client.release['assets'][0]['id'] = 999
                    else:
                        self.client.release = None
                    return terminal(root, commit, jobs)
                with patch.object(owner, '_publication_terminal', side_effect=observe):
                    with self.assertRaisesRegex(RuntimeError, 'changed during gate observation'):
                        self.run_owned()
                self.assertNotEqual(json.loads(self.receipt.read_text())['status'], 'verified')
                self.assertFalse(self.client.posts)
        self.client.release = original

    def test_early_visible_success_jobs_are_not_terminal_proof(self):
        self.client.jobs = self.client.jobs[:1]
        with self.assertRaises(TimeoutError):
            self.run_owned()
        self.assertFalse(self.client.posts)

    def test_release_state_and_duplicate_asset_are_strict(self):
        for changes in (dict(tag_name='v0.2.0-beta.99'), dict(prerelease=False),
                        dict(assets=self.client.release['assets'] * 2)):
            with self.subTest(changes=changes):
                original = copy.deepcopy(self.client.release)
                self.client.release.update(changes)
                with self.assertRaisesRegex(RuntimeError, 'identity or channel'):
                    self.run_owned()
                self.client.release = original


if __name__ == '__main__':
    unittest.main()
