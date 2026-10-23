"""Read-only Git status snapshots for the project tree, without Git UI ownership."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic
from commonUtils.ui import pyside as qt

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='ide-git-status')
COLORS = {'add': '#009e73', 'modify': '#408bd6', 'delete': '#d55e00',
          'rename': '#a778cf', 'conflict': '#d88928'}
STATUS_CODES = {'add': 'A', 'modify': 'M', 'delete': 'D', 'rename': 'R', 'conflict': '!'}


def read_status(project_root, cancel):
    from features.git.editor_baseline import editor_runner
    from features.git.repository import Repository
    from features.git.models import parse_status, status_label
    runner = editor_runner(5, cancel)
    root = Repository(project_root, runner=runner).root()
    pending, records, visited = [root], [], set()
    deadline = monotonic() + 5
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        if len(visited) >= 16 or monotonic() >= deadline:
            break
        visited.add(current)
        result = runner.run(['--no-optional-locks', 'status', '--porcelain=v2', '-z',
                             '--untracked-files=all'], cwd=current,
                            timeout=max(.1, deadline - monotonic()))
        if result.truncated:
            raise ValueError('Git status exceeds the project tree limit')
        for change in parse_status(result.stdout).changes:
            path = current / change.path
            records.append((path, change))
            # The parent reports only the submodule folder. Its own Git index
            # is authoritative for individual modified/new files inside it.
            if (change.submodule.startswith('S') and path.is_relative_to(project_root)
                    and (path / '.git').exists() and not path.is_symlink()):
                pending.append(path)
    changes = {}
    priorities = {'add': 0, 'rename': 1, 'delete': 2, 'modify': 3, 'conflict': 4}
    for path, change in records:
        if not path.is_relative_to(project_root):
            continue
        codes = change.index + change.worktree
        kind = ('conflict' if change.conflict else 'delete' if 'D' in codes else
                'modify' if 'M' in codes or 'T' in codes else 'rename' if 'R' in codes else 'add')
        label = status_label(STATUS_CODES[kind])
        if change.index == '?':
            label += ' (untracked)'
        elif not change.conflict:
            label += ' (staged and unstaged)' if change.staged and change.unstaged else \
                     ' (staged)' if change.staged else ' (unstaged)'
        changes[path] = kind, label
        parent = path.parent
        while parent.is_relative_to(project_root):
            previous = changes.get(parent)
            if previous is None or priorities[kind] > priorities[previous[0]]:
                changes[parent] = kind, 'Contains Git changes'
            if parent == project_root:
                break
            parent = parent.parent
    return changes


class ProjectGitStatus(qt.QObject):
    def __init__(self, browser):
        super().__init__(browser)
        self.browser = browser
        self.future = None
        self.pending = []
        self.cancel = Event()
        cancel, pending = self.cancel, self.pending
        def stop():
            cancel.set()
            if pending:
                pending[0].cancel()
        self.destroyed.connect(stop)
        self.timer = qt.QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.poll = qt.QTimer(self)
        self.poll.setInterval(100)
        self.poll.timeout.connect(self.finished)
        self.refresh()

    def refresh(self):
        if (self.future is not None or self.cancel.is_set()
                or getattr(self.browser.workspace, 'closing', False)):
            return
        self.root = self.browser.project.root
        try:
            self.future = _executor.submit(read_status, self.root, self.cancel)
        except (OSError, RuntimeError):
            self._publish({})
            return
        self.pending[:] = [self.future]
        self.poll.start()

    def stop(self):
        self.cancel.set()
        self.timer.stop()
        self.poll.stop()
        if self.future is not None:
            self.future.cancel()

    def finished(self):
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        self.pending.clear()
        self.poll.stop()
        try:
            changes = future.result()
        except (ImportError, OSError, ValueError, RuntimeError):
            changes = {}
        if self.root != self.browser.project.root:
            self.refresh()
            return
        self._publish(changes)

    def _publish(self, changes):
        if changes != self.browser.proxy.git_changes:
            self.browser.proxy.git_changes = changes
            self.browser.tree.viewport().update()
