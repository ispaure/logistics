"""One-time remote folder pulls; publish only a complete, new local copy."""
import os
from pathlib import Path, PurePosixPath
import shutil
import threading
from tempfile import mkdtemp
from uuid import uuid4

from .cloud import download_name
from commonUtils.persistence.publication import rename_exclusive


def pull_folder(client, remote, folder, root, *, decrypted=False,
                cancelled=lambda: False, progress=lambda count, path: None, transfer_progress=None):
    name = download_name(folder)
    root = Path(root)
    if not root.is_absolute() or root.is_symlink():
        raise ValueError('Local downloads require a private local directory.')
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(mkdtemp(prefix='.folder-pull-', dir=root.parent))
    generation = getattr(client, 'generation', None)
    count = 0
    seen = set()

    def check():
        if cancelled() or getattr(client, 'generation', None) != generation:
            raise ValueError('Folder download cancelled; no partial copy was saved.')

    try:
        pending = [(folder, staging)]
        while pending:
            check()
            source, destination = pending.pop()
            rows = client.entries(remote, source)
            check()
            for row in rows:
                check()
                path = row['path']
                leaf = download_name(path)
                if str(PurePosixPath(path).parent) != source or path in seen:
                    raise ValueError('Remote returned an invalid or repeated folder entry.')
                seen.add(path)
                if len(seen) > 10000:
                    raise ValueError('This folder exceeds the 10,000-item download limit.')
                target = destination / leaf
                if row['directory']:
                    target.mkdir(mode=0o700)
                    pending.append((path, target))
                else:
                    with target.open('xb') as stream:
                        os.chmod(target, 0o600)
                        stream_download(client, remote, row, stream, decrypted=decrypted, progress=transfer_progress)
                        check()
                        stream.flush()
                        os.fsync(stream.fileno())
                    count += 1
                    progress(count, path)
        check()
        # Unique destinations preserve every previous copy and any local edits.
        target = root / (name + '-' + uuid4().hex[:12])
        staging.rename(target)
        return target
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def pull_item(client, remote, row, root, *, decrypted=False,
              cancelled=lambda: False, progress=lambda count, path: None, transfer_progress=None):
    """Copy one remote item; files publish exclusively after complete transfer."""
    if row['directory']:
        return pull_folder(client, remote, row['path'], root, decrypted=decrypted,
                           cancelled=cancelled, progress=progress, transfer_progress=transfer_progress)
    name = download_name(row['path'])
    root = Path(root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError('Choose an existing private local folder.')
    generation = getattr(client, 'generation', None)
    def check():
        if cancelled() or getattr(client, 'generation', None) != generation:
            raise ValueError('Copy cancelled; no partial copy was saved.')
    staging = Path(mkdtemp(prefix='.file-pull-', dir=root.parent))
    try:
        check()
        temporary = staging / name
        with temporary.open('xb') as stream:
            os.chmod(temporary, 0o600)
            stream_download(client, remote, row, stream, decrypted=decrypted, progress=transfer_progress)
            check()
            stream.flush()
            os.fsync(stream.fileno())
        target = root / name
        while True:
            check()
            try:
                # Atomic no-replace rename also works in Android sandboxes
                # which forbid hard links. Existing files remain untouched.
                rename_exclusive(temporary, target)
                break
            except FileExistsError:
                suffix = Path(name).suffix
                target = root / (Path(name).stem[:160] + '-copy-' + uuid4().hex[:12] + suffix)
        progress(1, row['path'])
        return target
    finally:
        shutil.rmtree(staging)


def stream_download(client, remote, row, stream, *, decrypted=False, progress=None):
    """Sample descriptor bytes while the native bridge streams on this worker."""
    download = client.download_decrypted_into if decrypted else client.download_into
    if progress is None:
        return download(remote, row['path'], stream.fileno())
    done = threading.Event()
    descriptor = stream.fileno()
    total = row.get('size', -1)
    def report():
        progress(os.fstat(descriptor).st_size, total, row['path'])
    def monitor():
        while not done.wait(0.2):
            report()
    report()
    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()
    try:
        return download(remote, row['path'], descriptor)
    finally:
        done.set()
        watcher.join()
        report()
