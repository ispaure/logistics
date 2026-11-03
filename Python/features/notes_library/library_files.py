"""Rooted daily-note discovery and verified local library file commands."""
from commonUtils.runtime.operations import check_cancelled
from services.documents.mutations import delete_document_tree, copy_document_tree


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


def copy(library, source, target, *, cancelled=lambda: False):
    """Validate the library boundary before host-owned verified publication."""
    if not all(library.supports(action) for action in ('create', 'rename', 'delete')):
        raise PermissionError('This Notes Library cannot copy files.')
    source, target = library.contained(source), library.contained(target)
    if source == library.root or target == library.root:
        raise ValueError('Cannot copy or replace the Notes Library root.')
    return copy_document_tree(library.provider, source, target, cancelled=cancelled)
