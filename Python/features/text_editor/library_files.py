"""Rooted daily-note discovery and verified local library file commands."""
import posixpath
from hashlib import sha256
from uuid import uuid4
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.resources.mutations import inventory, delete_resource
from commonUtils.runtime.streams import iter_chunks
from commonUtils.persistence.publication import mutation_lock
from services.documents.storage import document_operation


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
    with document_operation(library.provider, cancelled):
        return delete_resource(library.provider, path, cancelled=cancelled)


def copy(library, source, target, *, cancelled=lambda: False):
    """Stage, verify and rename within the provider; preserve the source."""
    if not all(library.supports(action) for action in ('create', 'rename', 'delete')):
        raise PermissionError('This Notes Library cannot copy files.')
    source, target = library.contained(source), library.contained(target)
    if source == library.root or target == library.root or target == source or target.startswith(source + '/'):
        raise ValueError('Choose a new path outside the selected folder.')
    provider = library.provider
    temporary = posixpath.join(posixpath.dirname(target), '.notes-copy-' + uuid4().hex)

    def digest(path):
        value = sha256()
        with provider.open(path) as stream:
            for chunk in iter_chunks(stream, cancelled=cancelled):
                value.update(chunk)
        return value.digest()

    with document_operation(provider, cancelled), mutation_lock:
        rows = inventory(provider, source, cancelled=cancelled)
        if not rows['']['directory']:
            from pathlib import PurePosixPath
            if PurePosixPath(source).suffix.lower() != PurePosixPath(target).suffix.lower():
                raise ValueError('Keep the document filename extension.')
        created = False
        try:
            for relative, row in rows.items():
                check_cancelled(cancelled)
                output = posixpath.join(temporary, relative) if relative else temporary
                if row['directory']:
                    provider.mkdir(output)
                else:
                    with provider.open(row['path']) as stream:
                        provider.create_file(output, stream, cancelled=cancelled)
                created = True
                if not row['directory'] and digest(row['path']) != digest(output):
                    raise ValueError('Copy verification failed; original files are preserved.')
            if rows != inventory(provider, source, cancelled=cancelled):
                raise ValueError('Source changed while copying; try again.')
            check_cancelled(cancelled)
            provider.rename(temporary, target)  # Providers refuse existing destinations.
            created = False
        finally:
            if created:
                delete_resource(provider, temporary)
    return target
