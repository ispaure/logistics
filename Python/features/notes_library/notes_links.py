"""Bounded, cancellable local connection scans; no persistent plaintext index."""
from pathlib import PurePosixPath
from html.parser import HTMLParser
from urllib.parse import urlsplit
from .link_policy import resolve_link
from commonUtils.runtime.operations import check_cancelled


class Targets(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.targets = set()
        from commonUtils.ui.native.markdown_preview import markdown_body
        self.feed(markdown_body(text, local_links=True))

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            target = dict(attrs).get('href')
            if target:
                self.targets.add(target)


def outgoing_connections(library, current, *, cancelled=lambda: False, visible=lambda path, **kw: True):
    """Resolve only this note's targets; never read other document bodies."""
    note = library.connection_index.note(library, current, cancelled=cancelled)
    outgoing, unresolved = set(), set()
    for target in note['targets']:
        check_cancelled(cancelled)
        try:
            resolved = library.link(current, target, cancelled=cancelled)[0]
            if resolved != current and visible(resolved, directory=False):
                outgoing.add(resolved)
        except ValueError:
            if not urlsplit(target).scheme:
                unresolved.add(target)
    return dict(outgoing=sorted(outgoing), unresolved=sorted(unresolved),
                words=note['words'], characters=note['characters'])


def connections(library, current, *, cancelled=lambda: False, visible=lambda path, **kw: True):
    """Read at most 5,000 notes / 64 MiB and fail explicitly on incomplete scans."""
    from .notes import MARKDOWN
    pending, seen, paths, notes = [library.root], set(), set(), set()
    entries = 0
    while pending:
        check_cancelled(cancelled)
        folder = pending.pop()
        if folder in seen:
            continue
        seen.add(folder)
        for row in library.folders(folder, cancelled=cancelled):
            entries += 1
            if entries > 10000:
                raise ValueError('Library exceeds the 10,000-entry connection scan limit.')
            path = library.contained(row['path'])
            if not visible(path, directory=row['directory']):
                continue
            if row['directory']:
                pending.append(path)
            else:
                paths.add(path)
                if PurePosixPath(path).suffix.lower() in MARKDOWN:
                    notes.add(path)
                if len(notes) > 5000:
                    raise ValueError('Library exceeds the 5,000-note connection scan limit.')
    suffixes = {}
    for path in paths:
        parts = PurePosixPath(path).relative_to(library.root or '.').parts
        for index in range(len(parts)):
            suffixes.setdefault('/'.join(parts[index:]), set()).add(path)

    def resolve(source, target):
        try:
            return resolve_link(source, target, root=library.root, contained=library.contained,
                exists=paths.__contains__, suffix_matches=lambda name: suffixes.get(name, ()),
                cancelled=cancelled)[0]
        except ValueError:
            return None

    incoming, outgoing, unresolved = set(), set(), set()
    total = words = characters = 0
    for path in sorted(notes):
        check_cancelled(cancelled)
        note = library.connection_index.note(library, path, cancelled=cancelled)
        total += note['size']
        if total > 64 * 1024 * 1024:
            raise ValueError('Library exceeds the 64 MiB connection scan limit.')
        if path == current:
            words, characters = note['words'], note['characters']
        for target in note['targets']:
            check_cancelled(cancelled)
            resolved = resolve(path, target)
            if resolved == current and path != current:
                incoming.add(path)
            if path == current:
                if resolved is not None and resolved != current:
                    outgoing.add(resolved)
                elif resolved is None and not urlsplit(target).scheme:
                    unresolved.add(target)
    return dict(incoming=sorted(incoming), outgoing=sorted(outgoing),
                unresolved=sorted(unresolved), words=words, characters=characters)
