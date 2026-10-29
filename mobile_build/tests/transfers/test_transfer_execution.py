"""Writer admission, captured connection lifetime and terminal outcomes without UI."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from features.rclone.transfers.mobile.execution import TransferExecution, TransferState


class TransferExecutionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = SimpleNamespace(generation=1, cancel=Mock())
        self.view = Mock()
        self.view.ready = AsyncMock(return_value=True)
        self.view.connection.return_value = self.client, 1
        self.view.current.side_effect = lambda client, generation: client.generation == generation
        self.state = TransferState()
        self.execution = TransferExecution(self.state, self.view)

    async def test_success_retires_progress_before_publishing_completion(self):
        self.view.finished.side_effect = lambda: self.assertFalse(self.state.busy)
        self.assertTrue(await self.execution.run(lambda *_: ('complete', 3), 'pull', source='Cloud:', destination='Local'))
        self.assertEqual(self.state.endpoints, ('Cloud:', 'Local'))
        self.assertTrue(self.state.complete)
        self.assertIsNone(self.state.cancel)
        self.assertEqual(self.state.epoch, 2)
        self.assertTrue(self.state.message.startswith('100%'))
        self.view.finished.assert_called_once_with()

    async def test_two_requests_waiting_for_restore_admit_only_one_writer(self):
        ready = asyncio.Event()
        async def restore():
            await ready.wait()
            return True
        self.view.ready.side_effect = restore
        started, release = Event(), Event()
        def work(*args):
            started.set()
            if not release.wait(5):
                raise RuntimeError('worker not released')
            return 1
        first = asyncio.create_task(self.execution.run(work, 'push'))
        second = asyncio.create_task(self.execution.run(work, 'push'))
        await asyncio.sleep(0)
        ready.set()
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 5))
            self.assertFalse(await second)
            self.view.started.assert_called_once_with()
        finally:
            release.set()
            await asyncio.gather(first, second)

    async def test_changed_credentials_cannot_publish_success(self):
        def work(*args):
            self.client.generation += 1
            return 4
        self.assertFalse(await self.execution.run(work, 'push'))
        self.assertFalse(self.state.complete)
        self.assertIn('connection changed', self.state.message)

    async def test_malformed_result_is_failure_even_after_successful_worker_return(self):
        self.assertFalse(await self.execution.run(lambda *_: ('invalid',), 'pull'))
        self.assertFalse(self.state.complete)
        self.assertFalse(self.state.busy)
        self.assertIn('Sync stopped', self.state.message)

    async def test_caller_cancellation_waits_for_native_writer_retirement(self):
        started, release = Event(), Event()
        def work(client, cancelled, progress):
            started.set()
            if not release.wait(5):
                raise RuntimeError('worker not released')
            self.assertTrue(cancelled())
            return 1
        task = asyncio.create_task(self.execution.run(work, 'push'))
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 5))
            task.cancel()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.assertTrue(self.state.busy)
            self.assertFalse(task.done())
            self.view.finished.assert_not_called()
        finally:
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertFalse(self.state.busy)
        self.assertFalse(self.state.complete)
        self.view.finished.assert_called_once_with()

    async def test_failed_presentation_releases_admission_for_retry(self):
        self.view.started.side_effect = ValueError('view retired')
        work = Mock()
        self.assertFalse(await self.execution.run(work, 'push'))
        self.assertFalse(self.state.busy)
        work.assert_not_called()
        self.view.started.side_effect = None
        self.assertTrue(await self.execution.run(lambda *_: 1, 'push'))

    async def test_conflicted_legacy_and_named_results_do_not_publish_verified_completion(self):
        from features.rclone.transfers.mobile.models import TransferOutcome
        for result in (('conflict', None), TransferOutcome('pull', status='conflict')):
            with self.subTest(result=result):
                self.assertFalse(await self.execution.run(lambda *_: result, 'pull'))
                self.assertFalse(self.state.complete)
                self.assertFalse(self.state.busy)
                self.assertIn('Files changed', self.state.message)
                self.assertNotIn('100%', self.state.message)

    async def test_completion_formatting_failure_does_not_leave_success_state(self):
        from unittest.mock import patch
        self.view.finished.side_effect = lambda: self.assertFalse(self.state.complete)
        with patch('features.rclone.transfers.mobile.execution.completion_message',
                   side_effect=ValueError('completion display failed')):
            self.assertFalse(await self.execution.run(lambda *_: 1, 'push'))
        self.assertFalse(self.state.complete)
        self.assertIn('Sync stopped', self.state.message)


class MirrorCopyAdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_open_releases_unpublished_provider(self):
        from pathlib import Path
        from unittest.mock import patch
        from features.rclone.transfers.mobile.ui import MirrorUI
        client = SimpleNamespace(generation=1)
        provider = Mock()
        def open_provider(location):
            client.generation = 2
            return provider
        service = SimpleNamespace(localcrypt=SimpleNamespace(open=open_provider))
        store = SimpleNamespace(jobs={'copy': dict(crypt=True, remote='Secret', identity='a' * 64)})
        owner = SimpleNamespace(rclone_ui=SimpleNamespace(local_read_available=Mock()), cloud_busy=False,
            mirror_store=lambda: store, show_local_location=AsyncMock(), cloud_client=client,
            navigation_generation=1, active_host=True, private_root=Path('/synthetic'),
            file_roots={}, browser_file_location=AsyncMock(), update_file_locations=Mock())
        with patch('features.rclone.transfers.mobile.jobs.remote_location', return_value=(None, 'books')), \
             patch('features.rclone.mobile.service.native_service', return_value=service):
            self.assertFalse(await MirrorUI.open_mirror_copy(owner, 'copy'))
        provider.close.assert_called_once_with()
        self.assertEqual(owner.file_roots, {})
        owner.browser_file_location.assert_not_called()
