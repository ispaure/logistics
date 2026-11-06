"""Workspace decisions can run without a native toolkit or application instance."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from commonUtils.configuration.layered import register_settings
from commonUtils.testing.stages import TestStage
from mobile import folder_hub
from mobile.workspace_policy import WorkspaceSelection, session_view
from services.folders.entries import get_folder_entries

TEST_STAGE = TestStage.REGRESSION


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

    def test_mobile_and_desktop_follow_personal_folder_exclusions_and_reset(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = root / 'configFile.ini'
            settings.write_text('[Folders]\nexcluded_remote_names = Default\n'
                                'excluded_folder_name_suffixes = -Old\n')
            store = register_settings(settings, root / 'personal.ini')
            remotes = ['Default', 'Personal', 'Draft-OLD', 'Draft-New', 'Keep']
            overrides = {('Folders', 'excluded_remote_names'): 'personal',
                         ('Folders', 'excluded_folder_name_suffixes'): '-new'}

            with patch('config.get_config_file_path', return_value=settings), patch.object(
                folder_hub, '__file__', str(root / 'mobile/folder_hub.py')
            ):
                def check_visible(expected):
                    self.assertCountEqual(folder_hub.visible_remotes(remotes), expected)
                    self.assertCountEqual(
                        [entry.name for entry in get_folder_entries(remotes, local_folders=[])],
                        expected,
                    )

                check_visible(['Personal', 'Draft-New', 'Keep'])
                store.save(overrides)
                check_visible(['Default', 'Draft-OLD', 'Keep'])
                store.save(dict.fromkeys(overrides))
                check_visible(['Personal', 'Draft-New', 'Keep'])
