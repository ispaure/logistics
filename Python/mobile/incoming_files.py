"""Consume complete native handoffs into an ordinary, browsable Inbox.

The native receivers own temporary OS grants. Only atomically ready directories
reach this owner; publication is exclusive and retryable after interruption.
"""
import asyncio
from hashlib import sha256
import json
from itertools import islice
import os
from pathlib import Path
import re
import shutil
import stat
import time

from commonUtils.persistence import atomic_write_json
from commonUtils.persistence.publication import rename_exclusive
from services.documents.locations import _unlinked, shared_documents_path, collection_base

MAX_FILE = 1024 * 1024 * 1024
MAX_FILES = 100


RECEIVED_FILES = 'Received Files'


def inbox_path(private_root):
    private_root = Path(private_root)
    documents = shared_documents_path(private_root)
    base = documents if documents is not None else collection_base(private_root)
    path = _unlinked(base / RECEIVED_FILES)
    path.mkdir(parents=True, exist_ok=True)
    # Older Android builds kept Inbox private even with an external collection.
    # iOS previously used the system-owned, read-only Documents/Inbox instead.
    sources = list(dict.fromkeys([private_root / 'Inbox', base / 'Inbox']))
    for source in sources:
        if source != path:
            _migrate_inbox(private_root, source, path, ios=documents is not None)
    return path


def _migrate_inbox(private_root, source, destination, *, ios):
    """Copy a legacy tree once; journal publication and retain the source backup."""
    from commonUtils.persistence.publication import mutation_lock
    from services.documents.locations import _inventory, _stage_collection_tree, _Progress
    with mutation_lock:
        source, destination = _unlinked(source), _unlinked(destination)
        # iOS container prefixes change after restore. Its two sources are
        # distinguished by their parent, not by a persisted absolute path.
        identity = ('shared' if source.parent != private_root else 'private') if ios else str(source)
        journal = _unlinked(private_root / ('inbox-upgrade-' + sha256(identity.encode()).hexdigest()[:16] + '.json'))
        state = _read_json(journal) if journal.exists() else None
        if state is not None:
            if (not isinstance(state, dict) or set(state) != {'target', 'done'}
                    or not isinstance(state['done'], bool)
                    or not isinstance(state['target'], str)
                    or state['target'] and valid_name(state['target']) != state['target']):
                raise ValueError('Invalid Inbox migration journal.')
            if state['done']:
                return
        snapshot = _inventory(source)
        if not snapshot:
            return
        if state is None:
            name = ''
            if any(destination.iterdir()):
                name = 'Previous Inbox'
                number = 1
                while (destination / name).exists() or (destination / name).is_symlink():
                    name = f'Previous Inbox ({number})'
                    number += 1
            state = dict(target=name, done=False)
            atomic_write_json(journal, state, durable_directory=True)
        target = _unlinked(destination / state['target'])
        existing = _inventory(target)
        if existing and existing != snapshot:
            raise FileExistsError('Inbox migration found changed files; both copies were preserved.')
        if not existing:
            _stage_collection_tree(source, target, snapshot, destination.parent, _Progress(None))
        if _inventory(source) != snapshot or _inventory(target) != snapshot:
            raise OSError('Inbox migration verification failed; original files were preserved.')
        atomic_write_json(journal, dict(state, done=True), durable_directory=True)


def valid_name(name):
    if (not isinstance(name, str) or name in ('', '.', '..') or len(name.encode('utf-8')) > 240
            or any(c in name for c in '/\\\0') or any(ord(c) < 32 for c in name)):
        raise ValueError('Invalid incoming filename.')
    return name


def _read_json(path):
    path = _unlinked(path)
    if not path.is_file() or path.stat().st_size > 4096:
        raise ValueError('Invalid incoming record.')
    return json.loads(path.read_text())


