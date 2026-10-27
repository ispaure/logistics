"""Only complete, fresh, exact-commit trusted workflow coverage can be reused."""
from copy import deepcopy
from datetime import datetime, timezone
import unittest
from select_release_evidence import select, REQUIRED


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


    def test_debug_off_forces_fresh_without_consulting_previous_hosted_passes(self):
        from unittest.mock import Mock
        request = Mock(side_effect=AssertionError('Fresh debug policy must not reuse prior runs'))
        self.assertEqual(select(request, 'fixture/repo', self.sha, now=self.now, reuse_allowed=False), {})
        request.assert_not_called()
