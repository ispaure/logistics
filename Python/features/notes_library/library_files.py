"""Rooted library search, daily-note discovery and verified file commands."""
from pathlib import PurePosixPath
from sqlite3 import Error as DatabaseError
from commonUtils.runtime.operations import OperationCancelled, check_cancelled
from commonUtils.search.names import natural_name_key
from commonUtils.search.providers import SearchResult, search_resources
from services.documents.mutations import delete_document_tree, copy_document_tree, copy_document_sibling


def directory_index(library):
    """Admit only known ordinary filesystem providers to the shared cache."""
    from services.documents.locations import ordinary_index_provider

    provider = library.provider
    if not ordinary_index_provider(provider):
        return None
    from commonUtils.filesystem.index import DirectoryCache
    from commonUtils.filesystem.local_access import check_local_path
    folder = provider._locate(library.root)
    check_local_path(folder, recursive=True)
    return DirectoryCache(database=library.index_database), folder


def indexed_children(library, snapshot, folder):
    parent = library.provider._locate(folder)
    entries = snapshot.children(parent, limit=10001)
    return library.visible_rows([
        dict(name=item.path.name, path=library.contained(
             item.path.relative_to(library.provider.root).as_posix()),
             directory=item.directory, size=item.size)
        for item in entries if not item.symlink and not item.path.name.startswith('.')
    ])


def search(library, query, *, include_text, visible=None, cancelled=lambda: False, progress=None,
           collapse_folder_notes=False):
    """Search the library boundary; hosts own scheduling and progress publication."""
    folder_pages = {}

    children = library.search_children

    def listing(folder, *, cancelled):
        try:
            rows = children(folder, cancelled=cancelled)
        except ValueError as error:
            if cancelled():
                raise OperationCancelled() from error
            # Unsupported or oversized folders make the result incomplete.
            raise OSError(str(error)) from error
        if visible is not None:
            rows = [row for row in rows if visible(row['path'], directory=row['directory'])]
        if collapse_folder_notes and folder != library.root:
            landing = PurePosixPath(folder).name + '.md'
            for row in rows:
                if not row['directory'] and row['name'] == landing:
                    folder_pages[folder] = row['path']
                    break
        return rows

    def project(result):
        pages = {row['path']: folder_pages[row['path']] for row in result.rows
                 if row['directory'] and row['path'] in folder_pages}
        represented = set(pages.values())
        rows = [dict(row, page=pages[row['path']]) if row['path'] in pages else row
                for row in result.rows if row['path'] not in represented]
        return SearchResult(rows, result.scanned, result.complete, result.errors)

    notify = progress
    if collapse_folder_notes and progress is not None:
        notify = lambda result: progress(project(result))
    read_text = library.read_text if include_text else None

    def run(report):
        folder_pages.clear()
        return search_resources(library.provider, library.root, query, cancelled=cancelled,
            list_children=listing, read_text=read_text, progress=report)

    index = directory_index(library) if not include_text else None
    result = None
    if index is not None:
        cache, root = index
        try:
            saved = cache.peek(root, partial=False, cancelled=cancelled) if notify is not None else None
            if saved is not None:
                with saved:
                    children = lambda folder, **kwargs: indexed_children(library, saved, folder)
                    previous = run(None)
                    notify(SearchResult(previous.rows, previous.scanned, False, previous.errors))
            with cache.get(root, cancelled=cancelled, validate_files=False) as current:
                if current.complete and not current.errors:
                    children = lambda folder, **kwargs: indexed_children(library, current, folder)
                    result = run(notify)
        except (OSError, DatabaseError):
            pass  # Search remains available if the disposable index cannot be read or updated.
    if result is None:
        children = library.search_children
        result = run(notify)
    return project(result) if collapse_folder_notes else result


def ranked_search_rows(rows):
    """Filename matches precede body matches, with natural filename/path order."""
    return sorted(rows, key=lambda row: (row.get('content_match', False),
        natural_name_key(PurePosixPath(row['path']).name), natural_name_key(row['path'])))


