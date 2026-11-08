"""Journaled, temporary upgrade of existing mobile collections."""

import errno
import json
from pathlib import Path, PurePosixPath

from commonUtils.filesystem.snapshots import verified_file_snapshot
from commonUtils.persistence import atomic_write_json
from commonUtils.persistence.publication import rename_exclusive, serialize_mutation
from ..mobile_locations import COPIES, ENCRYPTED_COPIES, FILES, RECEIVED, _enabled, _parts, enabled, reserved_phone_name

_journals = {}
_android_ready = {}
_JOURNAL_LIMIT = 16 * 1024 * 1024


def legacy_collection_name(private_root, base):
    return 'LocalFiles' if base == Path(private_root) else 'Local'


def legacy_encrypted_name(private_root, base):
    return 'LocalCryptFolders' if base == Path(private_root) else 'LocalCrypt'


def _journal_path(private_root, base, ios, token):
    from ..locations import _unlinked
    if ios or base == Path(private_root):
        scope = 'ios' if ios else 'internal'
    else:
        if not token or len(token) != 32 or any(character not in '0123456789abcdef' for character in token):
            raise ValueError('Invalid mobile storage location.')
        scope = token
    return _unlinked(Path(private_root) / f'public-storage-v1-{scope}.json')


def _current_journal(private_root):
    from ..locations import collection_base, selection, shared_documents_path
    docs = shared_documents_path(private_root)
    base = docs if docs is not None else collection_base(private_root)
    chosen = selection(private_root) if docs is None else None
    journal = _journal_path(private_root, base, docs is not None, chosen['token'] if chosen else None)
    return base, _journals.get(journal, ({}, {}))


def ios_upgrade_pending(private_root, documents):
    return not _journal_path(private_root, documents, True, None).exists()


def remapped_path(private_root, original, *, ios_relative=None):
    if not enabled(private_root):
        return None
    from ..locations import _unlinked
    try:
        base, (moves, _) = _current_journal(private_root)
    except OSError:
        return None
    if ios_relative is None:
        # /var and /private/var can both appear in old absolute references.
        try:
            relative = original.resolve().relative_to(base.resolve())
        except ValueError:
            return None
    else:
        relative = ios_relative
    for old in (relative, *relative.parents):
        move = moves.get(old.as_posix())
        if move is not None:
            target = _unlinked(base / move['to'] / relative.relative_to(old))
            return target if target.exists() else None
    return None


def legacy_copy_path(private_root, key):
    from ..locations import collection_path
    base, _ = _current_journal(private_root)
    original = base / legacy_collection_name(private_root, base) / key
    return remapped_path(private_root, original) or collection_path(private_root) / key


def legacy_reference(private_root, physical):
    """Get the old checkpoint key and any verified change in file revision."""
    from ..locations import selection, shared_documents_path
    base, (_, reverse) = _current_journal(private_root)
    relative = physical.relative_to(base.resolve())
    for parent in (relative, *relative.parents):
        match = reverse.get(parent.as_posix())
        if match is not None:
            old, move = match
            previous = Path(old) / relative.relative_to(parent)
            binding = (move['stat'], move.get('published', move['stat'])) if parent == relative else None
            break
    else:
        previous, binding = relative, None
    if shared_documents_path(private_root) is not None:
        return ('local', 'app:ios-documents', previous.as_posix()), binding
    selected = selection(private_root)
    scope = 'app' if selected is None else 'drive:' + selected['token']
    if previous.parts and previous.parts[0] == legacy_collection_name(private_root, base):
        return ('local', scope + ':local', Path(*previous.parts[1:]).as_posix()), binding
    if previous.parts and previous.parts[0] == RECEIVED:
        return ('local', scope + ':received', Path(*previous.parts[1:]).as_posix()), binding
    return None, None


