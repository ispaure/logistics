"""Verified upgrade of the historical private and iOS system Inbox trees."""

from hashlib import sha256
from pathlib import Path

from commonUtils.persistence import atomic_write_json
from ..locations import _unlinked, collection_base, shared_documents_path
from ..mobile_locations import RECEIVED as RECEIVED_FILES


def legacy_inbox_path(private_root):
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
    from mobile.incoming_files import _read_json, valid_name
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
