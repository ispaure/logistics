"""Presentation of unified patches, independent of Qt and Git execution."""
from dataclasses import dataclass, field
import re


@dataclass(frozen=True)
class DiffLine:
    text: str
    old: str = ''
    new: str = ''
    kind: str = ''


@dataclass
class DiffView:
    lines: list[DiffLine] = field(default_factory=list)
    hunks: list[tuple[int, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    added: int = 0
    removed: int = 0

    @property
    def text(self):
        return '\n'.join(line.text for line in self.lines)

    @property
    def summary(self):
        counts = f'{len(self.hunks)} hunk{"s" if len(self.hunks) != 1 else ""} · +{self.added} added · −{self.removed} removed' if self.hunks else 'No text changes'
        return ' · '.join([counts, *dict.fromkeys(self.notes)])


def present_diff(patch):
    """Hide patch plumbing, retaining hunk content and exact old/new positions."""
    view = DiffView()
    old = new = old_left = new_left = 0
    in_hunk = False
    recognized = False
    for line in patch.split('\n'):
        match = re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)', line)
        if match:
            recognized = in_hunk = True
            old, old_left, new, new_left = (int(match[1]), int(match[2] or 1), int(match[3]), int(match[4] or 1))
            def span(start, count): return 'empty' if count == 0 else str(start) if count == 1 else f'{start}–{start + count - 1}'
            label = f'Hunk {len(view.hunks) + 1} · Original {span(old, old_left)} → New {span(new, new_left)}'
            if view.lines: view.lines.append(DiffLine(''))
            view.hunks.append((len(view.lines), label))
            view.lines.append(DiffLine(label, kind='hunk'))
        elif in_hunk and line.startswith(('+', '-', ' ')):
            kind = 'add' if line.startswith('+') else 'remove' if line.startswith('-') else ''
            view.lines.append(DiffLine(line, '' if kind == 'add' else str(old), '' if kind == 'remove' else str(new), kind))
            if kind != 'add': old += 1; old_left -= 1
            if kind != 'remove': new += 1; new_left -= 1
            view.added += kind == 'add'
            view.removed += kind == 'remove'
            in_hunk = old_left > 0 or new_left > 0
        elif line.startswith('\\ No newline at end of file'):
            view.lines.append(DiffLine('No newline at end of file', kind='note'))
        elif line.startswith('diff --git '):
            recognized = True
            in_hunk = False
        elif line.startswith('new file mode '): view.notes.append('Added file')
        elif line.startswith('deleted file mode '): view.notes.append('Deleted file')
        elif line.startswith('old mode '): view.notes.append('File permissions changed')
        elif line.startswith('rename from '): view.notes.append('Renamed from ' + line.removeprefix('rename from '))
        elif line.startswith('rename to '): view.notes.append('Renamed to ' + line.removeprefix('rename to '))
        elif line.startswith(('Binary files ', 'GIT binary patch')): view.notes.append('Binary file changed; text preview unavailable')
        elif line.startswith('[') and 'truncated' in line.lower(): view.notes.append(line.strip('[]'))
    if not view.lines:
        view.lines = [DiffLine(view.summary if recognized else patch or 'No differences.')]
    return view
