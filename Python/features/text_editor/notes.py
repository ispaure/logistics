"""Bounded provider-backed Notes Libraries with on-demand note-link lookup."""
import posixpath
from pathlib import PurePosixPath
from services.documents.storage import DocumentResource
from .access import can_write

MARKDOWN = {'.md', '.markdown'}
MAX_NOTE = 2 * 1024 * 1024


def operation(provider, cancelled):
    from services.documents.storage import document_operation
    return document_operation(provider, cancelled)


def vault_root(provider, directory, rows):
    provider = getattr(provider, 'provider', provider)
    if not callable(getattr(provider, 'relative', None)):
        return None
    directory = provider.relative(directory)
    marker = posixpath.join(directory, '.obsidian')
    return directory if any(row['path'] == marker and row['directory'] for row in rows) else None


class NotesLibrary:
    def __init__(self, provider, root=''):
        self.provider, self.root = provider, provider.relative(root)

    @property
    def writable(self):
        return can_write(provider=self.provider)

    def contained(self, path):
        path = self.provider.relative(path)
        if self.root and path != self.root and not path.startswith(self.root + '/'):
            raise ValueError('That note is outside this Notes Library.')
        parts = PurePosixPath(path).relative_to(self.root or '.').parts
        if any(part.startswith('.') for part in parts):
            raise ValueError('Hidden configuration is not a note.')
        return path

    def folders(self, path, *, cancelled=lambda: False):
        path = self.contained(path)
        with operation(self.provider, cancelled):
            rows = self.provider.list(path, cancelled=cancelled)
        if len(rows) > 10000:
            raise ValueError('Folder exceeds the 10,000-entry limit.')
        return self.visible_rows(rows)

    @staticmethod
    def visible_rows(rows):
        if len(rows) > 10000:
            raise ValueError('Folder exceeds the 10,000-entry limit.')
        return sorted((row for row in rows if not row['name'].startswith('.')
            and (row['directory'] or PurePosixPath(row['name']).suffix.lower() in MARKDOWN)),
            key=lambda row: (not row['directory'], row['name'].casefold()))

    def entry(self, path):
        if hasattr(self.provider, 'stat') and not hasattr(self.provider, 'entry'):
            info = self.provider.stat(path)
            return dict(size=info['Size'], directory=info['IsDir'], revision=self.provider._revision(info))
        return self.provider.entry(path)

    def read(self, path, *, cancelled=lambda: False):
        path = self.contained(path)
        if PurePosixPath(path).suffix.lower() not in MARKDOWN:
            raise ValueError('Choose a Markdown note.')
        before = self.entry(path)
        if before['directory'] or not 0 <= before['size'] <= MAX_NOTE + 4096:
            raise ValueError('Note exceeds the 2 MiB preview limit.')
        with DocumentResource(self.provider, path, max_bytes=MAX_NOTE, independent=False) as resource:
            data = resource.read(cancelled=cancelled)
        data.decode('utf-8-sig')
        return data

    def create(self, name, parent=None, *, cancelled=lambda: False):
        from .names import document_name
        if not self.writable:
            raise ValueError('This Notes Library is read-only.')
        name = document_name(name)
        if PurePosixPath(name).suffix.lower() not in MARKDOWN:
            name += '.md'
        path = self.contained(posixpath.join(self.root if parent is None else parent, name))
        DocumentResource.publish(self.provider, path, b'', max_bytes=MAX_NOTE, cancelled=cancelled)
        return path

    def supports(self, action):
        from commonUtils.runtime.resources.provider import capabilities
        return self.writable and getattr(capabilities(self.provider), action)

    def create_folder(self, name, parent=None, *, cancelled=lambda: False):
        from .names import document_name
        if not self.supports('create'):
            raise ValueError('This Notes Library cannot create folders.')
        path = self.contained(posixpath.join(self.root if parent is None else parent, document_name(name)))
        from services.documents.storage import create_document_folder
        create_document_folder(self.provider, path, cancelled=cancelled)
        return path

    def move(self, source, destination, *, cancelled=lambda: False):
        if not self.supports('rename'):
            raise ValueError('This Notes Library cannot move notes.')
        source, destination = self.contained(source), self.contained(destination)
        if source == self.root or destination == self.root:
            raise ValueError('Cannot move or replace the Notes Library root.')
        if destination == source or destination.startswith(source + '/'):
            raise ValueError('Choose a different destination outside the selected folder.')
        with operation(self.provider, cancelled):
            entry = self.entry(source)
            if not entry['directory'] and (PurePosixPath(source).suffix.lower() not in MARKDOWN
                                           or PurePosixPath(destination).suffix.lower() not in MARKDOWN):
                raise ValueError('Keep a Markdown filename extension.')
            from services.documents.storage import move_document_resource
            move_document_resource(self.provider, source, destination, cancelled=cancelled)
        return destination

    def image_source(self, path):
        from commonUtils.formats.markdown.image_sources import folder_image_source
        from types import SimpleNamespace
        # Keep the library adapter for providers exposing entry or stat.
        source = SimpleNamespace(relative=self.provider.relative, entry=self.entry, open=self.provider.open)
        return folder_image_source(source, self.contained(path), root=self.root)

    def link(self, current, target, *, cancelled=lambda: False):
        from urllib.parse import unquote, urlsplit
        from commonUtils.runtime.operations import check_cancelled
        link = urlsplit(target)
        if link.scheme or link.netloc or link.query or link.path.startswith(('/', '\\')) or '\\' in link.path:
            raise ValueError('Choose a note inside this Notes Library.')
        current = self.contained(current)
        name = unquote(link.path)
        if not name:
            return current, link.fragment
        if not PurePosixPath(name).suffix:
            name += '.md'
        path = self.contained(posixpath.normpath(posixpath.join(posixpath.dirname(current), name)))
        if PurePosixPath(path).suffix.lower() not in MARKDOWN:
            raise ValueError('Choose a Markdown note.')
        with operation(self.provider, cancelled):
            listings = {}
            count = 0
            def listing(folder):
                nonlocal count
                check_cancelled(cancelled)
                if folder not in listings:
                    rows = self.provider.list(folder, cancelled=cancelled)
                    count += len(rows)
                    if count > 10000:
                        raise ValueError('Note lookup exceeds the 10,000-entry limit. Use an explicit note path.')
                    listings[folder] = rows
                return listings[folder]

            def exists(candidate):
                folder = self.root
                parts = PurePosixPath(candidate).relative_to(self.root or '.').parts
                for index, part in enumerate(parts):
                    row = next((row for row in listing(folder) if row['name'] == part), None)
                    if row is None:
                        return False
                    if index == len(parts) - 1:
                        return not row['directory']
                    if not row['directory']:
                        return False
                    folder = self.contained(row['path'])
                return False

            candidates = [path]
            # Explicit ../ paths retain their relative meaning. Other wiki paths
            # may be relative to either the current note or the vault root.
            if not any(part in {'.', '..'} for part in name.split('/')):
                candidates.append(self.contained(posixpath.join(self.root, name)))
            for candidate in dict.fromkeys(candidates):
                check_cancelled(cancelled)
                if exists(candidate):
                    return candidate, link.fragment
            if any(part in {'.', '..'} for part in name.split('/')):
                raise ValueError('Note not found in this Notes Library.')
            matches, pending, seen = [], [self.root], set()
            while pending:
                check_cancelled(cancelled)
                folder = pending.pop()
                if folder in seen:
                    continue
                seen.add(folder)
                rows = listing(folder)
                for row in rows:
                    check_cancelled(cancelled)
                    if row['name'].startswith('.'):
                        continue
                    child = self.contained(row['path'])
                    if row['directory']:
                        pending.append(child)
                    elif child.endswith('/' + name) or child == name:
                        matches.append(child)
            if len(matches) == 1:
                return matches[0], link.fragment
            if matches:
                raise ValueError('Several notes match this link. Use a path from the Notes Library root.')
            raise ValueError('Note not found in this Notes Library.')
