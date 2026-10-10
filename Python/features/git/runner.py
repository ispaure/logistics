"""Binary-safe cancellable execution. Reuses commonUtils process-tree cleanup.

Commands never go through a shell. Temporary output files avoid pipe deadlocks and
unbounded capture; stderr is streamed separately from machine-readable stdout.
"""
from dataclasses import dataclass
import os
import re
import shutil
import subprocess
from tempfile import TemporaryFile
from threading import Event
from time import monotonic

from commonUtils.wrappers.cmdShellWrapper.process import (
    get_process_group_kwargs, terminate_process_tree,
)


def redact(text: str) -> str:
    def url(match):
        scheme, remainder = match.group().split('://', 1)
        authority, separator, path = remainder.partition('/')
        if '@' in authority: authority = '[credentials]@' + authority.rsplit('@', 1)[1]
        value = scheme + '://' + authority + separator + path
        head, query, _ = value.partition('?')
        return head + '?[redacted]' if query else value
    # Consume each complete URL once. An unbounded scheme followed by a required
    # suffix can backtrack quadratically over long non-URL hook output.
    text = re.sub(r'[a-z][a-z0-9+.-]{0,31}://[^\s]+', url, text)
    text = re.sub(r'(?i)(authorization\s*[=:]\s*)(?:bearer|basic)\s+[^\s]+', r'\1[redacted]', text)
    return re.sub(r'(?i)((?:password|access_token|token|authorization)\s*[=:]\s*)[^\s]+',
                  r'\1[redacted]', text)


class GitError(RuntimeError):
    pass


class GitCancelled(GitError):
    pass


@dataclass(frozen=True)
class CommandResult:
    stdout: bytes
    stderr: str
    returncode: int
    truncated: bool = False


class GitRunner:
    def __init__(self, executable='git', *, cancel=None, progress=None, timeout=120):
        self.executable = executable or 'git'
        self.cancel = cancel or Event()
        self.progress = progress or (lambda text: None)
        self.timeout = timeout

    def version(self):
        text = self.run(['--version']).stdout.decode('utf-8', 'replace').strip()
        match = re.search(r'git version (\d+)\.(\d+)', text)
        if not match or tuple(map(int, match.groups())) < (2, 40):
            raise GitError(f'Git 2.40 or newer is required; found {text or "an unknown version"}.')
        return text

    def run(self, arguments, *, cwd=None, check=True, limit=8 * 1024 * 1024, timeout=None):
        if self.cancel.is_set(): raise GitCancelled('Operation cancelled.')
        program = shutil.which(self.executable)
        if program is None:
            raise GitError('Git executable not found. Install Git or set its path in Git settings.')
        command = [program, '--no-pager', '--literal-pathspecs', '-c', 'color.ui=false',
                   '-c', 'core.quotepath=false', *map(str, arguments)]
        env = os.environ.copy()
        # Do not let another repository's shell environment redirect this workspace.
        for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
                    'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_NAMESPACE'):
            env.pop(key, None)
        env.update(GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never', LC_ALL='C')
        # SSH agents and configured credential helpers remain available. Never wait
        # for an invisible terminal prompt; host-key/password setup happens outside.
        if 'GIT_SSH_COMMAND' not in env and 'GIT_SSH' not in env:
            env['GIT_SSH_COMMAND'] = 'ssh -o BatchMode=yes'
        duration = self.timeout if timeout is None else timeout
        started = monotonic()
        with TemporaryFile() as output, TemporaryFile() as errors:
            try:
                process = subprocess.Popen(command, cwd=str(cwd) if cwd else None, env=env,
                                           stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
                                           **get_process_group_kwargs())
            except OSError as exc:
                raise GitError(redact(str(exc))) from exc
            position = 0
            try:
                while True:
                    if self.cancel.is_set(): raise GitCancelled('Operation cancelled. Refresh to inspect repository state.')
                    if duration and monotonic() - started > duration:
                        raise GitError('Git operation timed out. Refresh to inspect repository state.')
                    try:
                        code = process.wait(timeout=.05)
                    except subprocess.TimeoutExpired:
                        code = None
                    # Read through a separate descriptor: seeking the writer's file
                    # offset would corrupt concurrent child writes on POSIX.
                    size = os.fstat(errors.fileno()).st_size
                    if size > position:
                        if hasattr(os, 'pread'):
                            chunk = os.pread(errors.fileno(), min(size - position, 65536), position)
                        else:
                            # Windows doesn't offer pread; stream at completion there.
                            chunk = b''
                        position += len(chunk)
                        if chunk: self.progress(redact(chunk.decode('utf-8', 'replace')))
                    if code is not None: break
            except BaseException:
                terminate_process_tree(process)
                raise
            output.seek(0)
            data = output.read(limit + 1)
            errors.seek(max(0, os.fstat(errors.fileno()).st_size - 65536))
            stderr = redact(errors.read().decode('utf-8', 'replace'))
            if not hasattr(os, 'pread') and stderr: self.progress(stderr)
            result = CommandResult(data[:limit], stderr, code, len(data) > limit)
            if check and code:
                raise GitError(stderr.strip() or f'Git exited with code {code}.')
            if check and result.truncated:
                raise GitError('Git response exceeded the capture limit. Narrow the selection and try again.')
            return result
