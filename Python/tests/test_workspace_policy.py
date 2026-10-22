"""Workspace decisions can run without a native toolkit or application instance."""
from types import SimpleNamespace as NS
import unittest
from mobile.workspace_policy import WorkspaceSelection, session_view


class WorkspacePolicyTests(unittest.TestCase):
    def test_only_retained_editable_provider_views_can_be_paired(self):
        editable = object()
        app = NS(workspace=NS(sessions={'private': object(), 'closed': object()}), text_views={},
                 private_sessions=NS(controllers={'private': NS(crypt_reader=NS(editable=True), crypt_view=editable)}))
        self.assertIs(session_view(app, 'private'), editable)
        self.assertIsNone(session_view(app, 'closed'))
        self.assertIsNone(session_view(app, 'unknown'))
        app.private_sessions.controllers['private'].crypt_reader.editable = False
        self.assertIsNone(session_view(app, 'private'))

    def test_focus_swap_and_close_retire_only_the_pinned_selection(self):
        selection = WorkspaceSelection('left')
        views = {'left': object(), 'right': object()}
        selection.focus('left', 'right', views.get)
        self.assertEqual(selection.pinned, 'right')
        views.pop('right')
        selection.retire_unavailable(views.get)
        self.assertIsNone(selection.pinned)

    def test_pair_picker_excludes_current_and_noneditable_providers(self):
        sessions = {'current': NS(provider='managed-text'), 'text': NS(provider='managed-text'),
                    'editable': NS(provider='remote'), 'readonly': NS(provider='remote')}
        self.assertEqual(WorkspaceSelection().candidates(sessions, 'current',
                         lambda key: object() if key == 'editable' else None), ('text', 'editable'))
