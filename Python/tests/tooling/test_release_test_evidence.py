"""Signed local proof crosses a real Git-notes transport; invalid proof runs fresh."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from build_manager import Phase, Plan
from build_manager.evidence import EvidenceCache
from logistics_build import release_test_evidence as evidence


@unittest.skipUnless(shutil.which('ssh-keygen'), 'SSH signing tool unavailable')
class ReleaseTestEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'source'
        self.root.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Evidence fixture')
        self.key = self.base / 'signing'
        with patch.object(evidence, 'signing_key', return_value=self.key):
            evidence.enroll(self.root, 'owner/project')
        (self.root / 'build-manager-dependency.json').write_text(json.dumps(dict(revision='b' * 40)))
        self.git('add', '.')
        self.git('update-index', '--add', '--cacheinfo', '160000,' + 'c' * 40 + ',Python/commonUtils')
        self.git('commit', '-qm', 'Fixture source')
        # A missing worktree gitlink looks dirty; export needs the pinned index,
        # while this fixture only models its identity rather than a real library.
        self.git('update-index', '--assume-unchanged', 'Python/commonUtils')
        environment = patch.dict('os.environ', {'GITHUB_SHA': self.git('rev-parse', 'HEAD')})
        environment.start()
        self.addCleanup(environment.stop)
        self.now = datetime.now(timezone.utc)
        self.phase = Phase('macos.validation.commonutils', ('python', 'tests.py'), str(self.root),
                           effect='test', reuse_key='a' * 64)
        self.cache = EvidenceCache(self.base / 'cache')
        self.cache.execute(self.phase, self.base, lambda: dict(id=self.phase.id, status='passed',
                           finished_at=self.now.isoformat(), seconds=10, artifacts=[]))
        self.request = self.base / 'request.json'
        self.request.write_text(json.dumps(dict(source=evidence.bindings(self.root, 'owner/project')['source'],
                                               phases=[asdict(self.phase)])))
        self.digest = hashlib.sha256(self.request.read_bytes()).hexdigest()

    def git(self, *args):
        return evidence.git(self.root, *args).stdout.decode().strip()

    def export(self, **kwargs):
        return evidence.prepare_export(self.root, 'owner/project', self.request, self.digest,
                                       cache=self.cache, key=self.key, now=kwargs.get('now', self.now))

    def match(self, envelope=None, phase=None):
        return evidence.matched_proof(self.root, phase or replace(self.phase, id='commonutils'),
                                      envelope=envelope, repository='owner/project', now=self.now)

    def test_real_signature_and_notes_round_trip_preserve_independent_input_binding(self):
        proof = self.export()
        self.assertEqual(self.match(proof)['inputs'], 'a' * 64)
        remote = self.base / 'remote.git'
        subprocess.run(['git', 'init', '-q', '--bare', str(remote)], check=True)
        self.git('remote', 'add', 'origin', str(remote))
        self.git('push', '-q', 'origin', 'HEAD:refs/heads/main')
        evidence.publish_note(self.root, proof, self.base / 'envelope.json')
        self.assertEqual(self.match()['source'], evidence.bindings(self.root, 'owner/project')['source'])
        # A retry reconciles the exact existing proof without replacing it.
        evidence.publish_note(self.root, proof, self.base / 'envelope.json')
        changed = json.loads(json.dumps(proof))
        changed['signature'] = 'changed'
        with self.assertRaises(ValueError):
            evidence.publish_note(self.root, changed, self.base / 'envelope.json')
        self.assertEqual(json.loads(self.git('notes', '--ref=' + evidence.NOTE_REF, 'show', 'HEAD')), proof)

    def test_changed_receiver_inputs_source_or_signature_require_fresh_checks(self):
        proof = self.export()
        self.assertIsNone(self.match(proof, replace(self.phase, reuse_key='d' * 64)))
        bad = json.loads(json.dumps(proof))
        bad['payload']['bindings']['source'] = 'e' * 40
        self.assertIsNone(self.match(bad))
        bad = json.loads(json.dumps(proof))
        bad['signature'] = 'bad'
        self.assertIsNone(self.match(bad))
        (self.root / '.github/local-test-signers').write_text('untrusted signer\n')
        self.assertIsNotNone(self.match(proof))  # Working edits cannot enroll a new signer.
        self.git('add', '.github/local-test-signers')
        self.git('commit', '-qm', 'Changed trust source')
        self.assertIsNone(self.match(proof))

    def test_other_hosted_source_never_accepts_fixture_proof(self):
        proof = self.export()
        with patch.dict('os.environ', {'GITHUB_SHA': 'e' * 40}):
            self.assertIsNone(self.match(proof))

    def test_changed_reviewed_recipe_dirty_source_and_old_receipts_are_not_exported(self):
        self.assertIsNone(self.export(now=self.now + timedelta(days=2)))
        self.request.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'request changed'):
            self.export()
        (self.root / 'uncommitted.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'Commit intended source'):
            self.export()

    def test_missing_or_corrupt_receipts_do_not_create_a_signed_pass(self):
        path = self.cache.directory / ('a' * 64 + '.json')
        data = json.loads(path.read_text())
        data['payload']['row']['status'] = 'failed'
        path.write_text(json.dumps(data))
        self.assertIsNone(self.export())

    def test_export_request_is_bound_into_release_command_not_device_commands(self):
        release = Phase('github.delivery.release-source-and-gates', ('python', 'release.py'),
                        str(self.root), effect='publish', kind='publication')
        plan = Plan('Fixture', 'Release', {'logistics_commit': self.git('rev-parse', 'HEAD')},
                    (self.phase, release), str(self.base / 'workspace'), effect='publish')
        result = evidence.with_export_request(plan)
        self.assertEqual(result.phases[0], self.phase)
        command = result.phases[-1].argv
        path = Path(command[command.index('--test-evidence-request') + 1])
        digest = command[command.index('--test-evidence-sha256') + 1]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
        self.assertEqual(json.loads(path.read_text())['phases'][0]['reuse_key'], self.phase.reuse_key)


    def test_hosted_wrapper_reuses_verified_proof_and_runs_fresh_on_mismatch(self):
        import sys
        from build_manager import Executor
        from logistics_build.platform_checks import run_check
        proof = self.export()
        marker = self.base / 'executed'
        command = [sys.executable, '-c', 'from pathlib import Path;Path(' + repr(str(marker)) + ').touch()']
        def bound(plan):
            return replace(plan, phases=(replace(plan.phases[0], reuse_key='a' * 64),))
        receiver = evidence.matched_proof
        environment = dict(GITHUB_ACTIONS='true', GITHUB_REPOSITORY='owner/project',
                           GITHUB_SHA=self.git('rev-parse', 'HEAD'))
        with patch.dict('os.environ', environment), patch('logistics_build.test_evidence.with_reuse', side_effect=bound), \
             patch('logistics_build.release_test_evidence.matched_proof', side_effect=lambda root, phase: receiver(root, phase, envelope=proof, repository='owner/project', now=self.now)), \
             patch('logistics_build.platform_checks.Executor', side_effect=lambda **kw: Executor(evidence_directory=self.base/'receiver-cache', **kw)):
            reused = run_check('commonutils', command, root=self.root, results=self.base/'results', environment={}, timeout=10)
            self.assertTrue(reused['reused'])
            self.assertFalse(marker.exists())
            proof['payload']['tests'][0]['inputs'] = 'f' * 64
            fresh = run_check('commonutils', command, root=self.root, results=self.base/'results', environment={}, timeout=10)
            self.assertNotIn('reused', fresh)
            self.assertTrue(marker.exists())
            self.assertEqual(fresh['status'], 'passed')


    def test_unavailable_note_transport_cannot_break_fresh_validation(self):
        for error in (OSError('unavailable'), subprocess.TimeoutExpired(['git'], 60)):
            with self.subTest(error=type(error).__name__), patch.object(evidence, 'git', side_effect=error):
                self.assertFalse(evidence.fetch_note(self.root))


    def test_debug_policy_disables_hosted_reuse_through_the_release_tag(self):
        tag = 'v0.1.0-alpha.1'
        self.git('tag', '-a', tag, '-m', 'Logistics release\n\nBuild-Manager-Reuse: off')
        with patch.dict('os.environ', {'GITHUB_REF': 'refs/tags/' + tag, 'LOGISTICS_REUSE_TEST_RESULTS': 'on'}):
            self.assertTrue(evidence.reuse_disabled(self.root))
        with patch.dict('os.environ', {'GITHUB_REF': 'refs/heads/alpha', 'LOGISTICS_REUSE_TEST_RESULTS': 'off'}):
            self.assertTrue(evidence.reuse_disabled(self.root))
        self.git('tag', 'v0.1.0-alpha.2')
        with patch.dict('os.environ', {'GITHUB_REF': 'refs/tags/v0.1.0-alpha.2', 'LOGISTICS_REUSE_TEST_RESULTS': 'on'}):
            self.assertFalse(evidence.reuse_disabled(self.root))
        with patch.dict('os.environ', {'GITHUB_REF': 'refs/tags/unavailable', 'LOGISTICS_REUSE_TEST_RESULTS': 'on'}):
            self.assertTrue(evidence.reuse_disabled(self.root))


    def test_release_plan_carries_the_explicit_fresh_execution_choice(self):
        import sys
        from logistics_build.build_project import LogisticsProject
        project = object.__new__(LogisticsProject)
        project.root, project.interpreter = self.root, Path(sys.executable)
        source = dict(dirty=False, logistics_commit=self.git('rev-parse', 'HEAD'),
                      run_overrides={'testing.reuse_verified_results': 'off'})
        plan = project.github_plan('Release', 'macos', source, self.base / 'release-work', {},
                                   'HEAD', 'v0.1.0-alpha.1')
        self.assertIn('--no-test-reuse', plan.phases[0].argv)
        source['run_overrides'] = {}
        plan = project.github_plan('Release', 'macos', source, self.base / 'release-work', {},
                                   'HEAD', 'v0.1.0-alpha.1')
        self.assertNotIn('--no-test-reuse', plan.phases[0].argv)

    def test_off_release_creates_a_new_annotated_policy_tag_without_moving_a_tag(self):
        from logistics_build.build_project import release_source
        from threading import Event
        commit = self.git('rev-parse', 'HEAD')
        commands = []
        def read(root, *arguments):
            if arguments == ('status', '--porcelain'):
                return ''
            return commit if arguments == ('rev-parse', 'HEAD') else 'main'
        def run(command, **kwargs):
            commands.append(command)
            if command[:2] == ['git', 'tag']:
                raise RuntimeError('Fixture stops before tag push')
        with patch('logistics_build.build_project.git', side_effect=read), \
             patch('logistics_build.build_project.subprocess.check_output', return_value=''), \
             patch('logistics_build.build_project.subprocess.run', side_effect=run):
            with self.assertRaisesRegex(RuntimeError, 'Fixture stops'):
                release_source(self.root, None, 'v0.1.0-alpha.1', commit, Event(), reuse_test_results=False)
        tag = next(command for command in commands if command[:2] == ['git', 'tag'])
        self.assertIn('-a', tag)
        self.assertIn('Build-Manager-Reuse: off', tag[-1])
        self.assertNotIn('-f', tag)
