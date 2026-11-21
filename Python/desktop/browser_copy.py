"""Cancellable copy via browser providers, including encrypted destinations."""
from hashlib import sha256
from uuid import uuid4

from commonUtils.persistence.publication import mutation_lock
from commonUtils.persistence.transfers import verify_unchanged
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.resources.mutations import delete_resource, inventory
from commonUtils.runtime.streams import iter_chunks
from commonUtils.runtime.streams.progress import ReadingStream


def _digest(provider, path, cancelled):
    digest = sha256()
    with provider.open(path) as stream:
        for chunk in iter_chunks(stream, cancelled=cancelled):
            digest.update(chunk)
    return digest.digest()


def copy_item(source, path, destination, target, *, cancelled, progress, revision=None):
    """Publish a verified tree without replacing a destination or removing a source."""
    with mutation_lock:
        rows = inventory(source, path, cancelled=cancelled)
        if revision is not None and rows['']['revision'] != revision:
            raise ValueError('The selected item changed. Select it again before copying.')
        directory = rows['']['directory']
        origin = source.transfer_location(path, directory=directory)
        output = destination.transfer_location(target, directory=directory)
        if origin == output or origin in output.parents or output in origin.parents:
            raise ValueError('Source and destination overlap.')
        try:
            destination.entry(target)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError('Destination already exists.')
        temporary = '/'.join(filter(None, (target.rpartition('/')[0], '.drag-' + uuid4().hex)))
        created = False
        try:
            for relative, row in rows.items():
                check_cancelled(cancelled)
                staged = '/'.join(filter(None, (temporary, relative)))
                if row['directory']:
                    destination.mkdir(staged)
                else:
                    with source.open(row['path']) as stream:
                        measured = ReadingStream(stream, lambda done, total: progress(
                            phase='Copying', done=done, total=total), getattr(stream, 'size', row['size']))
                        destination.create_file(staged, measured, cancelled=cancelled)
                created = True
                if not row['directory']:
                    progress(phase='Verifying')
                    if _digest(source, row['path'], cancelled) != _digest(destination, staged, cancelled):
                        raise ValueError('Destination verification failed.')
            verify_unchanged(rows, lambda: inventory(source, path, cancelled=cancelled),
                             message='Source changed during copying.')
            check_cancelled(cancelled)
            destination.rename(temporary, target)
            created = False
        finally:
            if created:
                delete_resource(destination, temporary)
