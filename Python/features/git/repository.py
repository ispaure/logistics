"""Repository operations and snapshots, usable without Qt.

UI callers execute these methods on a worker. Refs are validated before being
used as options; paths use literal pathspecs and explicit argument boundaries.
"""
from dataclasses import dataclass
from pathlib import Path
import re

from .models import parse_status, parse_log, parse_refs, parse_tree
from .runner import GitError, GitRunner, redact


def argument(value, label='Value'):
    value = str(value)
    if not value or value.startswith('-') or any(ord(c) < 32 for c in value):
        raise GitError(f'{label} must be nonempty, cannot start with a dash, and cannot contain control characters.')
    return value


def remote_url(value):
    value = argument(value.strip(), 'Repository URL')
    if re.search(r'https?://[^/\s]*@', value) or re.search(r'https?://[^\s]*\?', value):
        raise GitError('Use a repository URL without credentials or query tokens. Configure a Git credential helper or SSH agent.')
    return value


@dataclass
class Snapshot:
    root: Path
    status: object
    commits: list
    refs: list
    remotes: list[str]
    stashes: list[tuple[str, str]]
    operation: str = ''
    more_history: bool = False


class Repository:
    def __init__(self, path, runner=None):
        self.path = Path(path).expanduser().absolute()
        self.runner = runner or GitRunner()

    def run(self, args, **kwargs):
        return self.runner.run(args, cwd=self.path, **kwargs)

    def root(self):
        result = self.run(['rev-parse', '--show-toplevel'])
        return Path(result.stdout.decode('utf-8', 'surrogateescape').rstrip('\r\n'))

    def status(self):
        return parse_status(self.run(['status', '--porcelain=v2', '--branch', '-z']).stdout)

    def refs(self):
        return parse_refs(self.run(['for-each-ref', '--format=%(refname)%00%(objectname)%00%(upstream)%00%(HEAD)',
                                    'refs/heads', 'refs/remotes', 'refs/tags']).stdout)

    def history(self, limit=200):
        if not 1 <= limit <= 5000: raise GitError('History limit must be between 1 and 5000.')
        return parse_log(self.run(['log', '--all', '--topo-order', f'--max-count={limit}',
                                  '--format=%H%x00%P%x00%an%x00%aI%x00%s%x00%D%x00%x00']).stdout)

    def operation(self):
        for marker, name in (('rebase-merge', 'rebase'), ('rebase-apply', 'rebase'),
                             ('MERGE_HEAD', 'merge'), ('CHERRY_PICK_HEAD', 'cherry-pick'),
                             ('REVERT_HEAD', 'revert'), ('BISECT_LOG', 'bisect')):
            result = self.run(['rev-parse', '--git-path', marker])
            path = Path(result.stdout.decode('utf-8', 'surrogateescape').rstrip('\r\n'))
            if not path.is_absolute(): path = self.path / path
            if path.exists(): return name
        return ''

    def snapshot(self, limit=200):
        root = self.root()
        self.path = root
        status = self.status()
        refs = self.refs()
        # Empty repositories have no log. Do not swallow unrelated log failures.
        commits = self.history(limit + 1) if refs or status.oid not in ('', '(initial)') else []
        stashes = []
        for line in self.run(['stash', 'list', '--format=%gd%x00%gs']).stdout.splitlines():
            ref, subject = line.split(b'\0', 1)
            stashes.append((ref.decode('ascii'), subject.decode('utf-8', 'replace')))
        remotes = self.run(['remote']).stdout.decode('utf-8', 'replace').splitlines()
        return Snapshot(root, status, commits[:limit], refs, remotes, stashes, self.operation(), len(commits) > limit)

    def diff(self, path, *, staged=False):
        result = self.run(['diff', '--no-ext-diff', '--no-textconv', *(['--cached'] if staged else []),
                           '--', path], check=False, limit=1024 * 1024)
        if result.returncode: raise GitError(result.stderr)
        text = result.stdout.decode('utf-8', 'replace')
        return text + ('\n[Diff truncated to 1 MiB]' if result.truncated else '')

    def untracked_preview(self, path):
        file = self.path / path
        if file.is_symlink(): return 'Symbolic link → ' + str(file.readlink())
        if not file.is_file(): return 'Directory or nested repository. Open it separately to inspect its files.'
        with file.open('rb') as stream: data = stream.read(1024 * 1024 + 1)
        if b'\0' in data: return 'Binary file (preview unavailable).'
        return data[:1024 * 1024].decode('utf-8', 'replace') + ('\n[Preview truncated]' if len(data) > 1024 * 1024 else '')

    def commit_details(self, oid):
        oid = self.object_id(oid)
        result = self.run(['show', '--no-ext-diff', '--no-textconv', '--format=fuller', '--stat', '--patch', oid,
                           '--'], check=False, limit=1024 * 1024)
        if result.returncode: raise GitError(result.stderr)
        return result.stdout.decode('utf-8', 'replace') + ('\n[Commit preview truncated]' if result.truncated else '')

    @staticmethod
    def object_id(oid):
        if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', oid): raise GitError('Invalid object ID.')
        return oid

    def tree(self, oid):
        return parse_tree(self.run(['ls-tree', '-rz', self.object_id(oid)]).stdout)

    def blob(self, oid):
        result = self.run(['cat-file', 'blob', self.object_id(oid)], check=False, limit=1024 * 1024)
        if result.returncode: raise GitError(result.stderr)
        if b'\0' in result.stdout: return 'Binary file (preview unavailable).'
        return result.stdout.decode('utf-8', 'replace') + ('\n[File preview truncated]' if result.truncated else '')

    def stage(self, paths):
        if not paths: raise GitError('Select files to stage.')
        return self.run(['add', '--', *paths])

    def unstage(self, paths):
        if not paths: raise GitError('Select files to unstage.')
        # rm --cached also works before the first commit, and leaves files on disk.
        if self.status().oid == '(initial)': return self.run(['rm', '--cached', '-r', '--', *paths])
        return self.run(['restore', '--staged', '--', *paths])

    def commit(self, message, amend=False):
        if not message.strip(): raise GitError('Enter a commit message.')
        if self.operation() in ('rebase', 'cherry-pick', 'revert'):
            raise GitError('Use Continue to finish the current operation.')
        return self.run(['commit', *(['--amend'] if amend else []), '-m', message], timeout=600)

    def create_branch(self, name, switch=True):
        name = argument(name.strip(), 'Branch name')
        self.run(['check-ref-format', '--branch', name])
        return self.run(['switch', '-c', name] if switch else ['branch', name])

    def switch(self, name):
        return self.run(['switch', argument(name, 'Branch name')])

    def delete_branch(self, name):
        return self.run(['branch', '-d', argument(name, 'Branch name')])

    def rename_branch(self, old, new):
        self.run(['check-ref-format', '--branch', argument(new, 'Branch name')])
        return self.run(['branch', '-m', argument(old), new])

    def remote_add(self, name, url):
        return self.run(['remote', 'add', argument(name.strip(), 'Remote name'), remote_url(url)])

    def remote_set_url(self, name, url):
        return self.run(['remote', 'set-url', argument(name), remote_url(url)])

    def remote_remove(self, name):
        return self.run(['remote', 'remove', argument(name)])

    def remote_details(self, name):
        return redact(self.run(['remote', 'get-url', argument(name)]).stdout.decode('utf-8', 'replace').strip())

    def fetch(self, remote=None):
        return self.run(['fetch', '--progress', *([argument(remote)] if remote else ['--all'])], timeout=1800)

    def pull(self, strategy='ff-only'):
        options = {'ff-only': ['--ff-only'], 'merge': ['--no-rebase', '--no-edit'], 'rebase': ['--rebase']}
        if strategy not in options: raise GitError('Unknown pull strategy.')
        return self.run(['pull', '--progress', *options[strategy]], timeout=1800)

    def push(self, remote=None, branch=None):
        args = ['push', '--progress']
        if remote:
            if not branch: raise GitError('Select a branch to publish.')
            args += ['--set-upstream', argument(remote), f'HEAD:refs/heads/{argument(branch)}']
        return self.run(args, timeout=1800)

    def stash_save(self, message, include_untracked=False):
        return self.run(['stash', 'push', *(['--include-untracked'] if include_untracked else []), '-m', message or 'Logistics stash'])

    def stash_action(self, action, ref):
        if action not in ('apply', 'pop', 'drop'): raise GitError('Invalid stash action.')
        if not re.fullmatch(r'stash@\{\d+\}', ref): raise GitError('Invalid stash reference.')
        return self.run(['stash', action, ref])

    def discard(self, paths):
        if not paths: raise GitError('Select tracked files to discard.')
        return self.run(['restore', '--worktree', '--', *paths])

    def merge(self, ref):
        return self.run(['merge', '--no-edit', argument(ref)], timeout=600)

    def cherry_pick(self, oid):
        return self.run(['cherry-pick', self.object_id(oid)], timeout=600)

    def revert(self, oid):
        return self.run(['revert', '--no-edit', self.object_id(oid)], timeout=600)

    def finish_operation(self, operation, abort=False):
        if operation not in ('merge', 'rebase', 'cherry-pick', 'revert'): raise GitError('No supported operation in progress.')
        if not abort and operation == 'merge': return self.run(['commit', '--no-edit'], timeout=600)
        # Prevent an invisible editor when completing a rebase/cherry-pick.
        return self.run(['-c', 'core.editor=true', operation, '--abort' if abort else '--continue'], timeout=600)

    def worktrees(self):
        data = self.run(['worktree', 'list', '--porcelain', '-z']).stdout
        result, current = [], {}
        for record in data.split(b'\0'):
            if not record:
                if current: result.append(current); current = {}
            else:
                key, _, value = record.partition(b' ')
                current[key.decode('ascii')] = value.decode('utf-8', 'surrogateescape')
        if current: result.append(current)
        return result

    def add_worktree(self, path, branch):
        return self.run(['worktree', 'add', '--', str(Path(path).expanduser().absolute()), argument(branch)])

    def submodules(self):
        return self.run(['submodule', 'status', '--recursive']).stdout.decode('utf-8', 'replace')

    def update_submodules(self):
        return self.run(['submodule', 'update', '--init', '--recursive', '--progress'], timeout=1800)

    def add_submodule(self, url, path):
        return self.run(['submodule', 'add', '--', remote_url(url), argument(path, 'Submodule path')], timeout=1800)

    def subtree(self, action, prefix, url, branch, squash=False):
        if action not in ('add', 'pull', 'push'): raise GitError('Invalid subtree action.')
        prefix = argument(prefix, 'Subtree prefix')
        if Path(prefix).is_absolute() or '..' in Path(prefix).parts: raise GitError('Use a relative prefix within the repository.')
        args = ['subtree', action, f'--prefix={prefix}', remote_url(url), argument(branch)]
        if squash and action != 'push': args.append('--squash')
        return self.run(args, timeout=1800)


def clone(url, destination, runner=None, recursive=False, branch=''):
    runner = runner or GitRunner()
    destination = Path(destination).expanduser().absolute()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise GitError('Choose a new or empty destination directory.')
    args = ['clone', '--progress', *(['--recurse-submodules'] if recursive else [])]
    if branch: args += ['--branch', argument(branch, 'Branch name')]
    runner.run([*args, '--', remote_url(url), str(destination)], timeout=1800)
    return destination


def initialize(path, runner=None):
    path = Path(path).expanduser().absolute()
    path.mkdir(parents=True, exist_ok=True)
    (runner or GitRunner()).run(['init', '--', str(path)])
    return path