def _digest(path):
    path = _unlinked(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_FILE:
        raise ValueError('Invalid incoming file.')
    digest = sha256()
    size = 0
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            size += len(block)
            if size > MAX_FILE:
                raise ValueError('Incoming file exceeds the size limit.')
            digest.update(block)
    after = path.stat()
    if (info.st_ino, info.st_size, info.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns) or size != info.st_size:
        raise ValueError('Incoming file changed while reading.')
    return digest.hexdigest(), size


def _publish(delivery, inbox):
    record = _read_json(delivery / 'metadata.json')
    if not isinstance(record, dict) or set(record) != {'name'}:
        raise ValueError('Invalid incoming record.')
    name = valid_name(record['name'])
    source = _unlinked(delivery / 'payload')
    digest, size = _digest(source)
    receipt_path = delivery / 'receipt.json'
    if receipt_path.exists():
        receipt = _read_json(receipt_path)
        if (not isinstance(receipt, dict) or set(receipt) != {'name', 'sha256', 'size'}
                or receipt['sha256'] != digest or receipt['size'] != size):
            raise ValueError('Incoming file changed before publication.')
        name = valid_name(receipt['name'])
    else:
        original = Path(name)
        for number in range(10000):
            suffix = original.suffix.encode('utf-8')[:80].decode('utf-8', 'ignore')
            counter = f' ({number})'
            budget = 240 - len((counter + suffix).encode('utf-8'))
            stem = original.stem.encode('utf-8')[:budget].decode('utf-8', 'ignore')
            name = original.name if number == 0 else stem + counter + suffix
            if not (inbox / name).exists() and not (inbox / name).is_symlink():
                break
        else:
            raise FileExistsError('Too many incoming files with this name.')
        atomic_write_json(receipt_path, dict(name=name, sha256=digest, size=size), durable_directory=True)
    destination = _unlinked(inbox / name)
    if destination.exists():
        if _digest(destination) != (digest, size):
            raise FileExistsError('Inbox destination changed; incoming file preserved.')
    else:
        # Stage on the destination volume; publish without overwriting, including
        # Android removable filesystems which do not support hard links.
        temporary = _unlinked(inbox / ('.incoming-' + delivery.name))
        temporary.unlink(missing_ok=True)
        try:
            with temporary.open('xb') as output, source.open('rb') as stream:
                shutil.copyfileobj(stream, output, 1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            if _digest(temporary) != (digest, size):
                raise OSError('Incoming copy verification failed.')
            rename_exclusive(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        descriptor = os.open(inbox, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    shutil.rmtree(delivery)


def consume(queue, inbox, *, failed_deliveries=None):
    """Return saved/failed counts. Failed ready imports remain retryable."""
    import fcntl
    queue, inbox = _unlinked(queue), _unlinked(inbox)
    if not queue.exists():
        return 0, 0
    saved = failed = 0
    with _unlinked(queue / '.consumer.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0, 0
        failure = _unlinked(queue / 'failed')
        if failure.exists():
            failed += 1
            failure.unlink()
        admitted = 0
        for delivery in sorted(islice(queue.iterdir(), 1000)):
            if re.fullmatch(r'[0-9a-fA-F-]{32,36}\.partial', delivery.name):
                try:
                    _unlinked(delivery)
                    if time.time() - delivery.stat().st_mtime > 24 * 60 * 60:
                        shutil.rmtree(delivery)
                except (OSError, ValueError):
                    failed += 1
                continue
            if not re.fullmatch(r'[0-9a-fA-F-]{32,36}\.ready', delivery.name):
                continue
            if failed_deliveries is not None and delivery.name in failed_deliveries:
                continue
            if admitted >= MAX_FILES:
                continue
            admitted += 1
            try:
                _unlinked(delivery)
                _publish(delivery, inbox)
                saved += 1
            except (OSError, ValueError, TypeError):
                failed += 1
                if failed_deliveries is not None:
                    failed_deliveries.add(delivery.name)
    return saved, failed


def native_queues(app):
    if type(app._impl).__module__.startswith('toga_android.'):
        return [Path(str(app._impl.native.getNoBackupFilesDir().getAbsolutePath())) / 'Incoming']
    if type(app._impl).__module__.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        receiver = ObjCClass('LogisticsIncomingFiles')
        paths = [Path(str(receiver.privateQueue()))]
        shared = receiver.sharedQueue()
        if shared is not None:
            paths.append(Path(str(shared)))
        return paths
    return []


def start_receiving(app):
    if getattr(app, 'window_id', 'primary') != 'primary':
        return
    queues = native_queues(app)
    if not queues:
        return
    async def receive():
        failed_deliveries = {queue: set() for queue in queues}
        while (getattr(app, 'active_host', True) and not getattr(app, '_reset_scheduled', False)
               and not getattr(getattr(app, '_host_lifecycle', None), 'exited', False)):
            try:
                def receive_ready():
                    from commonUtils.persistence.publication import mutation_lock
                    with mutation_lock:
                        if getattr(app, '_storage_changing', False):
                            return None, 0, 0
                        inbox = inbox_path(app.private_root)
                        saved = failed = 0
                        for queue in queues:
                            good, bad = consume(queue, inbox, failed_deliveries=failed_deliveries[queue])
                            saved += good
                            failed += bad
                        return inbox, saved, failed
                inbox, saved, failed = await asyncio.to_thread(receive_ready)
                if not app.active_host:
                    break
                if saved or failed:
                    app.incoming_status = (f'{saved} file(s) saved to Received Files.' if saved else '')
                    if failed:
                        app.incoming_status += ' Some incoming files could not be saved; reopen the app to retry.'
                    status = getattr(app, 'incoming_notice', None)
                    if status is not None:
                        status.text = app.incoming_status
                    provider = getattr(app, 'file_provider', None)
                    root = getattr(provider, 'root', None)
                    shown = Path(root) / getattr(app, 'file_path', '') if root is not None else None
                    if (saved and shown == inbox and getattr(app, 'body', None) is getattr(app, 'files_view', None)
                            and not getattr(app, 'cloud_busy', False)):
                        await app.browse_files()
            except (OSError, ValueError):
                app.incoming_status = 'Incoming files are waiting. Check available storage and reopen the app.'
            await asyncio.sleep(2)
    app.incoming_task = app.loop.create_task(receive())
