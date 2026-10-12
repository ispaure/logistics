"""Read-only editor baselines independent of repository registration and Git UI."""
from pathlib import Path
from commonUtils.persistence.text import decode_bytes
from .runner import GitRunner, GitError


def index_baseline(path, encoding, *, cancel=None):
    runner = GitRunner(timeout=3, cancel=cancel)
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


def stage_preview(path, encoding, text, start, end):
    """Review a complete Git hunk only after the entire buffer has been saved."""
    import re
    from commonUtils.persistence.text import read_text_file
    from .repository import Repository
    from .patches import single_hunk
    path = Path(path).resolve()
    if read_text_file(path, encoding=encoding).text != text:
        raise ValueError('Save the buffer before staging, then reopen the hunk.')
    repo = Repository(path.parent, runner=GitRunner(timeout=5))
    root = repo.root().resolve()
    relative = path.relative_to(root).as_posix()
    repo = Repository(root, runner=GitRunner(timeout=5))
    repo._check_text_attributes(relative)
    patch = repo.diff(relative)
    if read_text_file(path, encoding=encoding).text != text:
        raise ValueError('The file changed while loading its patch. Reopen the hunk.')
    for index, match in enumerate(re.finditer(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', patch, re.M)):
        count = int(match[2]) if match[2] is not None else 1
        first = int(match[1]) - (1 if count else 0)
        if first <= start and end <= first + count:
            preview = single_hunk(patch.encode('utf-8'), index).decode('utf-8')
            return str(root), relative, patch, index, preview
    raise ValueError('No saved Git hunk matches this change. Save or refresh first.')


def stage_reviewed(inputs):
    from .repository import Repository
    root, relative, patch, index, _ = inputs
    Repository(root, runner=GitRunner(timeout=5)).apply_hunk(relative, index, patch)
