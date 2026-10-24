"""Bounded provider-backed Notes Libraries; no recursive discovery or disk cache."""
import posixpath
from pathlib import PurePosixPath
from contextlib import nullcontext
from commonUtils.runtime.streams import read_up_to
from .access import can_write

MARKDOWN = {'.md', '.markdown'}
MAX_NOTE = 2 * 1024 * 1024


def operation(provider, cancelled):
    return provider.operation(cancelled) if hasattr(provider, 'operation') else nullcontext()


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
        self.remote = bool(getattr(provider, 'remote_storage', False))

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
        with operation(self.provider, cancelled):
            before = self.entry(path)
            if cancelled():
                raise ValueError('Notes Library closed.')
            if before['directory'] or not 0 <= before['size'] <= MAX_NOTE + 4096:
                raise ValueError('Note exceeds the 2 MiB preview limit.')
            with self.provider.open(path) as stream:
                data = read_up_to(stream, MAX_NOTE + 1)
            if len(data) > MAX_NOTE or cancelled() or self.entry(path) != before:
                raise ValueError('Note changed or is too large. Reopen it.')
        data.decode('utf-8-sig')
        return data

    def create(self, name, parent=None, *, cancelled=lambda: False):
        from io import BytesIO
        from .names import document_name
        if not self.writable:
            raise ValueError('Remote Notes Libraries are read-only.')
        name = document_name(name)
        if PurePosixPath(name).suffix.lower() not in MARKDOWN:
            name += '.md'
        path = self.contained(posixpath.join(self.root if parent is None else parent, name))
        with operation(self.provider, cancelled):
            self.provider.create_file(path, BytesIO(b''), cancelled=cancelled)
        return path

    def image_source(self, path):
        from urllib.parse import unquote, urlsplit
        from commonUtils.formats.markdown.image_sources import folder_image_source
        load = folder_image_source(self.provider, self.contained(path))
        def image(target):
            parsed = urlsplit(target)
            self.contained(posixpath.normpath(posixpath.join(posixpath.dirname(path), unquote(parsed.path))))
            return load(target)
        return image

    def link(self, current, target):
        from urllib.parse import unquote, urlsplit
        link = urlsplit(target)
        if link.scheme or link.netloc or link.query or link.path.startswith(('/', '\\')) or '\\' in link.path:
            raise ValueError('Choose a note inside this Notes Library.')
        path = self.contained(posixpath.normpath(posixpath.join(posixpath.dirname(current), unquote(link.path))))
        if PurePosixPath(path).suffix.lower() not in MARKDOWN:
            raise ValueError('Choose a Markdown note.')
        return path, link.fragment
