"""Service requests capture mappings; cancellation retains native worker ownership."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import Mock, patch

from commonUtils.runtime.operations import OperationCancelled
from features.rclone.mobile.service import native_service
from features.rclone.transfers.mobile.jobs import MirrorJobs
from features.rclone.transfers.mobile.plan import NativeTransferRequest
from features.rclone.transfers.mobile.review_ui import _prepare
from features.rclone.transfers.mobile.execution import wait_for_transfer
from features.rclone.transfers.review import ReviewRequest
from features.rclone.transfers.service import TransferPlan, TransferService
from features.rclone.transfers.transfer_options import TransferOptions
from mobile_build.tests.transfers.test_mirror_jobs import MirrorClient


class NativeTransferTests(unittest.TestCase):
    def approve(self, prepared):
        self.assertTrue(prepared.review.scan.retired.wait(2))
        self.assertTrue(prepared.review.approve())
        self.assertTrue(prepared.review.scan.retired.wait(2))
        self.assertTrue(prepared.review.approved)

    def test_service_pull_survives_its_own_record_publication(self):
        with TemporaryDirectory() as folder:
            store, client = MirrorJobs(Path(folder)), MirrorClient()
            job = store.prepare_review(client, 'Remote', 'folder', storage='Local')
            transfer = NativeTransferRequest(store, job, False, True, TransferOptions(), client.generation)
            job['target'] = 'Other'  # A caller's mutable proposal cannot redirect it.
            service = native_service(client).transfers
            prepared = service.review(transfer)
            self.approve(prepared)
            self.assertEqual(service.execute(prepared), ('updated', None))
            self.assertEqual((store.target(dict(transfer.job)) / 'note.txt').read_bytes(), b'first')
            self.assertFalse((Path(folder) / 'LocalFiles' / 'Other').exists())

    def test_changed_generation_refuses_review_before_starting_scanner(self):
        with TemporaryDirectory() as folder:
            store, client = MirrorJobs(Path(folder)), MirrorClient()
            job = store.prepare_review(client, 'Remote', 'folder', storage='Local')
            transfer = NativeTransferRequest(store, job, False, True, TransferOptions(), client.generation)
            client.generation += 1
            with patch('features.rclone.transfers.mobile.plan.native_scanner') as scanner:
                with self.assertRaisesRegex(ValueError, 'Credentials changed'):
                    native_service(client).transfers.review(transfer)
                scanner.assert_not_called()

    def test_storage_relocation_after_confirmation_refuses_execution(self):
        with TemporaryDirectory() as folder:
            store, client = MirrorJobs(Path(folder)), MirrorClient()
            job = store.prepare_review(client, 'Remote', 'folder', storage='Local')
            service = native_service(client).transfers
            prepared = service.review(NativeTransferRequest(store, job, False, True, TransferOptions(), client.generation))
            self.approve(prepared)
            with patch.object(store, 'target', return_value=Path(folder) / 'LocalFiles' / 'Other'), patch.object(
                    store, 'execute_review') as execute:
                with self.assertRaises(ValueError):
                    service.execute(prepared)
                execute.assert_not_called()

    def test_late_generation_change_is_carried_into_engine_cancellation(self):
        with TemporaryDirectory() as folder:
            store, client = MirrorJobs(Path(folder)), MirrorClient()
            job = store.prepare_review(client, 'Remote', 'folder', storage='Local')
            service = native_service(client).transfers
            prepared = service.review(NativeTransferRequest(store, job, False, True, TransferOptions(), client.generation))
            self.approve(prepared)
            def executing(*args, cancelled, **kwargs):
                self.assertFalse(cancelled())
                client.generation += 1
                self.assertTrue(cancelled())
                raise OperationCancelled()
            with patch.object(store, 'execute_review', side_effect=executing):
                with self.assertRaises(OperationCancelled):
                    service.execute(prepared)


class TransferCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_caller_cancellation_waits_for_the_writer_even_if_cancelled_again(self):
        started, release, stopping = Event(), Event(), Event()
        def writing():
            started.set()
            if not release.wait(5):
                raise TimeoutError('Fixture was not released')
            raise OSError('Late write failure')
        client = Mock()
        worker = asyncio.create_task(asyncio.to_thread(writing))
        caller = asyncio.create_task(wait_for_transfer(worker, stopping, client))
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            caller.cancel()
            await asyncio.sleep(.02)
            self.assertTrue(stopping.is_set())
            self.assertFalse(caller.done())
            caller.cancel()
            await asyncio.sleep(.02)
            self.assertFalse(caller.done())
        finally:
            release.set()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        self.assertTrue(worker.done())
        client.cancel.assert_called_once()

    async def test_cancelled_preparation_retires_a_late_comparison(self):
        started, release, retired = Event(), Event(), Event()
        def scan(emit, cancelled):
            while not cancelled():
                Event().wait(.01)
            retired.set()
            return ''
        def plan(value):
            started.set()
            if not release.wait(5):
                raise TimeoutError('Fixture was not released')
            return TransferPlan(ReviewRequest('Pull', 'Remote:', '/local', 'fixture'), scan,
                                lambda: True, lambda *args: None)
        service = TransferService(plan)
        task = asyncio.create_task(_prepare(service, object()))
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            task.cancel()
            await asyncio.sleep(.02)
            self.assertFalse(task.done())
        finally:
            release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(retired.is_set())
