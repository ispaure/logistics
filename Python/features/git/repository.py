"""Repository operations and snapshots, usable without Qt.

UI callers execute these methods on a worker. Refs are validated before being
used as options; paths use literal pathspecs and explicit argument boundaries.
"""
from dataclasses import dataclass
from pathlib import Path
import re
import os

from .models import Status, Commit, Ref, parse_status, parse_log, parse_refs, parse_tree, TreeEntry
from .runner import GitError, GitRunner, redact


def argument(value, label='Value'):
    value = str(value)
    if not value or value.startswith('-') or any(ord(c) < 32 for c in value):
        raise GitError(f'{label} must be nonempty, cannot start with a dash, and cannot contain control characters.')
    return value


def remote_url(value):
    value = argument(value.strip(), 'Repository URL')
    if (re.search(r'https?://[^/\s]*@', value) or re.search(r'https?://[^\s]*\?', value)
            or re.search(r'[a-z][a-z0-9+.-]{0,31}://[^/\s]*:[^/\s]*@', value)):
        raise GitError('Use a repository URL without credentials or query tokens. Configure a Git credential helper or SSH agent.')
    return value


@dataclass
class Snapshot:
    root: Path
    status: Status
    commits: list[Commit]
    refs: list[Ref]
    remotes: list[str]
    stashes: list[tuple[str, str]]
    operation: str = ''
    more_history: bool = False
    submodule_paths: tuple[str, ...] = ()
    display_name: str = ''
    template_text: str = ''
    template_warning: str = ''
    template_configured: bool = False
    tracked_paths: tuple[str, ...] = ()



@dataclass(frozen=True)
class ConflictInputs:
    path: Path
    relative_path: str
    index_state: bytes
    base: str
    left: str
    right: str
    working: object
    existed: bool
    operation: str


