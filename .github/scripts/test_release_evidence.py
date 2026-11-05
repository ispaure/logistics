"""Only complete, fresh, exact-commit trusted workflow coverage can be reused."""

# TEST_STAGE = TestStage.REGRESSION
from copy import deepcopy
from datetime import datetime, timezone
import unittest
from select_release_evidence import select, REQUIRED, hosted_validation_mode


class ReleaseEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.sha = 'a' * 40
        self.now = datetime(2026, 10, 27, tzinfo=timezone.utc)
        self.run = dict(id=42, head_sha=self.sha, path=REQUIRED['validate'][0],
            status='completed', conclusion='success', event='push',
            head_repository={'full_name': 'fixture/repo'}, html_url='https://github.com/fixture/repo/actions/runs/42')
        self.jobs = [dict(name=name, status='completed', conclusion='success', completed_at='2026-10-26T23:00:00Z')
                     for name in REQUIRED['validate'][1]]

    def inspect(self):
        def request(path):
            return {'workflow_runs': [self.run]} if path.startswith('/actions/runs?') else {'jobs': self.jobs}
        return select(request, 'fixture/repo', self.sha, now=self.now)

    def test_complete_exact_commit_matrix_is_reused_with_provenance(self):
        self.assertEqual(self.inspect()['validate']['run_id'], 42)
        self.assertNotIn('mobile-build', self.inspect())

    def test_partial_failed_stale_different_source_or_fork_never_skips(self):
        original = deepcopy(self.jobs)
        self.jobs.pop()
        self.assertEqual(self.inspect(), {})
        for changes in ({'conclusion': 'failure'}, {'conclusion': 'skipped'}, {'completed_at': '2026-10-24T00:00:00Z'}):
            self.jobs = deepcopy(original)
            self.jobs[0].update(changes)
            self.assertEqual(self.inspect(), {})
        self.jobs = original
        for changes in ({'head_sha': 'b' * 40}, {'event': 'pull_request'}, {'head_repository': {'full_name': 'fork/repo'}}):
            saved = deepcopy(self.run)
            self.run.update(changes)
            self.assertEqual(self.inspect(), {})
            self.run = saved


    def test_android_build_and_ui_are_both_required_for_native_evidence_reuse(self):
        self.run['path'] = REQUIRED['mobile-build'][0]
        required = REQUIRED['mobile-build'][1]
        self.assertIn('Build shared Android test app', required)
        self.assertIn('Validate Android', required)
        self.jobs = [dict(name=name, status='completed', conclusion='success',
                         completed_at='2026-10-26T23:00:00Z') for name in required]
        self.assertIn('mobile-build', self.inspect())
        original = deepcopy(self.jobs)
        for name in ('Build shared Android test app', 'Validate Android'):
            for status in ('failure', 'skipped', 'cancelled'):
                self.jobs = deepcopy(original)
                next(job for job in self.jobs if job['name'] == name)['conclusion'] = status
                self.assertNotIn('mobile-build', self.inspect())
            self.jobs = [job for job in deepcopy(original) if job['name'] != name]
            self.assertNotIn('mobile-build', self.inspect())

    def test_debug_off_forces_fresh_without_consulting_previous_hosted_passes(self):
        from unittest.mock import Mock
        request = Mock(side_effect=AssertionError('Fresh debug policy must not reuse prior runs'))
        self.assertEqual(select(request, 'fixture/repo', self.sha, now=self.now, reuse_allowed=False), {})
        request.assert_not_called()


class ReleasePublicationWorkflowTests(unittest.TestCase):
    def test_publish_survives_reused_validation_but_requires_successful_package(self):
        from pathlib import Path
        workflow = (Path(__file__).resolve().parents[1] / 'workflows/release.yml').read_text()
        publish = workflow.split('\n  publish:\n', 1)[1]
        condition = publish.split('    if: >-\n', 1)[1].split('    runs-on:', 1)[0]
        # An explicit status check suppresses implicit success() propagation
        # from deliberately skipped validation ancestors. Packaging still gates publication.
        self.assertIn('always()', condition)
        self.assertIn('!cancelled()', condition)
        self.assertIn("needs.package.result == 'success'", condition)
        self.assertIn("github.event_name == 'push'", condition)
        self.assertIn("startsWith(github.ref, 'refs/tags/v')", condition)


