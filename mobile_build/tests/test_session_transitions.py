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