def _stat(path):
    info = path.stat()
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def _plan(private_root, base, phone, *, old_copies):
    from ..locations import _unlinked
    from features.rclone.transfers.mobile.records import CopyRecords
    from features.notes_library.notes import LIBRARY_MARKER
    moves = {}
    legacy = _unlinked(base / old_copies)
    copies = _unlinked(base / COPIES)
    received = _unlinked(base / RECEIVED)
    occupied = {child.name.casefold() for child in phone.iterdir()}

    def plan_child(child, label):
        _unlinked(child)
        if not child.is_dir() and (not child.is_file() or child.stat().st_nlink != 1):
            raise ValueError('Storage contains an unsupported item: ' + child.name)
        name = 'Received ' + child.name if child.name.startswith(('.incoming-', '.storage-copy-')) else child.name
        original_name = name
        counter = 1
        while name.casefold() in occupied or reserved_phone_name(name):
            suffix = '' if child.is_dir() else child.suffix
            tag = f' ({label} {counter})'
            extension = suffix.encode('utf-8')[:80].decode('utf-8', 'ignore')
            budget = 240 - len((tag + extension).encode('utf-8'))
            stem = original_name.removesuffix(suffix).encode('utf-8')[:budget].decode('utf-8', 'ignore')
            name = stem + tag + extension
            counter += 1
        occupied.add(name.casefold())
        moves[child.relative_to(base).as_posix()] = dict(
            to=(phone / name).relative_to(base).as_posix(), stat=_stat(child))

    def library(folder):
        marker, obsidian = folder / LIBRARY_MARKER, folder / '.obsidian'
        return ((marker.is_file() and not marker.is_symlink())
                or (obsidian.is_dir() and not obsidian.is_symlink()))

    if received.exists():
        for child in [received] if library(received) else sorted(received.iterdir()):
            plan_child(child, 'received')
    if legacy.exists():
        if not legacy.is_dir() or copies.exists():
            raise FileExistsError('Both Local and Rclone Copies exist. Move the conflicting item and retry.')
        records = CopyRecords(private_root, _unlinked)
        if not records.error and not library(legacy):
            mapped = {PurePosixPath(job['target']).parts[0].casefold()
                      for job in records.jobs.values() if not job['crypt'] and job['target']}
            for child in sorted(legacy.iterdir()):
                if child.name.casefold() not in mapped and not child.is_symlink() and (
                    child.is_file() and not child.name.startswith('.') or
                    child.is_dir() and (child / LIBRARY_MARKER).is_file() and not (child / LIBRARY_MARKER).is_symlink()
                ):
                    plan_child(child, 'local')
        moves[old_copies] = dict(to=COPIES, stat=_stat(legacy))
    return moves


def _load_plan(path, *, old_copies, phone_prefix):
    if path.stat().st_size > _JOURNAL_LIMIT:
        raise ValueError('Mobile storage migration journal is too large.')
    state = json.loads(path.read_text())
    if (not isinstance(state, dict) or set(state) != {'done', 'moves'}
            or type(state['done']) is not bool or not isinstance(state['moves'], dict)):
        raise ValueError('Invalid mobile storage migration journal.')
    for old, move in state['moves'].items():
        if (not isinstance(move, dict) or not {'to', 'stat'} <= set(move) <= {'to', 'stat', 'digest', 'published', 'reservation'}
                or not _parts(old) or not isinstance(move['to'], str) or not _parts(move['to'])
                or any(not isinstance(move[key], list) or len(move[key]) != 5
                       or not all(type(value) is int for value in move[key])
                       for key in ('stat', 'published', 'reservation') if key in move)
                or ('digest' in move and (not isinstance(move['digest'], str) or len(move['digest']) != 64))):
            raise ValueError('Invalid mobile storage migration path.')
        source, target = _parts(old), _parts(move['to'])
        if old == old_copies:
            valid = target == [COPIES]
        else:
            valid = (source[0] in (old_copies, RECEIVED) and len(source) <= 2
                     and len(target) == len(phone_prefix) + 1 and target[:-1] == phone_prefix
                     and not reserved_phone_name(target[-1]))
        if not valid:
            raise ValueError('Mobile storage migration escaped its collection.')
    return state


def _android_fallback(origin, target, item, save):
    """Handle removable filesystems that reject exclusive rename flags."""
    if origin.is_dir():
        if 'reservation' not in item:
            target.mkdir()  # Reserve exclusively before a plain directory rename.
            item['reservation'] = _stat(target)
            save()
        if _stat(target) != item['reservation'] or any(target.iterdir()):
            raise FileExistsError('The storage destination changed: ' + str(target))
        # A plain directory rename cannot replace a nonempty destination.
        origin.rename(target)
        return
    from commonUtils.runtime.resources.local import LocalFiles
    if 'digest' not in item and target.exists():
        raise FileExistsError('The storage destination already exists: ' + str(target))
    before, digest = verified_file_snapshot(origin)
    if list(before) != item['stat'] or digest.hex() != item.setdefault('digest', digest.hex()):
        raise ValueError('The original file changed during the storage upgrade.')
    save()
    if not target.exists():
        with origin.open('rb') as stream:
            LocalFiles(target.parent).create_file(target.name, stream)
    if target.stat().st_nlink != 1:
        raise ValueError('Linked storage destinations are not supported.')
    after, copied = verified_file_snapshot(target)
    if digest != copied or _stat(origin) != item['stat'] or _stat(target) != list(after):
        raise ValueError('Could not verify the storage copy. Both files were preserved.')
    item['published'] = list(after)
    save()  # Persist the verified destination before removing the original.
    origin.unlink()


def _move_item(origin, target, item, move, save):
    if 'digest' in item or 'reservation' in item:
        return _android_fallback(origin, target, item, save)
    if target.exists():
        raise FileExistsError('The storage destination already exists: ' + str(target))
    expected = item['stat']
    if (_stat(origin)[:2] != expected[:2] if origin.is_dir() else _stat(origin) != expected):
        raise ValueError('The original item changed during the storage upgrade: ' + str(origin))
    try:
        move(origin, target)
    except OSError as error:
        from commonUtils.runtime.platform import get_os, OS
        if get_os() is not OS.ANDROID or error.errno not in (errno.EINVAL, errno.ENOSYS, errno.ENOTSUP):
            raise
        _android_fallback(origin, target, item, save)