def daily_notes(library, *, visible=lambda path, **kw: True, cancelled=lambda: False):
    """Index names only; never read note bodies or hidden configuration."""
    from datetime import date
    result, count = {}, 0
    pending = [(library.root, 0)]
    while pending:
        folder, depth = pending.pop()
        check_cancelled(cancelled)
        if depth > 100:
            raise ValueError('Calendar exceeds 100 folder levels.')
        for row in library.folders(folder, cancelled=cancelled):
            count += 1
            if count > 10000:
                raise ValueError('Calendar exceeds 10,000 entries.')
            if not visible(row['path'], directory=row['directory']):
                continue
            if row['directory']:
                pending.append((row['path'], depth + 1))
            elif row['name'].lower().endswith('.md'):
                name = row['name'][:-3]
                try:
                    day = date.fromisoformat(name)
                except ValueError:
                    continue
                if day.isoformat() == name:
                    result.setdefault(name, []).append(row['path'])
    return {day: sorted(paths) for day, paths in result.items()}


def remove(library, path, *, cancelled=lambda: False):
    if not library.supports('delete'):
        raise PermissionError('This Notes Library cannot delete files.')
    path = library.contained(path)
    if path == library.root:
        raise ValueError('Cannot delete the Notes Library root.')
    return delete_document_tree(library.provider, path, cancelled=cancelled)


def copy(library, source, target=None, *, cancelled=lambda: False):
    """Validate the library boundary before host-owned verified publication."""
    if not all(library.supports(action) for action in ('create', 'rename', 'delete')):
        raise PermissionError('This Notes Library cannot copy files.')
    source = library.contained(source)
    target = library.contained(target) if target is not None else None
    if source == library.root or target == library.root:
        raise ValueError('Cannot copy or replace the Notes Library root.')
    if target is None:
        return copy_document_sibling(library.provider, source, cancelled=cancelled)
    return copy_document_tree(library.provider, source, target, cancelled=cancelled)


class LibraryFolderProvider:
    """A folder-only browser projection rooted at one Notes Library."""
    def __init__(self, library, *, exclude=None):
        self.library = library
        self.root = library.provider.root / library.root
        self.exclude = library.contained(exclude) if exclude is not None else None

    def __getattr__(self, name):
        return getattr(self.library.provider, name)

    def acquire(self):
        # The library owns this provider. A temporary picker borrows it; its
        # browser must not close the library's view when the picker retires.
        return lambda: None

    def relative(self, path):
        from pathlib import Path
        import posixpath
        if isinstance(path, Path) and path.is_absolute():
            full = self.library.contained(path)
        else:
            full = self.library.contained('/'.join(part for part in (self.library.root, str(path)) if part))
        if self.exclude is not None and (full == self.exclude or full.startswith(self.exclude + '/')):
            raise ValueError('Choose a folder outside the item being moved.')
        value = posixpath.relpath(full, self.library.root or '.')
        return '' if value == '.' else value

    def library_path(self, path):
        return self.library.contained('/'.join(part for part in (self.library.root, self.relative(path)) if part))

    def entry(self, path):
        path = self.relative(path)
        entry = dict(self.library.entry(self.library_path(path)))
        entry['path'] = path
        return entry

    def list(self, path='', *, cancelled=lambda: False):
        rows = self.library.folders(self.library_path(path), cancelled=cancelled)
        result = []
        for row in rows:
            if row['directory']:
                try:
                    relative = self.relative(self.library.provider.root / row['path'])
                except ValueError:
                    continue
                result.append(dict(row, path=relative))
        return result


def renamed_path(source, name):
    """Rename accepts a single name; move destinations are chosen separately."""
    from commonUtils.runtime.resources.paths import resource_name
    import posixpath
    if not name.strip():
        raise ValueError('Enter a file or folder name.')
    return posixpath.join(posixpath.dirname(source), resource_name(name))
