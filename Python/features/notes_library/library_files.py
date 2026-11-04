"""Rooted daily-note discovery and verified local library file commands."""
from commonUtils.runtime.operations import check_cancelled
from services.documents.mutations import delete_document_tree, copy_document_tree, copy_document_sibling


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