def _rename_encrypted(private_root, base, journal, *, move, report):
    from ..locations import _unlinked
    receipt = _unlinked(journal.with_name(journal.stem + '-encrypted.json'))
    source = _unlinked(base / legacy_encrypted_name(private_root, base))
    destination = _unlinked(base / ENCRYPTED_COPIES)
    def save(value):
        atomic_write_json(receipt, value, max_bytes=1024, durable_directory=True)

    if receipt.exists():
        if receipt.stat().st_size > 1024:
            raise ValueError('Invalid encrypted collection upgrade receipt.')
        item = json.loads(receipt.read_text())
        if item == {'done': True}:
            return
        if (not isinstance(item, dict) or set(item) != {'stat', 'reservation'}
                or any(not isinstance(value, list) or len(value) != 5
                       or any(type(part) is not int for part in value) for value in item.values())
                or source.exists() and item['stat'][:2] != _stat(source)[:2]):
            raise ValueError('Invalid encrypted collection upgrade receipt.')
    else:
        item = dict(stat=_stat(source)) if source.exists() else None
    if not source.exists():
        if item is not None and (not destination.is_dir() or _stat(destination)[:2] != item['stat'][:2]):
            raise FileNotFoundError('Cannot verify the encrypted collection rename.')
        save({'done': True})
        return
    if not source.is_dir():
        raise ValueError('Encrypted collection storage must be a folder.')
    report('Renaming encrypted copies…', 0, 1)
    _move_item(source, destination, item, move, lambda: save(item))
    save({'done': True})
    report('Renaming encrypted copies…', 1, 1)


@serialize_mutation
def prepare_layout(private_root, base, *, ios=False, token=None, move=rename_exclusive,
                   report=lambda label, done, total: None):
    """Publish a single resumable, no-overwrite upgrade for a storage volume."""
    from ..locations import _unlinked
    private_root, base = _unlinked(private_root), _unlinked(base)
    path = _journal_path(private_root, base, ios, token)
    _rename_encrypted(private_root, private_root if ios else base, path, move=move, report=report)
    if path in _journals:
        _enabled.add(private_root)
        return
    phone = base if ios else _unlinked(base / FILES)
    phone.mkdir(parents=True, exist_ok=True)
    old = legacy_collection_name(private_root, base)
    def save():
        atomic_write_json(path, state, max_bytes=_JOURNAL_LIMIT, durable_directory=True)

    if path.exists():
        state = _load_plan(path, old_copies=old, phone_prefix=list(phone.relative_to(base).parts))
    else:
        state = dict(done=False, moves=_plan(private_root, base, phone, old_copies=old))
        save()
    if not state['done']:
        total = len(state['moves'])
        if total:
            report('Organizing your files…', 0, total)
        for completed, (source, item) in enumerate(state['moves'].items(), 1):
            origin, target = _unlinked(base / source), _unlinked(base / item['to'])
            if origin.exists():
                _move_item(origin, target, item, move, save)
            elif not target.exists() or _stat(target)[:2] != item.get('published', item['stat'])[:2]:
                raise FileNotFoundError('Cannot verify the completed storage move for ' + source)
            report('Organizing your files…', completed, total)
        received = _unlinked(base / RECEIVED)
        if received.exists():
            received.rmdir()
        state['done'] = True
        save()
    _unlinked(base / COPIES).mkdir(exist_ok=True)
    moves = state['moves']
    _journals[path] = moves, {move['to']: (old, move) for old, move in moves.items()}
    _enabled.add(private_root)


def ensure_android_layout(private_root, base):
    private_root = Path(private_root)
    if enabled(private_root) and _android_ready.get(private_root) != base:
        prepare_android(private_root, base=base)


@serialize_mutation
def prepare_android(private_root, *, base=None, report=lambda label, done, total: None):
    from ..locations import collection_base, selection
    from .legacy_inbox import legacy_inbox_path
    private_root = Path(private_root)
    chosen = selection(private_root)
    try:
        base = collection_base(private_root) if base is None else base
    except OSError:
        # Keep unrelated screens usable with a disconnected collection drive.
        _enabled.add(private_root)
        return
    journal = _journal_path(private_root, base, False, chosen['token'] if chosen else None)
    if not journal.exists() and ((base / RECEIVED).exists() or (base / 'Inbox').exists()
                                 or (private_root / 'Inbox').exists() and not enabled(private_root)):
        report('Preparing received files…', 0, None)
        legacy_inbox_path(private_root)  # Finish the older Inbox upgrade first.
    prepare_layout(private_root, base, token=chosen['token'] if chosen else None, report=report)
    _android_ready[private_root] = base
