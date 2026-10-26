"""Captured mutations reject changed repository/branch before touching fixtures."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
from features.git.repository import Repository, initialize
from features.git.runner import GitError
from features.git.ui.commands.requests import GitCommand


class GitCommandTests(unittest.TestCase):
    def test_mutable_selection_is_detached_before_dispatch(self):
        paths = ['captured.txt']
        request = GitCommand.capture('/fixture', 'Stage', 'stage', (paths,))
        paths[:] = ['later.txt']
        repo = SimpleNamespace(path=Path('/fixture'), stage=Mock())
        request.execute(repo)
        repo.stage.assert_called_once_with(('captured.txt',))

    def test_options_and_nested_inputs_cannot_be_changed_after_capture(self):
        settings = {'identity': {'name': 'captured'}}
        request = GitCommand.capture('/fixture', 'Settings', 'save_settings', (settings,))
        settings['identity']['name'] = 'later'
        self.assertEqual(request.arguments[0]['identity']['name'], 'captured')
        with self.assertRaises(TypeError):
            request.arguments[0]['identity']['name'] = 'changed'
        with self.assertRaises(GitError):
            request.execute(SimpleNamespace(path=Path('/other')))

    def test_stale_branch_prevents_commit_and_valid_request_uses_existing_repository(self):
        with TemporaryDirectory() as directory:
            repo = Repository(initialize(Path(directory) / 'repo'))
            repo.run(['config', 'user.name', 'Command fixture'])
            repo.run(['config', 'user.email', 'fixture@example.invalid'])
            repo.run(['config', 'commit.gpgsign', 'false'])
            (repo.path / 'file').write_text('synthetic')
            repo.stage(['file'])
            repo.commit('Initial')
            before = repo.status().branch
            request = GitCommand.capture(repo.path, 'Commit', 'commit', ('Captured', False), expected_branch=before)
            repo.create_branch('other', True)
            with self.assertRaisesRegex(GitError, 'branch changed'):
                request.execute(repo)
            self.assertEqual(repo.history()[0].subject, 'Initial')
            branch = GitCommand.capture(repo.path, 'Create branch', 'create_branch', ('captured', False, None))
            branch.execute(repo)
            self.assertTrue(any(ref.name == 'refs/heads/captured' for ref in repo.refs()))


class CommandFormCaptureTests(unittest.TestCase):
    def test_merge_form_keeps_repository_and_branch_from_before_dialog(self):
        from features.git.ui.commands.forms import RepositoryCommands
        view = SimpleNamespace(path=Path('/first'), closing=False,
            snapshot=SimpleNamespace(status=SimpleNamespace(branch='original'),
                refs=[SimpleNamespace(current=False, name='refs/heads/topic')]),
            _confirm=Mock(return_value=True), _operation=Mock())
        commands = RepositoryCommands(view)
        view._merge = commands._merge
        dialog = Mock()
        dialog.choice.return_value.currentText.return_value = 'refs/heads/topic'
        def submitted():
            view.path = Path('/second')
            return True
        dialog.submitted.side_effect = submitted
        with patch('features.git.ui.commands.forms.FormDialog', return_value=dialog):
            commands.merge_dialog()
        view._operation.assert_not_called()

    def test_publish_form_cannot_retarget_a_different_repository(self):
        from features.git.ui.commands.forms import RepositoryCommands
        view = SimpleNamespace(path=Path('/first'), closing=False,
            snapshot=SimpleNamespace(status=SimpleNamespace(branch='original', upstream=''),
                                     remotes=['origin']), _operation=Mock())
        dialog = Mock()
        dialog.choice.return_value.currentText.return_value = 'origin'
        dialog.text.return_value.text.return_value = 'published'
        def submitted():
            view.path = Path('/second')
            return True
        dialog.submitted.side_effect = submitted
        with patch('features.git.ui.commands.forms.FormDialog', return_value=dialog):
            RepositoryCommands(view).publish_dialog()
        view._operation.assert_not_called()

    def test_force_push_confirmation_cannot_retarget_a_different_repository(self):
        from features.git.ui.commands.forms import RepositoryCommands
        view = SimpleNamespace(path=Path('/first'), closing=False,
            snapshot=SimpleNamespace(status=SimpleNamespace(branch='original', upstream='origin/original')),
            preferences=SimpleNamespace(options={'allow_force_push': True}), _operation=Mock())
        def confirm(*args):
            view.path = Path('/second')
            return True
        view._confirm = confirm
        RepositoryCommands(view).push(force_with_lease=True)
        view._operation.assert_not_called()

    def test_stash_application_revalidates_active_branch_on_worker(self):
        from features.git.ui.commands.forms import RepositoryCommands
        view = SimpleNamespace(path=Path('/fixture'), closing=False, _operation=Mock())
        commands = RepositoryCommands(view)
        commands.dispatch('Apply stash', 'stash_action', 'apply', 'stash@{0}', branch='original')
        request = view._operation.call_args.args[1]
        repository = SimpleNamespace(path=view.path,
            status=lambda: SimpleNamespace(branch='replacement'), stash_action=Mock())
        with self.assertRaises(GitError):
            request(repository)
        repository.stash_action.assert_not_called()

    def test_stage_confirmation_cannot_retarget_a_different_repository(self):
        from features.git.ui.application_preferences import ApplicationPreferences
        from features.git.ui.commands.forms import RepositoryCommands
        view = SimpleNamespace(path=Path('/first'), closing=False,
            snapshot=SimpleNamespace(status=SimpleNamespace(branch='original')),
            preferences=SimpleNamespace(options={'confirm_stage': True}), _operation=Mock())
        view.commands = RepositoryCommands(view)
        def confirm(*args):
            view.path = Path('/second')
            return True
        view._confirm = confirm
        ApplicationPreferences.stage_files(view, ['captured.txt'])
        view._operation.assert_not_called()

    def test_context_menu_callback_cannot_use_a_different_repository(self):
        from features.git.ui.commands.forms import RepositoryCommands
        callbacks = {}
        class Menu:
            def __init__(self, view):
                pass
            def addAction(self, title, callback):
                callbacks[title] = callback
            def actions(self):
                return list(callbacks)
            def exec(self, point):
                view.path = Path('/second')
                callbacks['Merge into current branch…']()
        view = SimpleNamespace(path=Path('/first'), closing=False, busy=False,
            snapshot=SimpleNamespace(status=SimpleNamespace(branch='original')),
            refs=SimpleNamespace(itemAt=lambda point: SimpleNamespace(data=lambda *args: ('branch', 'topic', None)),
                viewport=lambda: SimpleNamespace(mapToGlobal=lambda point: point)), _merge=Mock())
        with patch('features.git.ui.commands.forms.qt.QMenu', Menu):
            RepositoryCommands(view).ref_menu(None)
        view._merge.assert_not_called()
