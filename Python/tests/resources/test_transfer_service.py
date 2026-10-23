"""Approval binds execution to one plan, generation, options and runtime."""
from dataclasses import replace
from threading import Barrier, Event, Thread
import unittest

from commonUtils.runtime.operations import OperationCancelled
from features.rclone.transfers.review import ReviewRequest
from features.rclone.transfers.service import TransferContext, TransferPlan, TransferService
from features.rclone.transfers.transfer_options import TransferOptions


class TransferServiceTests(unittest.TestCase):
    def prepare(self, *, execute=None, valid=lambda: True):
        service = TransferService()
        request = ReviewRequest('Push', '/local', 'Remote:', 'fixture',
                                TransferOptions(bw_limit=3, excludes=('*.tmp',)))
        plan = TransferPlan(request, lambda emit, cancelled: 'revision', valid,
                            execute or (lambda request, context: request.options))
        return service, service.prepare(plan)

    def approve(self, prepared):
        review = prepared.review
        self.assertTrue(review.scan.retired.wait(2))
        self.assertTrue(review.approve())
        self.assertTrue(review.scan.retired.wait(2))
        self.assertTrue(review.approved)

    def test_only_the_service_that_prepared_the_plan_can_execute_it(self):
        service, prepared = self.prepare()
        self.approve(prepared)
        for foreign in (True, None, object()):
            with self.subTest(foreign=foreign), self.assertRaisesRegex(ValueError, 'another runtime'):
                service.execute(foreign)
        with self.assertRaisesRegex(ValueError, 'another runtime'):
            TransferService().execute(prepared)
        self.assertIs(service.execute(prepared), prepared.request.options)
        with self.assertRaisesRegex(ValueError, 'already used'):
            service.execute(prepared)

    def test_mutating_the_review_cannot_change_captured_destination_or_options(self):
        calls = []
        service, prepared = self.prepare(execute=lambda *args: calls.append(args))
        self.approve(prepared)
        prepared.review.request = replace(prepared.request, destination='Other:', options=TransferOptions())
        with self.assertRaisesRegex(ValueError, 'review changed'):
            service.execute(prepared)
        self.assertEqual(calls, [])

    def test_credential_revocation_after_approval_prevents_preflight_and_execution(self):
        active, calls = [True], []
        service, prepared = self.prepare(valid=lambda: active[0], execute=lambda *args: calls.append(args))
        self.approve(prepared)
        active[0] = False
        with self.assertRaisesRegex(ValueError, 'Connection or review changed'):
            service.execute(prepared)
        self.assertEqual(calls, [])

    def test_incomplete_approval_waits_for_scanner_retirement(self):
        finish, calls = Event(), []
        def scanner(emit, cancelled):
            finish.wait(2)
            return 'revision'
        service = TransferService()
        request = ReviewRequest('Pull', 'Remote:', '/local', 'fixture')
        prepared = service.prepare(TransferPlan(request, scanner, lambda: True,
                                               lambda *args: calls.append(args)))
        try:
            self.assertTrue(prepared.review.approve(incomplete=True))
            with self.assertRaises(ValueError):
                service.execute(prepared)
            self.assertEqual(calls, [])
        finally:
            finish.set()
            self.assertTrue(prepared.review.scan.retired.wait(2))
        service.execute(prepared)
        self.assertEqual(len(calls), 1)

    def test_failed_preflight_or_cancellation_consumes_approval(self):
        def fail(*args):
            raise OSError('fixture preflight refused')
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                service, prepared = self.prepare(execute=fail)
                self.approve(prepared)
                error = OperationCancelled if cancelled else OSError
                with self.assertRaises(error):
                    service.execute(prepared, TransferContext(cancelled=lambda: cancelled))
                with self.assertRaisesRegex(ValueError, 'already used'):
                    service.execute(prepared)

    def test_simultaneous_execution_attempts_start_one_job(self):
        barrier, calls, failures = Barrier(2), [], []
        service, prepared = self.prepare(execute=lambda *args: calls.append(args))
        self.approve(prepared)
        def run():
            barrier.wait(2)
            try:
                service.execute(prepared)
            except ValueError as error:
                failures.append(str(error))
        workers = [Thread(target=run) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(3)
            self.assertFalse(worker.is_alive())
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(failures), 1)
