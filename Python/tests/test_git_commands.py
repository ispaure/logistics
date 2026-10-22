"""Captured mutations reject changed repository/branch before touching fixtures."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock
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
