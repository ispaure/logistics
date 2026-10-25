"""Turn-local text snapshots and immutable unified patches; no Git execution."""
from difflib import unified_diff


def file_change(path, before, after):
    label = path.replace('\n', r'\n').replace('\r', r'\r').replace('\t', r'\t')
    lines = list(unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                              fromfile='a/' + label, tofile='b/' + label))
    added = sum(line.startswith('+') for line in lines[2:])
    removed = sum(line.startswith('-') for line in lines[2:])
    patch = ''.join(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n'
                    for line in lines)
    return dict(path=path, patch=patch, added=added, removed=removed)
