"""Bounded, cancellable local connection scans; no persistent plaintext index."""
import posixpath
from pathlib import PurePosixPath
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit
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
        url = urlsplit(target)
        name = unquote(url.path)
        if url.scheme or url.netloc or url.query or name.startswith('/') or '\\' in name:
            return None
        if not name:
            return source
        if not PurePosixPath(name).suffix:
            name += '.md'
        explicit = any(part in {'.', '..'} for part in name.split('/'))
        candidates = [posixpath.normpath(posixpath.join(posixpath.dirname(source), name))]
        if not explicit:
            candidates.append(posixpath.join(library.root, name))
        for candidate in candidates:
            if candidate in paths:
                return candidate
        matches = suffixes.get(name, ()) if not explicit else ()
        return next(iter(matches)) if len(matches) == 1 else None

    incoming, outgoing, unresolved = set(), set(), set()
    total = words = characters = 0
    for path in sorted(notes):
        check_cancelled(cancelled)
        data = library.read(path, cancelled=cancelled)
        total += len(data)
        if total > 64 * 1024 * 1024:
            raise ValueError('Library exceeds the 64 MiB connection scan limit.')
        text = data.decode('utf-8-sig')
        if path == current:
            words, characters = len(text.split()), len(text)
        for target in Targets(text).targets:
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