class HostedValidationPolicyTests(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        import subprocess
        from tempfile import TemporaryDirectory
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.subprocess = subprocess
        self.git('init', '-q')
        self.git('config', 'user.name', 'Policy fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'tag.gpgsign', 'false')
        (self.root / 'source').write_text('reviewed source')
        self.git('add', 'source')
        self.git('commit', '-qm', 'Synthetic source')
        self.commit = self.git('rev-parse', 'HEAD')
        self.ref = 'refs/tags/v0.2.0-alpha.7'
        self.owner = 'Build-Manager-Publication: ' + 'b' * 32

    def git(self, *args):
        return self.subprocess.check_output(['git', *args], cwd=self.root, stderr=self.subprocess.PIPE, text=True).strip()

    def tag(self, policy):
        self.git('tag', '-a', self.ref.removeprefix('refs/tags/'), '-m', self.owner + '\n' + policy)

    def mode(self, event='push', commit=None):
        return hosted_validation_mode(self.root, commit or self.commit, self.ref, event)

    def test_default_strict_lightweight_and_annotated_tags(self):
        self.git('tag', self.ref.removeprefix('refs/tags/'))
        self.assertEqual(self.mode(), 'on')
        self.git('tag', '-d', self.ref.removeprefix('refs/tags/'))
        self.tag('Ordinary reviewed tag')
        self.assertEqual(self.mode(), 'on')

    def test_explicit_owned_annotated_push_tag_selects_distinct_off_mode(self):
        self.tag('Build-Manager-Hosted-Validation: off')
        self.assertEqual(self.mode(), 'off')
        self.assertEqual(self.mode(event='workflow_dispatch'), 'on')

    def test_unknown_duplicate_malformed_and_unowned_opt_out_fail_closed(self):
        for policy in ('Build-Manager-Hosted-Validation: maybe',
                       'Build-Manager-Hosted-Validation: off\nBuild-Manager-Hosted-Validation: on',
                       'build-manager-hosted-validation: off',
                       'Build-Manager-Hosted-Validation=off'):
            with self.subTest(policy=policy):
                self.tag(policy)
                with self.assertRaises(ValueError):
                    self.mode()
                self.git('tag', '-d', self.ref.removeprefix('refs/tags/'))
        self.git('tag', '-a', self.ref.removeprefix('refs/tags/'), '-m', 'Build-Manager-Hosted-Validation: off')
        with self.assertRaisesRegex(ValueError, 'owned publication'):
            self.mode()

    def test_policy_is_bound_to_exact_source(self):
        self.tag('Build-Manager-Hosted-Validation: off')
        with self.assertRaisesRegex(ValueError, 'captured source'):
            self.mode(commit='a' * 40)

    def test_off_main_never_queries_rest_or_claims_verified_reuse(self):
        import json
        import os
        from unittest.mock import Mock, patch
        import select_release_evidence as selector
        self.tag('Build-Manager-Hosted-Validation: off')
        environment = dict(GITHUB_REPOSITORY='fixture/repo', GITHUB_SHA=self.commit,
            GITHUB_REF=self.ref, GITHUB_EVENT_NAME='push', GITHUB_TOKEN='not-used',
            GITHUB_OUTPUT=str(self.root / 'output'), GITHUB_STEP_SUMMARY=str(self.root / 'summary'))
        opener = Mock()
        with patch.dict(os.environ, environment), patch.object(selector.Path, 'cwd', return_value=self.root), \
                patch.object(selector, 'build_opener', return_value=opener):
            # main's relative evidence files belong to this isolated fixture.
            prior = os.getcwd()
            try:
                os.chdir(self.root)
                selector.main()
            finally:
                os.chdir(prior)
        opener.open.assert_not_called()
        self.assertEqual(json.loads((self.root / 'release-evidence.json').read_text()), {})
        policy = json.loads((self.root / 'release-validation-policy.json').read_text())
        self.assertTrue(policy['hosted_skip'])
        self.assertEqual(policy['verified_reuse_families'], [])
        self.assertEqual(policy['source'], self.commit)
        self.assertEqual((self.root / 'output').read_text().splitlines(),
            ['hosted-skip=true', 'validate=false', 'mobile-build=false', 'mobile-runtime=false'])
        summary = (self.root / 'summary').read_text()
        self.assertIn('no hosted validation', summary)
        self.assertNotIn('reused [verified', summary)

    def test_actual_package_expression_requires_strict_gates_or_distinct_opt_out(self):
        from pathlib import Path
        workflow = (Path(__file__).resolve().parents[1] / 'workflows/release.yml').read_text()
        condition = workflow.split('\n  package:', 1)[1].split('    if: >-\n', 1)[1].split('    runs-on:', 1)[0]
        def allows(skip, results, reuse=False, evidence='success'):
            expression = condition.replace('always()', 'True').replace('!cancelled()', 'True')
            values = {"needs.evidence.outputs['hosted-skip']": str(skip).lower(),
                      'needs.evidence.result': evidence}
            for name, result in zip(('validate', 'mobile-build', 'mobile-runtime'), results):
                key = 'needs.validate.result' if name == 'validate' else "needs['" + name + "'].result"
                output = 'needs.evidence.outputs.validate' if name == 'validate' else "needs.evidence.outputs['" + name + "']"
                values[key] = result
                values[output] = str(reuse).lower()
            for key in sorted(values, key=len, reverse=True):
                expression = expression.replace(key, repr(values[key]))
            return eval(' '.join(expression.replace('&&', 'and').replace('||', 'or').split()), {'__builtins__': {}})
        self.assertTrue(allows(False, ['success'] * 3))
        self.assertTrue(allows(False, ['skipped'] * 3, reuse=True))
        self.assertFalse(allows(False, ['skipped'] * 3))
        self.assertTrue(allows(True, ['skipped'] * 3))
        for failure in ('failure', 'cancelled', 'timed_out', 'in_progress'):
            self.assertFalse(allows(False, [failure, 'success', 'success'], reuse=True))
            self.assertFalse(allows(True, [failure, 'skipped', 'skipped']))
        self.assertFalse(allows(True, ['skipped'] * 3, evidence='failure'))

    def test_workflow_keeps_strict_default_and_separate_bypass_gate(self):
        from pathlib import Path
        workflow = (Path(__file__).resolve().parents[1] / 'workflows/release.yml').read_text()
        for family in ('validate', 'mobile-build', 'mobile-runtime'):
            job = workflow.split('\n  ' + family + ':\n', 1)[1].split('    uses:', 1)[0]
            self.assertIn("outputs['hosted-skip'] != 'true'", job)
        package = workflow.split('\n  package:\n', 1)[1].split('\n  publish:', 1)[0]
        self.assertIn("needs.evidence.result == 'success'", package)
        self.assertIn("outputs['hosted-skip'] == 'true'", package)
        self.assertIn("outputs['hosted-skip'] != 'true'", package)
        self.assertIn("needs.validate.result == 'success'", package)
        self.assertIn('Package tagged source and pinned submodules', package)
        tooling = package.split('- name: Test release tooling', 1)[1]
        self.assertTrue(tooling.lstrip().startswith("if: needs.evidence.outputs['hosted-skip'] != 'true'"))
        self.assertIn('release-validation-policy.json', workflow)


class StandaloneSelectorTests(unittest.TestCase):
    def test_real_script_without_pythonpath_sdk_or_submodule_remains_dependency_free(self):
        import json
        import os
        from pathlib import Path
        import shutil
        import subprocess
        import sys
        from tempfile import TemporaryDirectory
        source = Path(__file__).resolve().parents[2]
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / '.github/scripts/select_release_evidence.py'
            script.parent.mkdir(parents=True)
            shutil.copy2(source / '.github/scripts/select_release_evidence.py', script)
            (root / 'logistics_build').mkdir()
            # No package __init__, SDK, commonUtils or third-party dependencies.
            for name in ('hosted_requirements.py', 'release_test_evidence.py'):
                shutil.copy2(source / 'logistics_build' / name, root / 'logistics_build' / name)
            environment = {key:value for key,value in os.environ.items() if key not in ('PYTHONPATH','PYTHONHOME')}
            environment.update(GITHUB_REPOSITORY='fixture/repo', GITHUB_SHA='a'*40,
                GITHUB_TOKEN='fixture-no-network', LOGISTICS_REUSE_TEST_RESULTS='off',
                GITHUB_REF='refs/heads/fixture', GITHUB_EVENT_NAME='workflow_dispatch',
                BUILD_MANAGER_HOSTED_VALIDATION='off',
                GITHUB_OUTPUT=str(root/'output'), GITHUB_STEP_SUMMARY=str(root/'summary'))
            result = subprocess.run([sys.executable, '-I', '-S', str(script)], cwd=root,
                env=environment, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((root/'release-evidence.json').read_text()), {})
            self.assertEqual((root/'output').read_text().splitlines(),
                ['hosted-skip=false','validate=false','mobile-build=false','mobile-runtime=false'])
