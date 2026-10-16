"""Expose only Local in iOS Documents; private state lives in Application Support."""
import json
from pathlib import Path

from commonUtils.persistence import atomic_write_json
from features.rclone.mobile.storage_location import _unlinked, use_shared_local

MIGRATION = 'ios-file-sharing-migration.json'
# These identify the old Toga Documents-as-private-data layout. New installations
# can already have user files in Documents before their first app launch.
LEGACY_NAMES = {
    'LocalFiles', 'LocalCryptFolders', 'Credentials', 'CredentialPackages',
    'preferences.ini', 'workspace.json', 'recent-documents.json', 'locations.json',
    'mirror-jobs.json', 'resource-imports.json', 'collection-storage.json',
    'transfer-options.json',
}


def prepare_storage(documents, private, *, exclude_backup, move):
    """Resume same-volume, exclusive moves before starting any app services.

    Journal the old root's names before moving anything. Once private state is
    relocated, publish LocalFiles' children into Documents/Local. Renames
    preserve bytes without requiring a second copy of a large collection. A
    crash leaves each entry at its source or destination; retries never overwrite.
    """
    documents, private = _unlinked(documents), _unlinked(private)
    if documents == private or private.is_relative_to(documents) or documents.is_relative_to(private):
        raise ValueError('Shared Local storage must be separate from private app data.')
    documents.mkdir(parents=True, exist_ok=True)
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Fail before publishing ordinary files if the backup exclusion fails.
    # Reapply every launch, including after device restore or directory recreation.
    exclude_backup(documents)
    journal = _unlinked(private / MIGRATION)
    if journal.exists():
        if journal.stat().st_size > 1024 * 1024:
            raise ValueError('Invalid iOS storage migration journal.')
        state = json.loads(journal.read_text())
        if (not isinstance(state, dict) or set(state) != {'phase', 'names'}
                or state['phase'] not in ('private', 'local', 'done')
                or not isinstance(state['names'], list)
                or any(not isinstance(name, str) or not name or name in ('.', '..')
                       or '/' in name or '\\' in name for name in state['names'])
                or len(set(state['names'])) != len(state['names'])):
            raise ValueError('Invalid iOS storage migration journal.')
    else:
        legacy = any((documents / name).exists() for name in LEGACY_NAMES)
        # Inbox is owned by iOS document import, not private application state.
        names = sorted(p.name for p in documents.iterdir() if p.name != 'Inbox') if legacy else []
        state = dict(phase='private', names=names)
        atomic_write_json(journal, state, durable_directory=True)

    if state['phase'] == 'private':
        _move_entries(documents, private, state['names'], move)
        source = _unlinked(private / 'LocalFiles')
        names = sorted(p.name for p in source.iterdir()) if source.exists() else []
        state = dict(phase='local', names=names)
        atomic_write_json(journal, state, durable_directory=True)
    if state['phase'] == 'local':
        source = _unlinked(private / 'LocalFiles')
        local = _unlinked(documents / 'Local')
        local.mkdir(exist_ok=True)
        _move_entries(source, local, state['names'], move)
        if source.exists():
            source.rmdir()
        atomic_write_json(journal, dict(phase='done', names=[]), durable_directory=True)
    # Keep a visible child even before the first pull, and recreate it if deleted
    # in Files. No migration of files already in the shared root is needed.
    local = _unlinked(documents / 'Local')
    local.mkdir(exist_ok=True)
    use_shared_local(private, documents)
    return private


def _move_entries(source, destination, names, move):
    # Preflight the entire phase; never silently merge an existing directory.
    for name in names:
        old, new = _unlinked(source / name), _unlinked(destination / name)
        if old.exists() and new.exists():
            raise FileExistsError('Storage migration found a conflicting file; both copies were preserved: ' + str(new))
        if not old.exists() and not new.exists():
            raise FileNotFoundError('Storage migration cannot find: ' + name)
    for name in names:
        old, new = _unlinked(source / name), _unlinked(destination / name)
        if old.exists():
            move(old, new)  # Native API must reject an existing destination.


def prepare_for_app(app):
    from rubicon.objc import ObjCClass

    def exclude_backup(path):
        url = ObjCClass('NSURL').fileURLWithPath(str(path))
        if not url.setResourceValue(True, forKey='NSURLIsExcludedFromBackupKey', error=None):
            raise OSError('Local file sharing could not be excluded from backup. Reopen Logistics to retry.')

    def move(source, destination):
        manager = ObjCClass('NSFileManager').defaultManager
        if not manager.moveItemAtPath(str(source), toPath=str(destination), error=None):
            raise OSError('Storage migration could not move ' + source.name + '. Reopen Logistics to retry; existing files were preserved.')

    # Toga iOS 0.5.7 data is the shared Documents directory. config is located
    # under Library/Application Support/Config; its sibling is genuinely private.
    return prepare_storage(Path(app.paths.data), Path(app.paths.config).parent / 'Logistics',
                           exclude_backup=exclude_backup, move=move)
