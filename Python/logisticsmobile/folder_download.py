"""One-time remote folder pulls; publish only a complete, new local copy."""
import os
from pathlib import Path, PurePosixPath
import shutil
from tempfile import mkdtemp
from uuid import uuid4

from .cloud import download_name


def pull_folder(client, remote, folder, root, *, decrypted=False,
                cancelled=lambda: False, progress=lambda count, path: None):
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
                    download = client.download_decrypted_into if decrypted else client.download_into
                    with target.open('xb') as stream:
                        os.chmod(target, 0o600)
                        download(remote, path, stream.fileno())
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
