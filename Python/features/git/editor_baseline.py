"""Read-only editor baselines independent of repository registration and Git UI."""
from pathlib import Path
from commonUtils.persistence.text import decode_bytes
from .runner import GitRunner, GitError


def index_baseline(path, encoding):
    runner = GitRunner(timeout=3)
    path = Path(path).resolve()
    root = runner.run(['rev-parse', '--show-toplevel'], cwd=path.parent)
    root = Path(root.stdout.decode().rstrip('\n'))
    relative = path.relative_to(root).as_posix()
    from .repository import Repository
    Repository(root, runner=runner)._check_text_attributes(relative)
    result = runner.run(['ls-files', '--stage', '-z', '--', relative], cwd=root)
    entries = result.stdout.split(b'\0')
    entry = next((row for row in entries if row and row.split(b'\t', 1)[0].endswith(b' 0')), None)
    if entry is None:
        if any(entries):
            raise GitError('Unmerged index')
        return '', 'Git index (untracked file)'
    mode, oid, stage = entry.split(b'\t', 1)[0].split()
    if mode not in (b'100644', b'100755'):
        raise GitError('Not a regular text file')
    data = runner.run(['cat-file', 'blob', oid.decode('ascii')], cwd=root, limit=1024 * 1024)
    if data.truncated:
        raise GitError('Baseline exceeds gutter limit')
    return decode_bytes(data.stdout, encoding=encoding).text, 'Git index (unstaged changes)'
