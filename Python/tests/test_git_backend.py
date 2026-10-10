"""Real disposable repositories, including conflicts and a local bare remote."""
from pathlib import Path
import os
import shutil
import subprocess
from tempfile import TemporaryDirectory
from threading import Event
import unittest

from features.git.models import parse_status
from features.git.repository import Repository, clone, initialize, argument, remote_url
from features.git.runner import GitRunner, GitError, GitCancelled, redact


@unittest.skipUnless(shutil.which('git'), 'Git executable required')
class GitBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = Repository(initialize(self.root / 'repo'))
        self.repo.run(['config', 'user.name', 'Logistics Test'])
        self.repo.run(['config', 'user.email', 'test@example.invalid'])
        self.repo.run(['config', 'commit.gpgsign', 'false'])
        self.repo.run(['config', 'core.autocrlf', 'false'])
        self.repo.run(['config', 'core.hooksPath', str(self.root / 'no-hooks')])
        self.repo.run(['symbolic-ref', 'HEAD', 'refs/heads/main'])

    def write(self, name='file.txt', content='one\n'):
        path = self.repo.path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return path

    def commit(self, name='file.txt', content='one\n', message='First'):
        self.write(name, content)
        self.repo.stage([name])
        self.repo.commit(message)
        return self.repo.status().oid

    def test_empty_repository_snapshot_and_unborn_unstage(self):
        snapshot = self.repo.snapshot()
        self.assertEqual(snapshot.status.oid, '(initial)')
        self.assertEqual(snapshot.commits, [])
        self.write()
        self.repo.stage(['file.txt'])
        self.repo.unstage(['file.txt'])
        self.assertTrue((self.repo.path / 'file.txt').exists())
        self.assertEqual(self.repo.status().changes[0].index, '?')

    def test_status_handles_unicode_spaces_newlines_and_literal_pathspec(self):
        names = ['space name.txt', 'é漢.txt', ':literal.txt', 'line\nbreak.txt', '-dash.txt']
        for name in names: self.write(name)
        self.assertEqual({c.path for c in self.repo.status().changes}, set(names))
        self.repo.stage(names)
        self.assertTrue(all(c.staged for c in self.repo.status().changes))
        self.repo.commit('Paths')
        self.assertEqual({e.path for e in self.repo.tree(self.repo.status().oid)}, set(names))

    def test_history_tree_blob_and_changed_diff(self):
        first = self.commit('dir/a.txt', 'hello\n', 'First commit')
        self.commit('dir/a.txt', 'second\n', 'Second commit')
        snapshot = self.repo.snapshot()
        self.assertEqual([c.subject for c in snapshot.commits], ['Second commit', 'First commit'])
        self.assertEqual(snapshot.commits[0].parents, (first,))
        self.assertEqual(self.repo.blob(self.repo.tree(first)[0].oid), 'hello\n')
        self.assertIn('First commit', self.repo.commit_details(first))
        self.write('dir/a.txt', 'third\n')
        self.assertIn('+third', self.repo.diff('dir/a.txt'))
        self.repo.stage(['dir/a.txt'])
        self.assertIn('+third', self.repo.diff('dir/a.txt', staged=True))

    def test_stage_rename_and_unstage_both_paths(self):
        self.commit('old name.txt')
        (self.repo.path / 'old name.txt').rename(self.repo.path / 'new name.txt')
        self.repo.stage(['old name.txt', 'new name.txt'])
        change = self.repo.status().changes[0]
        self.assertEqual((change.path, change.original_path, change.index), ('new name.txt', 'old name.txt', 'R'))
        self.repo.unstage([change.path, change.original_path])
        self.assertTrue((self.repo.path / 'new name.txt').exists())

    def test_branch_stash_discard_and_amend(self):
        self.commit()
        self.repo.create_branch('feature/test')
        self.assertEqual(self.repo.status().branch, 'feature/test')
        self.repo.rename_branch('feature/test', 'feature/renamed')
        self.write(content='changed\n')
        self.repo.stash_save('Save it')
        self.assertEqual(len(self.repo.snapshot().stashes), 1)
        self.assertFalse(self.repo.status().changes)
        self.repo.stash_action('pop', 'stash@{0}')
        self.repo.discard(['file.txt'])
        self.assertEqual((self.repo.path / 'file.txt').read_text(), 'one\n')
        self.repo.commit('Amended', amend=True)
        self.assertEqual(self.repo.history()[0].subject, 'Amended')
        self.repo.switch('main')
        with self.assertRaises(GitError): self.repo.delete_branch('feature/renamed')
        self.repo.create_branch('temporary', switch=False)
        self.repo.delete_branch('temporary')

    def test_conflicting_merge_can_resolve_and_continue(self):
        self.commit()
        self.repo.create_branch('other')
        self.commit(content='other\n', message='Other')
        self.repo.switch('main')
        self.commit(content='main\n', message='Main')
        with self.assertRaises(GitError): self.repo.merge('other')
        self.assertEqual(self.repo.operation(), 'merge')
        self.assertTrue(self.repo.status().changes[0].conflict)
        self.write(content='resolved\n')
        self.repo.stage(['file.txt'])
        self.repo.finish_operation('merge')
        self.assertFalse(self.repo.operation())
        self.assertEqual(len(self.repo.history()[0].parents), 2)

    def test_abort_conflicting_merge(self):
        self.commit()
        self.repo.create_branch('other')
        self.commit(content='other\n')
        self.repo.switch('main')
        self.commit(content='main\n')
        with self.assertRaises(GitError): self.repo.merge('other')
        self.repo.finish_operation('merge', abort=True)
        self.assertEqual((self.repo.path / 'file.txt').read_text(), 'main\n')

    def test_clone_fetch_publish_pull_and_remote_edit(self):
        self.commit()
        bare = self.root / 'remote.git'
        self.repo.runner.run(['init', '--bare', '--', str(bare)])
        self.repo.remote_add('origin', str(bare))
        self.repo.push('origin', 'main')
        self.repo.runner.run(['--git-dir', str(bare), 'symbolic-ref', 'HEAD', 'refs/heads/main'])
        copy = Repository(clone(str(bare), self.root / 'copy'))
        self.assertEqual(copy.status().branch, 'main')
        self.commit(content='remote update\n', message='Remote')
        self.repo.push()
        copy.fetch()
        self.assertEqual(copy.status().behind, 1)
        copy.pull()
        self.assertEqual((copy.path / 'file.txt').read_text(), 'remote update\n')
        copy.remote_set_url('origin', str(bare))
        self.assertEqual(copy.remote_details('origin'), str(bare))
        copy.remote_remove('origin')
        self.assertEqual(copy.snapshot().remotes, [])

    def test_clone_refuses_nonempty_destination(self):
        self.commit()
        with self.assertRaises(GitError): clone(str(self.repo.path), self.repo.path)

    def test_worktree_discovery_and_creation(self):
        self.commit()
        self.repo.create_branch('second', switch=False)
        path = self.root / 'work tree'
        self.repo.add_worktree(path, 'second')
        other = Repository(path)
        self.assertEqual(other.snapshot().status.branch, 'second')
        self.assertEqual(len(other.worktrees()), 2)
        self.assertEqual(other.root(), path.resolve())

    def test_cherry_pick_and_revert(self):
        self.commit()
        self.repo.create_branch('other')
        oid = self.commit('extra.txt', message='Extra')
        self.repo.switch('main')
        self.repo.cherry_pick(oid)
        self.assertTrue((self.repo.path / 'extra.txt').exists())
        self.repo.revert(self.repo.status().oid)
        self.assertFalse((self.repo.path / 'extra.txt').exists())

    def test_invalid_options_credentials_and_ids_rejected(self):
        for value in ('-x', '', 'line\nbreak'):
            with self.assertRaises(GitError): argument(value)
        for value in ('https://token@example.com/repo', 'https://example.com/repo?token=x'):
            with self.assertRaises(GitError): remote_url(value)
        with self.assertRaises(GitError): self.repo.commit_details('HEAD;anything')
        with self.assertRaises(GitError): self.repo.create_branch('-bad')
        with self.assertRaises(GitError): self.repo.subtree('add', '../bad', 'example', 'main')

    def test_cancellation_and_missing_executable(self):
        event = Event(); event.set()
        with self.assertRaises(GitCancelled): GitRunner(cancel=event).run(['status'])
        with self.assertRaises(GitError): GitRunner('/missing/git').run(['status'])

    def test_capture_limit_and_host_environment_isolation(self):
        from unittest.mock import patch
        self.commit()
        result = self.repo.run(['show', 'HEAD:file.txt'], check=False, limit=2)
        self.assertTrue(result.truncated)
        with self.assertRaises(GitError): self.repo.run(['show', 'HEAD:file.txt'], limit=2)
        with patch.dict(os.environ, {'GIT_DIR': str(self.root / 'missing')}):
            self.assertEqual(self.repo.status().branch, 'main')


class GitParsingTests(unittest.TestCase):
    def test_redaction(self):
        secret = 'fatal https://user:secret@example.com/repo?token=abc password=hunter2'
        result = redact(secret)
        for value in ('secret', 'abc', 'hunter2'): self.assertNotIn(value, result)

    def test_conflict_parser_and_branch_tracking(self):
        data = (b'# branch.oid abc\0# branch.head main\0# branch.upstream origin/main\0# branch.ab +2 -3\0'
                b'u UU N... 100644 100644 100644 100644 a b c conflict.txt\0')
        status = parse_status(data)
        self.assertEqual((status.ahead, status.behind), (2, 3))
        self.assertTrue(status.changes[0].conflict)
        self.assertEqual(status.changes[0].path, 'conflict.txt')


if __name__ == '__main__': unittest.main()
