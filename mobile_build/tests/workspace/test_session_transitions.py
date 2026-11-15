"""Explicit close preparation/results preserve vetoes and stale-session guards."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4
from mobile.workspace import Workspace
from mobile.session_workflows.transitions import SessionTransitions


class SessionTransitionTests(unittest.TestCase):
    def test_cancel_missing_and_stale_decisions_cannot_commit(self):
        with TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory).resolve())
            session = workspace.open('managed-text', uuid4().hex, 'text')
            owner = SessionTransitions(SimpleNamespace(workspace=workspace, text_views={}))
            self.assertEqual(owner.close('missing').reason, 'missing')
            self.assertEqual(owner.close(session.id, choice='cancel').reason, 'cancelled')
            decision = owner.prepare(session.id)
            workspace.invalidate(session.id)
            self.assertEqual(owner.commit(decision).reason, 'stale')
            self.assertIn(session.id, workspace.sessions)
            with self.assertRaises(ValueError):
                owner.prepare(session.id, choice='invalid')


class PendingCloseTests(unittest.IsolatedAsyncioTestCase):
    async def test_obsolete_dialog_answer_cannot_save_or_discard_invalidated_session(self):
        for choice in ('save', 'discard'):
            with self.subTest(choice=choice), TemporaryDirectory() as directory:
                workspace = Workspace(Path(directory).resolve())
                session = workspace.open('managed-text', uuid4().hex, 'text')
                answer = asyncio.get_running_loop().create_future()
                async def dialog(value):
                    return await answer
                host = SimpleNamespace(workspace=workspace, active_host=True,
                    loop=asyncio.get_running_loop(), main_window=SimpleNamespace(dialog=dialog))
                transitions = SessionTransitions(host)
                save, discard = Mock(), Mock()
                with patch('services.documents.authoring.document_dialogs.DocumentDialog'):
                    transitions.document_close_dialog(session.id, 'Synthetic', save, discard)
                    task = host._document_close_tasks[session.id]
                    await asyncio.sleep(0)
                    workspace.invalidate(session.id)
                    answer.set_result(choice)
                    await task
                save.assert_not_called()
                discard.assert_not_called()
                self.assertFalse(host._document_close_tasks)

    async def test_failed_book_progress_releases_exit_for_retry(self):
        with TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory).resolve())
            session = workspace.open('library', uuid4().hex, 'epub')
            release_flush = asyncio.Event()
            progress = SimpleNamespace(pending=object(), flush=release_flush.wait)
            book = SimpleNamespace(book_busy=False, _book_progress=progress,
                                   request_position_flush=Mock(return_value=object()))
            host = SimpleNamespace(workspace=workspace, active_host=True, loop=asyncio.get_running_loop(),
                                   readers=SimpleNamespace(controllers={session.id: book}),
                                   request_close_session=Mock())
            transitions = SessionTransitions(host)

            self.assertTrue(transitions.request_reader_close(session.id))
            first_exit = book._exit_task
            self.assertTrue(transitions.request_reader_close(session.id))
            self.assertIs(book._exit_task, first_exit)
            book.request_position_flush.assert_called_once_with()
            release_flush.set()
            await first_exit

            host.request_close_session.assert_not_called()
            self.assertNotIn(session.id, host._reader_closing)
            self.assertIsNone(book._exit_task)

            progress.pending = None
            self.assertTrue(transitions.request_reader_close(session.id))
            await book._exit_task
            host.request_close_session.assert_called_once_with(session.id)

    async def test_provider_worker_finishing_after_invalidation_cannot_continue_close(self):
        with TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory).resolve())
            session = workspace.open('provider-session', 'fixture', 'pdf', transient=True)
            loop = asyncio.get_running_loop()
            worker = loop.create_future()
            progress = SimpleNamespace(worker=worker, task=worker)
            private = SimpleNamespace(operation_busy=False, _provider_progress=progress)
            providers = SimpleNamespace(controllers={session.id: private})
            host = SimpleNamespace(workspace=workspace, active_host=True, loop=loop,
                                   provider_sessions=lambda: providers, request_close_session=Mock())
            transitions = SessionTransitions(host)

            self.assertTrue(transitions.request_reader_close(session.id))
            exit_task = private._exit_task
            await asyncio.sleep(0)
            self.assertFalse(exit_task.done())
            workspace.invalidate(session.id)
            progress.worker = None
            worker.set_result(None)
            await exit_task

            host.request_close_session.assert_not_called()
            self.assertIsNone(private._exit_task)
