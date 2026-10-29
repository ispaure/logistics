"""Native transport retries preserve evidence and refuse unreconciled work."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from logistics_build.guest_attempts import result_attempt


class GuestAttemptTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'results'
        self.source = {'logistics_commit': 'fixed', 'commonUtils_commit': 'shared'}
        self.backend = 'Parallels Windows'

    def finish(self, directory, *, status='failed', removed=True):
        directory.mkdir()
        report = dict(schema=1, source=self.source, backend=self.backend, status=status,
                      test_workspace_removed=removed, seconds=37, phases=[{'id':'suite','status':status}])
        (directory / 'result.json').write_text(json.dumps(report))
        return report

    def test_retry_allocates_fresh_path_and_preserves_original_report_and_artifacts(self):
        with result_attempt(self.root, self.source, self.backend) as first:
            self.assertFalse(first.exists()); self.finish(first)
            (first / 'suite.log').write_text('original failure evidence')
        original = (self.root / 'result.json').read_bytes()
        with result_attempt(self.root, self.source, self.backend) as second:
            self.assertNotEqual(first, second); self.assertFalse(second.exists())
            self.finish(second, status='passed')
        self.assertEqual((first / 'suite.log').read_text(), 'original failure evidence')
        retained = list((self.root / 'attempts').glob('retained-*.json'))
        self.assertEqual(len(retained), 1); self.assertEqual(retained[0].read_bytes(), original)
        result = json.loads((self.root / 'result.json').read_text())
        self.assertEqual(result['status'], 'passed'); self.assertEqual(result['attempt_directory'], str(second))

    def test_original_completed_backend_directory_can_be_retained_without_deletion(self):
        self.root.mkdir(); old = self.finish(self.root / 'unused')
        (self.root / 'result.json').write_text(json.dumps(old))
        with result_attempt(self.root, self.source, self.backend) as attempt:
            self.finish(attempt, status='passed')
        self.assertTrue((self.root / 'unused/result.json').is_file())
        self.assertEqual(len(list((self.root/'attempts').glob('retained-*.json'))), 1)

    def test_running_or_uncleaned_guest_cannot_be_replayed(self):
        for status, removed in [('running', True), ('failed', False), ('unknown', True)]:
            with self.subTest(status=status, removed=removed), TemporaryDirectory() as tmp:
                root = Path(tmp)/'results'
                with result_attempt(root, self.source, self.backend) as attempt:
                    self.finish(attempt, status=status, removed=removed)
                before = (root/'result.json').read_bytes()
                with self.assertRaisesRegex(ValueError, 'reconciliation'):
                    with result_attempt(root, self.source, self.backend): self.fail('unsafe replay')
                self.assertEqual((root/'result.json').read_bytes(), before)

    def test_changed_source_and_backend_are_rejected(self):
        with result_attempt(self.root, self.source, self.backend) as attempt:self.finish(attempt)
        for source, backend in [({'logistics_commit':'changed'},self.backend),(self.source,'Other backend')]:
            with self.assertRaisesRegex(ValueError,'source/backend'):
                with result_attempt(self.root,source,backend):self.fail('mismatched retry')

    def test_both_backend_entry_points_publish_new_attempts_without_mutating_request(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from logistics_build import windows_backend, vm_backend
        for module, backend in [(windows_backend, 'Parallels Windows'), (vm_backend, 'Parallels fedora')]:
            with self.subTest(backend=backend), TemporaryDirectory() as tmp:
                self.backend = backend
                directory = Path(tmp)/'results'
                request = SimpleNamespace(results=directory, source_identity=self.source, distribution='fedora')
                seen = []
                def execute(attempt):
                    self.assertIsNot(attempt, request)
                    self.assertFalse(attempt.results.exists())
                    seen.append(attempt.results)
                    self.finish(attempt.results, status='passed')
                    return 0
                with patch.object(module, '_run_attempt', side_effect=execute):
                    self.assertEqual(module.run(request), 0)
                    self.assertEqual(module.run(request), 0)
                self.assertEqual(request.results, directory)
                self.assertEqual(len(set(seen)), 2)
                self.assertTrue(all((path/'result.json').is_file() for path in seen))
                self.assertEqual(json.loads((directory/'result.json').read_text())['status'], 'passed')

    def test_incomplete_setup_remains_blocked_for_reconciliation(self):
        with self.assertRaises(RuntimeError):
            with result_attempt(self.root,self.source,self.backend):raise RuntimeError('setup interrupted')
        with self.assertRaisesRegex(ValueError,'reconciliation'):
            with result_attempt(self.root,self.source,self.backend):self.fail('unknown setup replay')


    def failed_setup(self):
        with self.assertRaises(RuntimeError):
            with result_attempt(self.root, self.source, self.backend) as attempt:
                attempt.mkdir()
                (attempt/'prepared.json').write_text(json.dumps(dict(
                    status='failed', tests_run=False, token='a'*32, vm='owned-vm')))
                raise RuntimeError('no interactive session')
        return attempt

    def test_absent_workspace_receipt_allows_new_attempt_without_rewriting_failure(self):
        from logistics_build.guest_attempts import reconcile_setup
        attempt = self.failed_setup()
        before = (self.root/'result.json').read_bytes()
        preparation = (attempt/'prepared.json').read_bytes()
        calls = []
        def inspect(vm, token):
            calls.append((vm, token))
            return dict(vm=vm, token=token, exists=False)
        receipt = reconcile_setup(self.root, inspect)
        self.assertEqual(reconcile_setup(self.root, inspect), receipt)
        self.assertEqual(len(calls), 1)
        self.assertEqual((self.root/'result.json').read_bytes(), before)
        self.assertEqual((attempt/'prepared.json').read_bytes(), preparation)
        with result_attempt(self.root, self.source, self.backend) as retry:
            self.assertNotEqual(attempt, retry)
            self.finish(retry, status='passed')
        self.assertEqual(next((self.root/'attempts').glob('retained-*.json')).read_bytes(), before)
        self.assertTrue(receipt.is_file())

    def test_present_or_foreign_namespace_never_authorizes_retry(self):
        from logistics_build.guest_attempts import reconcile_setup
        self.failed_setup()
        before = (self.root/'result.json').read_bytes()
        for proof in (dict(vm='owned-vm', token='a'*32, exists=True),
                      dict(vm='foreign-vm', token='a'*32, exists=False),
                      dict(vm='owned-vm', token='b'*32, exists=False)):
            with self.subTest(proof=proof), self.assertRaises(ValueError):
                reconcile_setup(self.root, lambda *_: proof)
        self.assertEqual((self.root/'result.json').read_bytes(), before)
        self.assertEqual(list(self.root.rglob('setup-reconciliation.json')), [])

    def test_changed_preparation_invalidates_prior_reconciliation(self):
        from logistics_build.guest_attempts import reconcile_setup
        attempt = self.failed_setup()
        reconcile_setup(self.root, lambda vm, token: dict(vm=vm, token=token, exists=False))
        data=json.loads((attempt/'prepared.json').read_text());data['error']='changed'
        (attempt/'prepared.json').write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'reconciliation'):
            with result_attempt(self.root, self.source, self.backend):
                self.fail('changed evidence was replayed')

    def test_non_setup_failure_cannot_be_reconciled_as_absent(self):
        from logistics_build.guest_attempts import reconcile_setup
        attempt = self.failed_setup()
        data=json.loads((attempt/'prepared.json').read_text());data['tests_run']=True
        (attempt/'prepared.json').write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'pre-test'):
            reconcile_setup(self.root, lambda *_: self.fail('inspection must not run'))


if __name__ == '__main__':unittest.main()
