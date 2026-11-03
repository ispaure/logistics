"""Bounded provider-backed Notes Libraries with on-demand note-link lookup."""
import posixpath
from pathlib import PurePosixPath
from threading import RLock
from services.documents.storage import DocumentResource
from services.documents.access import can_write

MARKDOWN = {'.md', '.markdown'}
TEXT = {'.json', '.jsonc', '.js', '.mjs', '.cjs', '.css', '.txt', '.csv',
        '.yaml', '.yml', '.toml', '.ini', '.xml', '.html', '.py', '.ts'}
DOCUMENTS = MARKDOWN | TEXT | {'.rmdoc'}
MAX_NOTE = 2 * 1024 * 1024


def document_kind(path):
    """The library's shared, filename-only document routing contract."""
    suffix = PurePosixPath(path).suffix.lower()
    return 'markdown' if suffix in MARKDOWN else 'text' if suffix in TEXT else 'notebook' if suffix == '.rmdoc' else None


def library_name(provider, root='', fallback='Notes Library'):
    if root:
        return PurePosixPath(root).name
    if getattr(provider, 'remote', None):
        from services.documents.storage import display_path
        return display_path(provider, '').rstrip(':')
    connection = getattr(provider, 'connection', None)
    if getattr(connection, 'remote', None):
        return connection.remote.rstrip(':')
    return provider.root.name or fallback


def operation(provider, cancelled):
    from services.documents.storage import document_operation
    return document_operation(provider, cancelled)


def local_library(provider):
    from services.documents.storage import document_remote
    return not document_remote(provider)


def vault_root(provider, directory, rows):
    if not local_library(provider):
        return None
    provider = getattr(provider, 'provider', provider)
    if not callable(getattr(provider, 'relative', None)):
        return None
    directory = provider.relative(directory)
    marker = posixpath.join(directory, '.obsidian')
    return directory if any(row['path'] == marker and row['directory'] for row in rows) else None


