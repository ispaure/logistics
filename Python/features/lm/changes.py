"""Turn-local text snapshots and immutable unified patches; no Git execution."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

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
