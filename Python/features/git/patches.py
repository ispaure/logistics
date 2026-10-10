"""Extract one complete Git-generated hunk without decoding its file contents."""
import re
from .runner import GitError


def single_hunk(patch, index):
    if len(re.findall(rb'^diff --git ', patch, re.M)) != 1 or any(line.startswith((b'old mode ', b'new mode ', b'rename ', b'copy '))
                                               for line in patch.splitlines()):
        raise GitError('Use file actions for renames, copies or permission changes.')
    starts = [match.start() for match in re.finditer(rb'^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@[^\n]*\n', patch, re.M)]
    if not isinstance(index, int) or not 0 <= index < len(starts):
        raise GitError('The selected hunk is unavailable. Refresh the preview.')
    return patch[:starts[0]] + patch[starts[index]:starts[index + 1] if index + 1 < len(starts) else len(patch)]