class NotesLibrary:
    def __init__(self, provider, root=''):
        if not local_library(provider):
            raise ValueError('Notes Library requires a local copy. Download or sync this folder first.')
        self.provider, self.root = provider, provider.relative(root)
        self._link_folders = {}
        self._link_lock = RLock()
        self._links_closed = False
        self._media = {}

    def close(self):
        """Retire in-memory names, including work completing after revocation."""
        with self._link_lock:
            self._links_closed = True
            self._link_folders.clear()
            media, self._media = self._media, {}
        for source in media.values():
            source.close()

    def _link_listing(self, folder, cancelled):
        """Reuse names only while the validated local directory is unchanged."""
        from commonUtils.runtime.operations import check_cancelled
        check_cancelled(lambda: self._links_closed or cancelled())
        locate = getattr(self.provider, 'transfer_location', None)
        if not callable(locate):
            return self.provider.list(folder, cancelled=cancelled)

        def revision():
            info = locate(folder, directory=True).stat()
            return info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns

        before = revision()
        with self._link_lock:
            check_cancelled(lambda: self._links_closed or cancelled())
            cached = self._link_folders.get(folder)
        if cached is not None and cached[0] == before:
            return cached[1]
        rows = self.provider.list(folder, cancelled=cancelled)
        check_cancelled(cancelled)
        # Do not keep stale size, content revision or modification metadata.
        names = [dict(name=row['name'], path=row['path'], directory=row['directory']) for row in rows]
        if revision() == before and len(names) <= 10000:
            with self._link_lock:
                check_cancelled(lambda: self._links_closed or cancelled())
                if sum(len(value[1]) for value in self._link_folders.values()) + len(names) > 10000:
                    self._link_folders.clear()
                self._link_folders[folder] = before, names
        return names

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
        return sorted((row for row in rows if not row['name'].startswith('.')),
            key=lambda row: (not row['directory'], row['name'].casefold()))

    def entry(self, path):
        if hasattr(self.provider, 'stat') and not hasattr(self.provider, 'entry'):
            info = self.provider.stat(path)
            return dict(size=info['Size'], directory=info['IsDir'], revision=self.provider._revision(info))
        return self.provider.entry(path)

    def folder_pages(self, rows, *, cancelled=lambda: False):
        """Resolve landing notes in one bounded provider batch when available."""
        folders = [self.contained(row['path']) for row in rows if row['directory']]
        paths = [self.contained(posixpath.join(folder, PurePosixPath(folder).name + '.md'))
                 for folder in folders]
        probe = getattr(self.provider, 'existing_files', None)
        if callable(probe):
            with operation(self.provider, cancelled):
                existing = probe(paths, cancelled=cancelled)
            return {folder: path if path in existing else None for folder, path in zip(folders, paths)}
        return {folder: self.folder_page(folder, cancelled=cancelled) for folder in folders}

    def folder_page(self, folder, *, cancelled=lambda: False):
        """Probe only the conventional landing note, without listing descendants."""
        folder = self.contained(folder)
        path = self.contained(posixpath.join(folder, PurePosixPath(folder).name + '.md'))
        try:
            with operation(self.provider, cancelled):
                info = self.entry(path)
            return None if info.get('directory', False) else path
        except (OSError, ValueError):
            return None

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

    def load_note(self, path, *, current='', resolve_link=False, cancelled=lambda: False,
                  stage=lambda message: None):
        """Shared finding/reading stages; platform hosts own rendering/publication."""
        from commonUtils.runtime.operations import check_cancelled
        fragment = ''
        if resolve_link:
            stage('Finding file…')
            path, fragment = self.link(current, path, cancelled=cancelled)
        else:
            path = self.contained(path)
        check_cancelled(cancelled)
        stage('Reading ' + PurePosixPath(path).name + '…')
        data = self.read(path, cancelled=cancelled) if document_kind(path) == 'markdown' else None
        check_cancelled(cancelled)
        return path, fragment, data

    def read_text(self, path, *, cancelled=lambda: False):
        """Bounded content search for the same source types shown in Files."""
        from commonUtils.persistence.text import decode_bytes
        path = self.contained(path)
        if document_kind(path) not in ('markdown', 'text'):
            return ''
        with DocumentResource(self.provider, path, max_bytes=MAX_NOTE, independent=False) as resource:
            return decode_bytes(resource.read(cancelled=cancelled)).text

    def create(self, name, parent=None, *, extension='md', cancelled=lambda: False):
        from services.documents.names import document_name
        if not self.writable:
            raise ValueError('This Notes Library is read-only.')
        name = document_name(name)
        if extension not in ('md', 'rmdoc'):
            raise ValueError('Choose Markdown or Remarkable Document.')
        suffixes = MARKDOWN if extension == 'md' else {'.rmdoc'}
        if PurePosixPath(name).suffix.lower() not in suffixes:
            name += '.' + extension
        path = self.contained(posixpath.join(self.root if parent is None else parent, name))
        data, limit = b'', MAX_NOTE
        if extension == 'rmdoc':
            from features.notebooks.notebook import Notebook, MAX_ARCHIVE
            data, limit = Notebook.new(PurePosixPath(name).stem).to_bytes(), MAX_ARCHIVE
        DocumentResource.publish(self.provider, path, data, max_bytes=limit, cancelled=cancelled)
        return path

    def supports(self, action):
        from commonUtils.runtime.resources.provider import capabilities
        return self.writable and getattr(capabilities(self.provider), action)

    def create_folder(self, name, parent=None, *, cancelled=lambda: False):
        from services.documents.names import document_name
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
            if not entry['directory'] and PurePosixPath(destination).suffix.lower() != PurePosixPath(source).suffix.lower():
                raise ValueError('Keep the document filename extension.')
            from services.documents.storage import move_document_resource
            move_document_resource(self.provider, source, destination, cancelled=cancelled)
        return destination

    def image_source(self, path):
        from services.documents.markdown_media import MarkdownMedia
        path = self.contained(path)
        with self._link_lock:
            if self._links_closed:
                raise ValueError('Notes Library closed.')
            if path not in self._media:
                self._media[path] = MarkdownMedia(self.provider, path, root=self.root, entry=self.entry)
            return self._media[path].render_source()

    def release_media(self, current, *, active=lambda: True):
        with self._link_lock:
            if not active():
                return
            retired = [self._media.pop(path) for path in tuple(self._media) if path != current]
        for source in retired:
            source.close()

    def discard_media(self, path, *, active=lambda: True):
        """Retire one abandoned attempt without touching a newer document."""
        with self._link_lock:
            source = self._media.pop(path, None) if active() else None
        if source is not None:
            source.close()

    def link(self, current, target, *, cancelled=lambda: False):
        from urllib.parse import unquote, urlsplit
        from commonUtils.runtime.operations import check_cancelled
        requested_cancelled = cancelled
        cancelled = lambda: self._links_closed or requested_cancelled()
        check_cancelled(cancelled)
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
        if PurePosixPath(path).suffix.lower() not in DOCUMENTS:
            raise ValueError('Choose a supported library document.')
        with operation(self.provider, cancelled):
            listings = {}
            count = 0
            def listing(folder):
                nonlocal count
                check_cancelled(cancelled)
                if folder not in listings:
                    rows = self._link_listing(folder, cancelled)
                    count += len(rows)
                    if count > 10000:
                        raise ValueError('Note lookup exceeds the 10,000-entry limit. Use an explicit note path.')
                    listings[folder] = rows
                return listings[folder]

            def exists(candidate):
                # A rooted provider validates the whole path itself. Listing
                # every ancestor makes a direct link proportional to unrelated
                # siblings (and decrypts their names for encrypted providers).
                check_cancelled(cancelled)
                try:
                    return not self.entry(candidate)['directory']
                except (FileNotFoundError, NotADirectoryError):
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
            find = getattr(self.provider, 'find_note_paths', None)
            if callable(find) and PurePosixPath(name).suffix.lower() in MARKDOWN:
                matches = [self.contained(match) for match in find(name, self.root, cancelled=cancelled)]
                check_cancelled(cancelled)
                if len(matches) == 1:
                    return matches[0], link.fragment
                if matches:
                    raise ValueError('Several notes match this link. Use a path from the Notes Library root.')
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
