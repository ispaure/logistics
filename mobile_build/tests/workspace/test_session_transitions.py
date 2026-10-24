"""Explicit close preparation/results preserve vetoes and stale-session guards."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
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
        import asyncio
        from unittest.mock import Mock, patch
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
                with patch('features.text_editor.mobile.document_dialogs.DocumentDialog'):
                    transitions.document_close_dialog(session.id, 'Synthetic', save, discard)
                    task = host._document_close_tasks[session.id]
                    await asyncio.sleep(0)
                    workspace.invalidate(session.id)
                    answer.set_result(choice)
                    await task
                save.assert_not_called()
                discard.assert_not_called()
                self.assertFalse(host._document_close_tasks)
