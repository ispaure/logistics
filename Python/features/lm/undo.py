"""Conservative reverse application of saved unified patches, without Git commands."""
import re


_HEADER = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n$')


def reverse_patch(current, patch):
    """Require unique exact post-edit hunk context; never fuzz, reset or overwrite conflicts.

    Match every hunk against the same current text before replacing any of them.
    This preserves unrelated later text, including line shifts, while refusing
    overlapping edits, ambiguous repeated blocks and malformed saved patches.
    """
    lines = patch.splitlines(keepends=True)
    if len(lines) < 3 or not lines[0].startswith('--- ') or not lines[1].startswith('+++ '):
        raise ValueError('The saved patch is unavailable or invalid.')
    hunks = []
    index = 2
    while index < len(lines):
        match = _HEADER.fullmatch(lines[index])
        if match is None:
            raise ValueError('Invalid saved patch hunk.')
        old_count, new_count = int(match[2] or 1), int(match[4] or 1)
        index += 1
        body = []
        while index < len(lines) and not lines[index].startswith('@@ '):
            line = lines[index]
            if line == '\\ No newline at end of file\n':
                if not body or not body[-1][1].endswith('\n'):
                    raise ValueError('Invalid saved newline marker.')
                kind, text = body[-1]
                body[-1] = (kind, text[:-1])
            elif line[:1] in (' ', '+', '-'):
                body.append((line[0], line[1:]))
            else:
                raise ValueError('Invalid saved patch content.')
            index += 1
        before = [text for kind, text in body if kind != '+']
        after = [text for kind, text in body if kind != '-']
        if len(before) != old_count or len(after) != new_count or not any(kind != ' ' for kind, _ in body):
            raise ValueError('Incomplete saved patch.')
        hunks.append((before, after))
    source = current.splitlines(keepends=True)
    offsets, offset = {}, 0
    for line_number, line in enumerate(source):
        offsets[offset] = line_number
        offset += len(line)
    offsets[offset] = len(source)
    replacements = []
    for before, after in hunks:
        if not after:
            # A deletion without surviving context can only be reversed safely
            # when the complete current file is still empty.
            positions = [0] if not source else []
        else:
            needle, positions, offset = ''.join(after), [], 0
            while len(positions) < 2:
                found = current.find(needle, offset)
                if found < 0:
                    break
                end = found + len(needle)
                if found in offsets and end in offsets:
                    positions.append(offsets[found])
                offset = found + 1
        if len(positions) != 1:
            raise ValueError('Later edits or ambiguous text conflict with this turn. No matching hunk can be safely undone.')
        start = positions[0]
        replacements.append((start, start + len(after), before))
    if not replacements:
        raise ValueError('The saved patch contains no changes.')
    if any(left[1] > right[0] or left[0] == right[0]
           for left, right in zip(replacements, replacements[1:])):
        raise ValueError('Saved hunks overlap or no longer appear in their original order.')
    for start, end, before in reversed(replacements):
        source[start:end] = before
    return ''.join(source)