class Repository:
    def __init__(self, path, runner=None):
        self.path = Path(path).expanduser().absolute()
        self.runner = runner or GitRunner()

    def run(self, args, **kwargs):
        return self.runner.run(args, cwd=self.path, **kwargs)

    def root(self):
        result = self.run(['rev-parse', '--show-toplevel'])
        return Path(result.stdout.removesuffix(b'\n').decode('utf-8', 'surrogateescape'))

    def status(self):
        return parse_status(self.run(['status', '--porcelain=v2', '--branch', '-z']).stdout)

    def refs(self):
        return parse_refs(self.run(['for-each-ref', '--format=%(refname)%00%(objectname)%00%(upstream)%00%(HEAD)',
                                    'refs/heads', 'refs/remotes', 'refs/tags']).stdout)

    def history(self, limit=200):
        if not 1 <= limit <= 5001: raise GitError('History limit must be between 1 and 5001.')
        return parse_log(self.run(['log', '--all', '--topo-order', f'--max-count={limit}',
                                  '--format=%H%x00%P%x00%an%x00' + ('%aI' if self.runner.author_date else '%cI') + '%x00%s%x00%D%x00%x00']).stdout)

    def search_history(self, query, mode='Commit Message', since='1980-01-01', until='2100-01-01', limit=200):
        from datetime import date, datetime, time
        try:
            first, last = date.fromisoformat(since), date.fromisoformat(until)
        except ValueError as exc:
            raise GitError('Choose valid search dates.') from exc
        if first > last: raise GitError('From date must be on or before To date.')
        if not 1 <= limit <= 5000: raise GitError('Search limit must be between 1 and 5000.')
        if mode not in ('Commit Message', 'Commit SHA', 'Branch', 'File Changes', 'User'):
            raise GitError('Unknown search field.')
        # Numeric bounds avoid Git's approximate-date parser misreading distant years.
        start = int(datetime.combine(first, time.min).timestamp())
        end = int(datetime.combine(last, time(23, 59, 59)).timestamp())
        bounds = [f'--max-age={start}', f'--min-age={end}']
        refs = ['--all']
        options = []
        query = query.strip()
        if query and mode == 'Branch':
            refs = [ref.name for ref in self.refs() if ref.name.startswith(('refs/heads/', 'refs/remotes/'))
                    and query.casefold() in ref.name.casefold()]
            if not refs: return []
        elif query and mode == 'Commit SHA':
            if not re.fullmatch(r'[a-fA-F0-9]{4,64}', query): return []
            hashes = self.run(['rev-list', '--all', *bounds]).stdout.decode('ascii').splitlines()
            refs = [oid for oid in hashes if oid.startswith(query.lower())][:limit + 1]
            if not refs: return []
            options = ['--no-walk']
        elif query and mode == 'File Changes':
            # Double NUL marks a header; filenames are NUL-separated and never empty.
            data = self.run(['log', '--all', *bounds, '--diff-merges=first-parent',
                             '--format=%x00%x00%H', '--name-only', '--no-renames', '-z']).stdout
            records = re.split(rb'\0\0([a-f0-9]{40}|[a-f0-9]{64})\0', data)
            refs = []
            for i in range(1, len(records), 2):
                paths = records[i + 1].removeprefix(b'\n').split(b'\0')
                if any(query.casefold() in os.fsdecode(path).casefold() for path in paths if path):
                    refs.append(records[i].decode('ascii'))
                    if len(refs) > limit: break
            if not refs: return []
            options = ['--no-walk']
        elif query and mode == 'User':
            options = ['--regexp-ignore-case', '--extended-regexp', '--author=' + re.escape(query)]
        elif query:
            options = ['--regexp-ignore-case', '--fixed-strings', '--grep=' + query]
        if not self.refs(): return []
        return parse_log(self.run(['log', *refs, *bounds, *options, f'--max-count={limit + 1}',
                                  '--format=%H%x00%P%x00%an%x00' + ('%aI' if self.runner.author_date else '%cI') + '%x00%s%x00%D%x00%x00']).stdout)

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
        self.runner.version()
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
        config = self.run(['config', '--file', '.gitmodules', '--null', '--get-regexp', r'^submodule\..*\.path$'], check=False)
        if config.returncode not in (0,1): raise GitError(config.stderr)
        submodule_paths = tuple(os.fsdecode(record.partition(b'\n')[2]) for record in config.stdout.split(b'\0') if b'\n' in record)
        superproject = self.run(['rev-parse', '--show-superproject-working-tree']).stdout.removesuffix(b'\n')
        display_name = root.name
        if superproject:
            parent = Path(os.fsdecode(superproject))
            display_name = parent.name + '/' + root.relative_to(parent).as_posix()
        template, warning = self.read_template()
        tracked = tuple(os.fsdecode(path) for path in self.run(['ls-files', '-z']).stdout.split(b'\0') if path)
        return Snapshot(root, status, commits[:limit], refs, remotes, stashes, self.operation(), len(commits) > limit, submodule_paths, display_name, template, warning,
                        self.config_value('commit.template', local=True) is not None, tracked)

    def diff(self, path, *, staged=False, ignore_whitespace=False, against_head=False):
        result = self.run(['diff', '--no-ext-diff', '--no-textconv', '--src-prefix=a/', '--dst-prefix=b/', *(['HEAD'] if against_head else ['--cached'] if staged else []),
                           *(['--ignore-all-space'] if ignore_whitespace else []),
                           '--', path], check=False, limit=self.runner.diff_limit)
        if result.returncode: raise GitError(result.stderr)
        text = result.stdout.decode('utf-8', 'replace')
        return text + ('\n[Diff truncated to configured preview limit]' if result.truncated else '')

    def apply_hunk(self, relative_path, index, expected_patch, *, staged=False, discard=False):
        from tempfile import TemporaryDirectory
        from .patches import single_hunk
        if discard and staged: raise GitError('Unstage this hunk before discarding it.')
        root = self.root().resolve()
        path = root / relative_path
        if Path(relative_path).is_absolute() or '..' in Path(relative_path).parts or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise GitError('Hunks require a regular file within this repository.')
        change = next((change for change in self.status().changes if change.path == relative_path), None)
        if change is None or change.conflict or change.original_path or change.submodule != 'N...' or change.index == '?':
            raise GitError('Use file actions for untracked files, conflicts, renames and submodules.')
        self._check_text_attributes(relative_path)
        entries = self.run(['ls-files', '--stage', '-z', '--', relative_path]).stdout
        if not entries:
            entries = self.run(['ls-tree', '-z', 'HEAD', '--', relative_path]).stdout
        if not entries.startswith((b'100644 ', b'100755 ')):
            raise GitError('Hunk actions support regular text files only.')
        result = self.run(['diff', '--no-ext-diff', '--no-textconv', '--src-prefix=a/', '--dst-prefix=b/',
                           *(['--cached'] if staged else []), '--', relative_path], limit=self.runner.diff_limit)
        if result.truncated: raise GitError('A truncated patch cannot be applied. Use file actions.')
        if result.stdout.decode('utf-8', 'replace') != expected_patch:
            raise GitError('This file changed since the preview was loaded. Refresh before applying a hunk.')
        patch = single_hunk(result.stdout, index)
        if discard: self.backup_files([relative_path])
        with TemporaryDirectory(prefix='logistics-hunk-') as folder:
            patch_path = Path(folder) / 'hunk.patch'
            patch_path.write_bytes(patch)
            options = [*(['--reverse'] if staged or discard else []), *([] if discard else ['--cached']), '--whitespace=nowarn']
            self.run(['apply', '--check', *options, '--', str(patch_path)])
            return self.run(['apply', *options, '--', str(patch_path)])

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

    def commit_metadata(self, oid):
        """Read message and identity separately from potentially large patches."""
        data = self.run(['show', '-s', '--format=%H%x00%P%x00%an%x00%ae%x00%aI%x00%B%x00%D',
                         self.object_id(oid), '--'], limit=1024 * 1024).stdout
        fields = data.decode('utf-8', 'replace').split('\0', 6)
        return dict(zip(('oid', 'parents', 'author', 'email', 'date', 'message', 'labels'), fields))

    def _commit_comparison(self, oid):
        oid = self.object_id(oid)
        parents = self.run(['rev-list', '--parents', '-n', '1', oid]).stdout.decode('ascii').split()
        # Merge review deliberately compares the first parent, like the history UI.
        return [parents[1], oid] if len(parents) > 1 else [oid]

    def commit_files(self, oid):
        data = self.run(['diff-tree', '--root', '-r', '--no-commit-id', '--name-status', '-z',
                         '--no-renames', *self._commit_comparison(oid), '--']).stdout.split(b'\0')
        return [TreeEntry(data[i].decode('ascii'), 'change', oid, os.fsdecode(data[i+1]))
                for i in range(0,len(data)-1,2)]

    def commit_file_diff(self, oid, path, *, ignore_whitespace=False):
        result = self.run(['diff-tree', '--root', '-r', '--no-commit-id', '--patch', '--no-ext-diff',
                           '--no-textconv', *(['--ignore-all-space'] if ignore_whitespace else []),
                           *self._commit_comparison(oid), '--', path], check=False, limit=self.runner.diff_limit)
        if result.returncode: raise GitError(result.stderr)
        return result.stdout.decode('utf-8','replace') + ('\n[Diff truncated to configured preview limit]' if result.truncated else '')

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
        self.check_submodules()
        return self.run(['commit', *(['--amend'] if amend else []), '-m', message], timeout=600)

    def create_branch(self, name, switch=True, start_oid=None):
        name = argument(name.strip(), 'Branch name')
        self.run(['check-ref-format', '--branch', name])
        args = ['switch', '-c', name] if switch else ['branch', name]
        if start_oid: args.append(self.object_id(start_oid))
        return self.run(args)

    def compare(self, first, second, *, ignore_whitespace=False):
        result = self.run(['diff', '--no-ext-diff', '--no-textconv', '--stat', '--patch',
                           *(['--ignore-all-space'] if ignore_whitespace else []),
                           self.object_id(first), self.object_id(second), '--'], check=False, limit=1024 * 1024)
        if result.returncode: raise GitError(result.stderr)
        return result.stdout.decode('utf-8', 'replace') + ('\n[Comparison truncated]' if result.truncated else '')

    def create_tag(self, name, message='', oid=None):
        name = argument(name.strip(), 'Tag name')
        self.run(['check-ref-format', 'refs/tags/' + name])
        args = ['tag', '-a', name, '-m', message] if message.strip() else ['tag', name]
        if oid: args.append(self.object_id(oid))
        return self.run(args)

    def delete_tag(self, name):
        return self.run(['tag', '-d', argument(name, 'Tag name')])

    def push_tag(self, remote, name):
        return self.run(['push', '--progress', argument(remote), 'refs/tags/' + argument(name)], timeout=1800)

    def reflog(self):
        entries = []
        result = self.run(['reflog', '--max-count=100', '--format=%H%x00%gd%x00%gs'])
        for record in result.stdout.splitlines():
            oid, ref, message = record.split(b'\0', 2)
            entries.append((oid.decode('ascii'), ref.decode('utf-8', 'replace'), message.decode('utf-8', 'replace')))
        return entries

    def identity(self):
        return tuple(self.run(['config', '--get', key], check=False).stdout.decode('utf-8', 'replace').strip()
                     for key in ('user.name', 'user.email'))

    def set_identity(self, name, email):
        if not name.strip() or not email.strip() or any(ord(c) < 32 for c in name + email):
            raise GitError('Enter an author name and email without control characters.')
        self.run(['config', '--local', '--', 'user.name', name.strip()])
        return self.run(['config', '--local', '--', 'user.email', email.strip()])

    SETTINGS_KEYS = ('commit.template', 'commit.gpgsign', 'user.signingkey',
                     'gpg.format', 'user.name', 'user.email')

    def config_value(self, key, *, local=False):
        result = self.run(['config', *(['--local'] if local else []), '--get', key], check=False)
        if result.returncode == 1:
            return None
        if result.returncode:
            raise GitError(result.stderr)
        return result.stdout.decode('utf-8', 'replace').removesuffix('\n')

    def template_text(self):
        path = self.run(['config', '--path', '--get', 'commit.template'], check=False)
        if path.returncode == 1 or not path.stdout.strip():
            return ''
        if path.returncode:
            raise GitError(path.stderr)
        template = Path(path.stdout.decode('utf-8', 'replace').removesuffix('\n'))
        if not template.is_absolute():
            template = self.path / template
        try:
            with template.open('rb') as stream:
                data = stream.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise GitError('Commit template exceeds 1 MiB.')
            return data.decode('utf-8', 'replace')
        except OSError as exc:
            raise GitError(f'Could not read commit template: {exc}') from exc

    def read_template(self):
        try:
            return self.template_text(), ''
        except GitError as exc:
            return '', str(exc)

    def settings(self):
        template, warning = self.read_template()
        return {
            'root': str(self.path),
            'local': {key: self.config_value(key, local=True) for key in self.SETTINGS_KEYS},
            'effective': {key: self.config_value(key) for key in self.SETTINGS_KEYS},
            'template_text': template,
            'template_warning': warning,
            'remotes': {name: self.remote_details(name) for name in
                        self.run(['remote']).stdout.decode('utf-8', 'replace').splitlines()},
        }

    def save_settings(self, values):
        local = values['local']
        if set(local) != set(self.SETTINGS_KEYS):
            raise GitError('Unexpected repository setting.')
        for key in ('user.name', 'user.email'):
            value = local[key]
            if value is not None and (not value.strip() or any(ord(c) < 32 for c in value)):
                raise GitError('Enter an author name and email without control characters.')
        remotes = values['remotes']
        current = {name: self.remote_details(name) for name in
                   self.run(['remote']).stdout.decode('utf-8', 'replace').splitlines()}
        original = values.get('original')
        if original is not None:
            current_local = {key: self.config_value(key, local=True) for key in self.SETTINGS_KEYS}
            if current != original['remotes'] or current_local != original['local']:
                raise GitError('Repository settings changed while the dialog was open. Reopen Settings before saving.')
        for name, url in remotes.items():
            if current.get(name) != url:
                argument(name, 'Remote name'); remote_url(url)
        if values['template_mode'] == 'custom' and values.get('template_changed', True):
            from commonUtils.persistence import atomic_write_bytes
            result = self.run(['rev-parse', '--git-path', 'logistics-commit-template.txt'])
            path = Path(result.stdout.decode('utf-8', 'replace').removesuffix('\n'))
            if not path.is_absolute(): path = self.path / path
            data = values['template_text'].encode('utf-8')
            if len(data) > 1024 * 1024: raise GitError('Commit template exceeds 1 MiB.')
            atomic_write_bytes(path, data)
            local = dict(local, **{'commit.template': str(path.resolve())})
        for key, value in local.items():
            if value == self.config_value(key, local=True): continue
            if value is None:
                result = self.run(['config', '--local', '--unset-all', key], check=False)
                if result.returncode not in (0, 5): raise GitError(result.stderr)
            else:
                self.run(['config', '--local', '--replace-all', key, value])
        for name in current:
            if name not in remotes: self.remote_remove(name)
        for name, url in remotes.items():
            if name not in current: self.remote_add(name, url)
            elif self.remote_details(name) != url: self.remote_set_url(name, url)
        return self.settings()

    def switch(self, name):
        return self.run(['switch', argument(name, 'Branch name')])

    def delete_branch(self, name):
        return self.run(['branch', '-d', argument(name, 'Branch name')])

    def rename_branch(self, old, new):
        self.run(['check-ref-format', '--branch', argument(new, 'Branch name')])
        return self.run(['branch', '-m', argument(old), new])

    def set_upstream(self, branch, ref):
        if not ref.startswith('refs/remotes/') or ref.endswith('/HEAD'):
            raise GitError('Choose an explicit remote branch as the upstream.')
        return self.run(['branch', '--set-upstream-to=' + argument(ref), argument(branch)])

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

    def push(self, remote=None, branch=None, *, force_with_lease=False):
        self.check_submodules()
        args = ['push', '--progress', '--no-follow-tags', *(['--tags'] if self.runner.push_tags else []),
                *(['--force-with-lease'] if force_with_lease else [])]
        if remote:
            if not branch: raise GitError('Select a branch to publish.')
            self.run(['check-ref-format', 'refs/heads/' + argument(branch)])
            args += ['--set-upstream', argument(remote), f'HEAD:refs/heads/{branch}']
        else:
            status = self.status()
            if status.branch == '(detached)' or not status.upstream:
                raise GitError('Publish the current branch to configure its upstream before pushing.')
            # An unqualified push may obey push.default=matching or push refspecs
            # and update other branches. This action always targets this branch's
            # configured upstream explicitly.
            remote = self.run(['config', '--get', f'branch.{status.branch}.remote']).stdout.decode('utf-8', 'replace').strip()
            target = self.run(['config', '--get', f'branch.{status.branch}.merge']).stdout.decode('utf-8', 'replace').strip()
            if not target.startswith('refs/heads/') or '\n' in target:
                raise GitError('This branch does not have one branch upstream configured.')
            args += [argument(remote, 'Upstream remote'), f'HEAD:{target}']
        return self.run(args, timeout=1800)

    def push_current_to_origin(self, expected_branch):
        if self.status().branch != expected_branch or expected_branch == '(detached)':
            raise GitError('The branch changed after committing. The commit is saved; push it manually.')
        return self.push('origin', expected_branch)

    def stash_save(self, message, include_untracked=False):
        return self.run(['stash', 'push', *(['--include-untracked'] if include_untracked else []), '-m', message or 'Logistics stash'])

    def stash_action(self, action, ref):
        if action not in ('apply', 'pop', 'drop'): raise GitError('Invalid stash action.')
        if not re.fullmatch(r'stash@\{\d+\}', ref): raise GitError('Invalid stash reference.')
        return self.run(['stash', action, ref])

    def discard(self, paths):
        if not paths: raise GitError('Select tracked files to discard.')
        self.backup_files(paths)
        return self.run(['restore', '--worktree', '--', *paths])

    def merge(self, ref):
        return self.run(['merge', '--no-edit', *(['--no-ff'] if self.runner.no_ff else []), argument(ref)], timeout=600)

    def check_submodules(self):
        if self.runner.check_submodules and any(change.submodule.startswith('S') and change.submodule[2:] != '..' for change in self.status().changes):
            raise GitError('A submodule has uncommitted changes. Commit or discard them in the submodule before committing or pushing the parent.')

    def backup_files(self, paths):
        if not self.runner.keep_backups: return
        from uuid import uuid4
        import json
        import shutil
        root = self.root().resolve()
        metadata = self.run(['rev-parse', '--path-format=absolute', '--git-path', 'logistics-backups']).stdout.decode().strip()
        folder = Path(metadata) / uuid4().hex
        folder.mkdir(parents=True, exist_ok=False, mode=0o700)
        manifest = {}
        for index, relative in enumerate(paths):
            path = root / relative
            if path.is_symlink() or not path.resolve().is_relative_to(root): raise GitError('Backups require files inside this repository.')
            if path.is_file():
                name = f'{index}.backup'; shutil.copy2(path, folder / name); (folder / name).chmod(0o600); manifest[name] = relative
        (folder / 'paths.json').write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding='utf-8')

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

    def update_submodules(self, recursive=True):
        return self.run(['submodule', 'update', '--init', *(['--recursive'] if recursive else []), '--progress'], timeout=1800)

    def add_submodule(self, url, path):
        return self.run(['submodule', 'add', '--', remote_url(url), argument(path, 'Submodule path')], timeout=1800)

    def subtree(self, action, prefix, url, branch, squash=False):
        if action not in ('add', 'pull', 'push'): raise GitError('Invalid subtree action.')
        prefix = argument(prefix, 'Subtree prefix')
        if Path(prefix).is_absolute() or '..' in Path(prefix).parts: raise GitError('Use a relative prefix within the repository.')
        args = ['subtree', action, f'--prefix={prefix}', remote_url(url), argument(branch)]
        if squash and action != 'push': args.append('--squash')
        return self.run(args, timeout=1800)


    def _check_text_attributes(self, relative_path):
        attrs = self.run(['check-attr', '-z', 'filter', 'working-tree-encoding', '--', relative_path]).stdout.split(b'\0')
        if any(attrs[i] not in (b'unspecified', b'unset') for i in range(2, len(attrs)-1, 3)):
            raise GitError('This file uses a Git conversion filter or working-tree encoding; use its configured merge tool or unified preview.')

    def comparison_inputs(self, relative_path, *, staged=False):
        """Read full text snapshots for review; never reconstruct files from a patch."""
        from commonUtils.persistence.text import decode_bytes, read_text_file
        from commonUtils.persistence.merge import bounded
        root = self.root().resolve()
        path = root / relative_path
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise GitError('Comparison supports regular text files within the repository.')
        self._check_text_attributes(relative_path)
        entries = self.run(['ls-files', '--stage', '-z', '--', relative_path]).stdout.split(b'\0')
        index = ''
        for entry in filter(None, entries):
            metadata, _, name = entry.partition(b'\t')
            mode, oid, stage = metadata.split()
            if stage != b'0' or mode not in (b'100644', b'100755'):
                raise GitError('Use Resolve conflict for unmerged files; submodules and symlinks use the unified preview.')
            data = self.run(['cat-file', 'blob', oid.decode('ascii')], limit=1024*1024)
            if data.truncated: raise GitError('Comparison exceeds the 1 MiB limit.')
            index = decode_bytes(data.stdout).text
        if staged:
            head = ''
            if self.status().oid != '(initial)':
                tree = self.run(['ls-tree', '-z', 'HEAD', '--', relative_path]).stdout
                if tree:
                    metadata = tree.split(b'\t', 1)[0]
                    mode, kind, oid = metadata.split()
                    if mode not in (b'100644', b'100755'): raise GitError('Use the unified preview for this file type.')
                    data = self.run(['cat-file', 'blob', oid.decode('ascii')], limit=1024*1024)
                    if data.truncated: raise GitError('Comparison exceeds the 1 MiB limit.')
                    head = decode_bytes(data.stdout).text
            left, right = head, index
        else:
            left, right = index, read_text_file(path).text if path.exists() else ''
        bounded(left); bounded(right)
        return left, right

    def conflict_inputs(self, relative_path):
        from commonUtils.persistence.text import decode_bytes, read_text_file, TextSnapshot
        root = self.root().resolve()
        path = root / relative_path
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise GitError('Merge supports regular files within the repository.')
        state = self.run(['ls-files', '--unmerged', '-z', '--', relative_path]).stdout
        stages = {}
        for record in state.split(b'\0'):
            if not record:
                continue
            metadata, _, name = record.partition(b'\t')
            mode, oid, stage = metadata.split()
            if mode not in (b'100644', b'100755'):
                raise GitError('Resolve symbolic links and submodules with Git or the file browser.')
            stages[int(stage)] = oid.decode('ascii')
        if not stages:
            raise GitError('This file no longer has unresolved index entries. Refresh the repository.')
        if 2 not in stages or 3 not in stages:
            raise GitError('This is a delete/modify conflict. Choose whether to keep or delete the file with Git, then stage it.')
        self._check_text_attributes(relative_path)
        texts = []
        for stage in (1, 2, 3):
            if stage not in stages:
                texts.append(''); continue
            result = self.run(['cat-file', 'blob', stages[stage]], limit=1024*1024)
            if result.truncated:
                raise GitError('Merge input exceeds the 1 MiB limit.')
            texts.append(decode_bytes(result.stdout).text)
        working = read_text_file(path) if path.exists() else TextSnapshot(path, b'', '')
        return ConflictInputs(path, relative_path, state, *texts, working, path.exists(), self.operation())


    def save_conflict(self, inputs, text, *, stage=False):
        from commonUtils.persistence.text import write_text_file
        from commonUtils.persistence.merge import bounded
        bounded(text)
        self._check_text_attributes(inputs.relative_path)
        root = self.root().resolve()
        if inputs.path.is_symlink() or not inputs.path.resolve().is_relative_to(root):
            raise GitError("The working file location changed. Reopen the merge.")
        current = self.run(['ls-files', '--unmerged', '-z', '--', inputs.relative_path]).stdout
        if current != inputs.index_state:
            raise GitError('The Git conflict changed. Reopen the merge before applying.')
        content = inputs.working.encode(text)
        write_text_file(inputs.path, content, expected=inputs.working.original if inputs.existed else None)
        if stage:
            current = self.run(['ls-files', '--unmerged', '-z', '--', inputs.relative_path]).stdout
            if current != inputs.index_state or inputs.path.read_bytes() != content:
                raise GitError('Result saved, but the file or index changed before staging. Review it and stage manually.')
            self.stage([inputs.relative_path])
        return inputs.path


def clone(url, destination, runner=None, recursive=False, branch=''):
    runner = runner or GitRunner()
    runner.version()
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
