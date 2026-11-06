"""Deletion phase retries, cancellation ownership and stale native decisions."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from threading import Event
import unittest
from unittest.mock import AsyncMock, patch

from mobile_build.tests.support.notebooks import create_notebook, create_storage_notebook_app
from features.notebooks.notebook import Notebook, MAX_ARCHIVE
from features.notebooks.storage import NotebookDocument
from services.documents.mobile_notebooks import open_notebook, retarget_notebook
from services.documents.storage import local_document_resource


class NotebookDeleteReviewTests(unittest.TestCase):
    def setUp(self):
        self.app, self.client, self.provider = create_storage_notebook_app(self)

    def test_completed_phases_are_not_repeated_after_history_failure(self):
        panel = create_notebook(self, private=False)
        document = panel.document
        physical = document.resource.provider._physical(document.resource.path)
        recovery = document.recovery.root / document.key
        with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='delete')):
            with patch.object(self.app.recent_documents, 'forget', side_effect=OSError('history unavailable')):
                with self.assertRaises(OSError):
                    self.app.loop.run_until_complete(panel.delete_document())
            self.assertTrue(document.source_deleted and document.recovery_deleted)
            recovery.mkdir()
            sentinel = recovery / 'replacement'
            sentinel.write_bytes(b'new owner')
            physical.write_bytes(b'new file')
            self.assertTrue(self.app.loop.run_until_complete(panel.delete_document()))
        self.assertEqual(physical.read_bytes(), b'new file')
        self.assertEqual(sentinel.read_bytes(), b'new owner')

    def test_deleted_draft_is_readonly_but_can_retry_delete_or_save_as(self):
        self.assertTrue(self.app.loop.run_until_complete(open_notebook(self.app)))
        panel = self.app.notebook_panel
        document = panel.document
        with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='delete')), \
                patch.object(self.app.recent_documents, 'forget', side_effect=OSError('history unavailable')):
            with self.assertRaises(OSError):
                self.app.loop.run_until_complete(panel.delete_document())
        self.assertFalse(document.source_deleted)
        self.assertTrue(document.recovery_deleted)
        self.assertTrue(panel.state()['read_only'])
        self.assertTrue(panel.state()['can_delete'])
        self.assertIn('Deleted', panel.state()['save_status'])
        title = document.book.name
        with self.assertRaisesRegex(ValueError, 'deleted'):
            document.save()
        with self.assertRaisesRegex(ValueError, 'deleted'):
            panel.editor.apply({'op': 'rename', 'name': 'Must roll back'})
        self.assertEqual(document.book.name, title)
        self.assertFalse((document.recovery.root / document.key).exists())
        target = self.app.storage_root / 'Saved As.rmdoc'
        target.write_bytes(document.book.to_bytes())
        resource = local_document_resource(target, max_bytes=MAX_ARCHIVE)
        self.assertTrue(self.app.loop.run_until_complete(retarget_notebook(self.app, panel, resource)))
        panel.editor.apply({'op': 'rename', 'name': 'New saved document'})
        panel.document.save()
        self.assertEqual(Notebook.read(target.read_bytes()).name, 'New saved document')
        self.assertFalse(panel.document.deletion_started)

    def test_false_or_failed_close_restores_routing_intent_and_allows_retry(self):
        for close_error in (False, OSError('workspace busy')):
            panel = create_notebook(self, private=False)
            key = panel.session.id
            previous_return = ('folders', 'old-route', True)
            self.app.__dict__.setdefault('_reader_returns', {})[key] = previous_return
            self.app.__dict__.setdefault('_reader_closing', set()).discard(key)
            with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='delete')):
                options = {'side_effect': close_error} if isinstance(close_error, Exception) else {'return_value': False}
                with patch.object(self.app, 'close_session', **options):
                    with self.assertRaisesRegex(OSError, 'data was deleted'):
                        self.app.loop.run_until_complete(panel.delete_document())
                self.assertEqual(self.app._reader_returns[key], previous_return)
                self.assertNotIn(key, self.app._reader_closing)
                self.assertFalse(panel.busy or panel.closed)
                self.assertTrue(self.app.loop.run_until_complete(panel.delete_document()))

    def test_moved_resource_during_confirmation_requires_a_new_decision(self):
        panel = create_notebook(self, private=False)
        resource = panel.document.resource
        async def move(dialog):
            resource.provider.rename(resource.path, 'Moved.rmdoc')
            resource.path = 'Moved.rmdoc'
            resource.revision = resource.provider.entry(resource.path)['revision']
            return 'delete'
        with patch.object(self.app.main_window, 'dialog', side_effect=move):
            self.assertFalse(self.app.loop.run_until_complete(panel.delete_document()))
        self.assertTrue(resource.check())
        self.assertFalse(panel.document.deletion_started)

    def test_replaced_canvas_does_not_inherit_the_old_busy_state(self):
        panel = create_notebook(self, private=False)
        original = panel.document
        self.addCleanup(original.close)
        replacement = NotebookDocument(Notebook.new('Replacement'), recovery=original.recovery)
        async def replace(dialog):
            panel.open_resource(replacement)
            return 'delete'
        with patch.object(self.app.main_window, 'dialog', side_effect=replace):
            self.app.loop.run_until_complete(panel.perform({'op': 'delete-file'}))
        self.assertIs(panel.document, replacement)
        self.assertFalse(panel.busy)
        self.assertTrue(original.resource.check())
        panel.editor.apply({'op': 'rename', 'name': 'Still usable'})
        self.assertEqual(replacement.book.name, 'Still usable')

    def test_cancelled_dialog_releases_reservation_without_touching_storage(self):
        panel = create_notebook(self, private=False)
        entered = asyncio.Event()
        async def dialog(value):
            entered.set()
            await asyncio.Future()
        async def exercise():
            with patch.object(self.app.main_window, 'dialog', side_effect=dialog):
                task = asyncio.create_task(panel.delete_document())
                await asyncio.wait_for(entered.wait(), 5)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        self.app.loop.run_until_complete(exercise())
        self.assertFalse(panel.busy or panel._delete_pending)
        self.assertTrue(panel.document.resource.check())
        self.assertFalse(panel.document.deletion_started)

    def test_cancelled_worker_keeps_reservation_until_settled_then_allows_retry(self):
        panel = create_notebook(self, private=False)
        document = panel.document
        entered, release = Event(), Event()
        original = document.delete
        def delayed():
            entered.set()
            if not release.wait(5):
                raise TimeoutError('Test worker was not released')
            original()
        async def exercise():
            with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='delete')), \
                    patch.object(document, 'delete', side_effect=delayed):
                task = asyncio.create_task(panel.delete_document())
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                    task.cancel()
                    await asyncio.sleep(0)
                    self.assertFalse(task.done())
                    self.assertTrue(panel.busy and panel._delete_pending)
                    self.assertFalse(await panel.delete_document())
                    # A second cancellation must not drop the worker ownership.
                    task.cancel()
                    await asyncio.sleep(0)
                    self.assertFalse(task.done())
                finally:
                    release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            self.assertTrue(document.source_deleted and document.recovery_deleted)
            self.assertFalse(panel.busy or panel._delete_pending or panel.closed)
            with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='delete')):
                self.assertTrue(await panel.delete_document())
        self.app.loop.run_until_complete(asyncio.wait_for(exercise(), 10))

    def test_cancelled_canvas_action_acknowledges_worker_failure_and_can_retry(self):
        panel = create_notebook(self, private=False)
        document = panel.document
        entered, release = Event(), Event()
        def delayed_failure():
            entered.set()
            if not release.wait(5):
                raise TimeoutError('Test worker was not released')
            raise OSError('source delete failed')
        async def exercise():
            with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='delete')), \
                    patch.object(document, 'delete', side_effect=delayed_failure):
                task = asyncio.create_task(panel.perform({'op': 'delete-file'}))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                    task.cancel()
                    await asyncio.sleep(0)
                    self.assertTrue(panel.busy)
                finally:
                    release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            self.assertFalse(panel.busy or panel._delete_pending)
            self.assertFalse(document.deletion_started)
            self.assertTrue(document.resource.check())
            self.assertIn('Deletion interrupted', panel.web.evaluate_javascript.call_args.args[0])
            with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='delete')):
                self.assertTrue(await panel.delete_document())
        self.app.loop.run_until_complete(asyncio.wait_for(exercise(), 10))
