"""Service requests capture mappings; cancellation retains native worker ownership."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import Mock, patch

from commonUtils.runtime.operations import OperationCancelled
from features.rclone.mobile.service import native_service
from features.rclone.transfers.mobile.jobs import MirrorJobs
from features.rclone.transfers.mobile.models import TransferOutcome
from features.rclone.transfers.mobile.plan import NativeTransferRequest
from features.rclone.transfers.mobile.review_ui import _prepare
from features.rclone.transfers.mobile.execution import wait_for_transfer
from features.rclone.transfers.review import ReviewRequest
from features.rclone.transfers.service import TransferPlan, TransferService
from features.rclone.transfers.transfer_options import TransferOptions
from mobile_build.tests.support.mirror import MirrorClient


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
            self.assertEqual(service.execute(prepared), TransferOutcome('pull'))
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


class ReviewPresentationRaceTests(unittest.TestCase):
    def test_worker_completion_cannot_enable_full_approval_over_partial_details(self):
        from types import SimpleNamespace
        from features.rclone.transfers.review import ReviewSnapshot
        from features.rclone.transfers.mobile.review_ui import _display_review
        state = {'complete': False}
        def snapshot():
            captured = ReviewSnapshot((), state['complete'], 'synthetic')
            # Deterministically reproduce completion between the UI's snapshot
            # and approval-capability reads, rather than relying on thread speed.
            state['complete'] = True
            return captured
        session = SimpleNamespace(scan=SimpleNamespace(snapshot=snapshot), can_approve=lambda: state['complete'])
        snapshot, enabled = _display_review(session)
        self.assertFalse(snapshot.complete)
        self.assertFalse(enabled)
        snapshot, enabled = _display_review(session)
        self.assertTrue(snapshot.complete)
        self.assertTrue(enabled)


class MappingValidationTests(unittest.TestCase):
    def test_corrupted_mapping_invalidates_review_without_raising_from_poll(self):
        with TemporaryDirectory() as folder:
            store, client = MirrorJobs(Path(folder)), MirrorClient()
            job, _ = store.create(client, 'Remote', 'folder', storage='Local')
            prepared = native_service(client).transfers.review(
                NativeTransferRequest(store, job, False, False, TransferOptions(), client.generation))
            self.addCleanup(prepared.review.cancel)
            store.jobs[job['id']]['crypt'] = 'invalid'
            self.assertFalse(prepared.review.valid())
            self.assertIn(prepared.review.poll(), ('stopping', 'cancelled'))
            self.assertTrue(prepared.review.scan.retired.wait(2))

    def test_named_outcomes_reject_invalid_counts_and_direction_mismatches(self):
        for count in (True, -1, '3', None):
            with self.subTest(count=count), self.assertRaises(ValueError):
                TransferOutcome.from_result('push', count)
        with self.assertRaises(ValueError):
            TransferOutcome.from_result('push', TransferOutcome('pull'))
        with self.assertRaises(ValueError):
            TransferOutcome('push', files=True)


class ReviewDialogRetirementTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_presentation_retires_comparison_before_releasing_host(self):
        from features.rclone.transfers.mobile.review_ui import TransferReviewDialog
        from features.rclone.transfers.review import ReviewSession
        started, release = Event(), Event()
        def scanning(emit, cancelled):
            started.set()
            release.wait(3)
            return 'synthetic'
        session = ReviewSession(ReviewRequest('Pull', 'Remote:', 'Local', 'identity'), scanning)
        view = Mock()
        view.retained.return_value = True
        from types import SimpleNamespace
        view.app = SimpleNamespace(loop=asyncio.get_running_loop(), active_host=True,
            main_window=SimpleNamespace(size=SimpleNamespace(width=390)))
        view.show.side_effect = ValueError('view closed')
        view.close.side_effect = lambda: self.assertTrue(session.scan.retired.is_set())
        task = asyncio.create_task(TransferReviewDialog(view).run(session))
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            await asyncio.sleep(.02)
            self.assertFalse(task.done())
            self.assertTrue(session.scan.cancelled.is_set())
            task.cancel()
            await asyncio.sleep(.02)
            self.assertFalse(task.done())
        finally:
            release.set()
        with self.assertRaisesRegex(ValueError, 'view closed'):
            await task
        view.close.assert_called_once()

    async def test_confirmation_returning_after_close_cannot_rebind_cancellation(self):
        from features.rclone.transfers.mobile.review_ui import TransferReviewDialog
        from features.rclone.transfers.review import ReviewSession
        shown, confirming, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        session = ReviewSession(ReviewRequest('Pull', 'Remote:', 'Local', 'identity'), lambda *_: 'synthetic')
        self.assertTrue(await asyncio.to_thread(session.scan.retired.wait, 2))
        view = Mock()
        view.retained.return_value = True
        from types import SimpleNamespace
        view.app = SimpleNamespace(loop=asyncio.get_running_loop(), active_host=True,
            main_window=SimpleNamespace(size=SimpleNamespace(width=390)))
        controls = []
        confirmations = []
        def show(box, *args):
            controls.append(box)
            shown.set()
        async def confirm(*args, **kwargs):
            confirmations.append(args)
            confirming.set()
            await release.wait()
            return True
        view.show.side_effect = show
        view.confirm = confirm
        dialog = asyncio.create_task(TransferReviewDialog(view).run(session))
        choice = None
        try:
            await asyncio.wait_for(shown.wait(), 2)
            confirm_button = controls[0]
            choice = asyncio.ensure_future(confirm_button.approve_review())
            await asyncio.wait_for(confirming.wait(), 2)
            # Let the polling loop render while the destructive dialog is open.
            await asyncio.sleep(.12)
            self.assertFalse(confirm_button.review_ready)
            self.assertFalse(controls[0].model['can_early'])
            await asyncio.wait_for(confirm_button.approve_review(), 2)
            self.assertEqual(len(confirmations), 1)
            session.cancel()
            await asyncio.wait_for(dialog, 2)
            release.set()
            await asyncio.wait_for(choice, 2)
            view.scanning.assert_not_called()
            self.assertFalse(confirm_button.review_ready)
        finally:
            session.cancel()
            release.set()
            await asyncio.gather(dialog, *([choice] if choice is not None else []), return_exceptions=True)

    async def test_navigation_failure_still_releases_cancel_and_busy_fields(self):
        from types import SimpleNamespace
        from features.rclone.transfers.mobile.review_ui import MobileReviewPresentation
        owner = SimpleNamespace(app=object(), _transfer_review_view=object(), _cancel_transfer_review=Mock(),
            _transfer_cancel=Event(), transfer_busy=True, set_cloud_busy=Mock(), refresh_transfer_status=Mock(),
            routes=SimpleNamespace(screens={'files': [('transfer-review', object())]},
                                   trim=Mock(), render=Mock(side_effect=ValueError('view retired'))))
        with self.assertRaisesRegex(ValueError, 'view retired'):
            MobileReviewPresentation(owner).close()
        self.assertIsNone(owner._transfer_cancel)
        self.assertFalse(owner.transfer_busy)
        owner.set_cloud_busy.assert_called_once_with(False)


class ReviewProjectionTests(unittest.TestCase):
    def test_large_reviews_are_bounded_searchable_and_keep_cleanup_distinct(self):
        from features.rclone.transfers.presentation import ReviewProjection, PAGE_SIZE
        from features.rclone.transfers.review import ReviewSnapshot
        snapshot = ReviewSnapshot(tuple(('add', f'folder/{index:05}.txt') for index in range(10000)) +
            (('match', 'unchanged'), ('delete', 'old.txt'), ('cleanup', 'local/generated.tmp')), True, 'revision')
        view = ReviewProjection(ReviewRequest('Push', 'Local/Test', 'Cloud:', 'identity'))
        def render():
            return view.model(snapshot, state='ready', can_confirm=True, can_early=True)
        self.assertEqual(len(render()['rows']), PAGE_SIZE)
        view.select(step=1)
        self.assertEqual(render()['page'], 1)
        view.select(kind='delete', query='')
        self.assertEqual(render()['rows'], (('delete', 'old.txt'),))
        self.assertEqual(render()['counts']['add'], 10000)
        view.select(kind='cleanup', query='')
        self.assertEqual(render()['rows'], (('cleanup', 'local/generated.tmp'),))
        view.select(kind='all', query='FOLDER/09999')
        self.assertEqual(render()['rows'], (('add', 'folder/09999.txt'),))
        view.clear()
        self.assertIsNone(view.snapshot)


class TransferSurfaceTests(unittest.IsolatedAsyncioTestCase):
    def surface(self, visible=lambda: True):
        from types import SimpleNamespace
        from features.rclone.transfers.mobile.surface import TransferSurface
        host = SimpleNamespace(loop=asyncio.get_running_loop(), active_host=True,
            main_window=SimpleNamespace(size=SimpleNamespace(width=390)), cloud_client=None)
        from unittest.mock import AsyncMock
        handler = AsyncMock()
        surface = TransferSurface(host, handler, visible=visible)
        self.addCleanup(surface.dispose)
        return surface, handler

    async def test_identical_models_and_hidden_surfaces_do_not_schedule_native_redraws(self):
        surface, _ = self.surface(visible=lambda: False)
        surface.ready = True
        surface.update(dict(mode='progress', phase='transfer', files=2))
        revision = surface.revision
        for _ in range(10):
            surface.update(dict(mode='progress', phase='transfer', files=2))
        self.assertEqual(surface.revision, revision)
        self.assertIsNone(surface.send_task)
        self.assertIsNotNone(surface.pending)

    async def test_stale_approval_and_retired_callbacks_cannot_authorize_changes(self):
        surface, handler = self.surface(visible=lambda: False)
        surface.update(dict(mode='review', can_confirm=True))
        surface.delivered_revision = surface.revision
        await surface.dispatch('approve', dict(revision=str(surface.revision)))
        handler.assert_not_awaited()  # Not rendered yet.
        surface.pending = None
        await surface.dispatch('approve', dict(revision='0'))
        handler.assert_not_awaited()
        await surface.dispatch('approve', dict(revision=str(surface.revision)))
        handler.assert_awaited_once()
        surface.dispose()
        await surface.dispatch('approve', dict(revision=str(surface.revision)))
        self.assertEqual(handler.await_count, 1)
        self.assertEqual(surface.model, {})
        self.assertEqual(surface.token, '')

    async def test_approval_during_delivery_cannot_use_the_previous_review(self):
        surface, handler = self.surface()
        surface.update(dict(mode='review', can_confirm=True, destination='First:'))
        old = surface.delivered_revision = surface.revision
        surface.update(dict(mode='review', can_confirm=True, destination='Second:'))
        # flush has taken the new model, but the WebView still shows the old one.
        surface.pending = None
        await surface.dispatch('approve', dict(revision=str(old)))
        handler.assert_not_awaited()

    async def test_foreign_bridge_urls_and_oversized_queries_are_rejected(self):
        surface, handler = self.surface()
        self.assertFalse(surface.navigate(surface.web, 'https://example.com/approve'))
        self.assertFalse(surface.navigate(surface.web, 'logistics-transfer://other/approve'))
        self.assertFalse(surface.navigate(surface.web, surface.bridge + 'approve?' + '&'.join(f'k{i}=x' for i in range(20))))
        await asyncio.sleep(0)
        handler.assert_not_awaited()

    async def test_revocation_disposes_private_content_and_redacts_retained_progress(self):
        from features.rclone.transfers.mobile.execution import TransferState
        from features.rclone.transfers.presentation import progress_model
        from types import SimpleNamespace
        surface, _ = self.surface()
        state = TransferState(endpoints=('Local/private-name', 'Secret:'), metrics=dict(active_files=[dict(name='private-name')]))
        surface.host._transfer_controller = SimpleNamespace(state=state)
        surface.revoke()
        self.assertTrue(surface.closed)
        self.assertTrue(state.display_revoked)
        self.assertNotIn('private-name', str(progress_model(state)))
