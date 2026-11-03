"""Document-tree publication behind the host storage policy."""
import posixpath
from hashlib import sha256
from uuid import uuid4
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.resources.mutations import inventory, delete_resource
from commonUtils.runtime.streams import iter_chunks
from commonUtils.persistence.publication import mutation_lock
from .storage import document_operation, document_writable


def delete_document_tree(provider, path, *, cancelled=lambda: False):
    if not document_writable(provider):
        raise PermissionError('This storage cannot delete documents.')
    with document_operation(provider, cancelled):
        return delete_resource(provider, path, cancelled=cancelled)


def copy_document_tree(provider, source, target, *, cancelled=lambda: False):
    """Stage and verify a captured tree before a collision-safe provider rename."""
    if not document_writable(provider):
        raise PermissionError('This storage cannot copy documents.')
    source, target = provider.relative(source), provider.relative(target)
    if not source or not target or source == target or target.startswith(source + '/'):
        raise ValueError('Choose a new path outside the selected folder.')
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
