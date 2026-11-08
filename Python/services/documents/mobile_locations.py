"""Mobile public storage paths and stable document reference aliases."""

from pathlib import Path, PurePosixPath

COPIES = 'Rclone Copies'
ENCRYPTED_COPIES = 'Rclone Copies Encrypted'
ENCRYPTED_ALIAS = 'RcloneCopiesEncrypted://'
PHONE = 'On This Phone'
FILES = 'Files'
RECEIVED = 'Received Files'
FILES_ALIAS = 'Files://'
COPIES_ALIAS = 'RcloneCopies://'
_RESERVED = {name.casefold() for name in (
    COPIES, ENCRYPTED_COPIES, 'Local', 'LocalFiles', 'Inbox', RECEIVED, 'LocalCrypt', 'LocalCryptFolders', '.logistics-storage')}
_enabled = set()


def enabled(private_root):
    return Path(private_root) in _enabled


def reserved_phone_name(name):
    return name.casefold() in _RESERVED or name.startswith(('.incoming-', '.storage-copy-'))


def phone_path(private_root):
    from .locations import collection_base, shared_documents_path, _unlinked
    documents = shared_documents_path(private_root)
    if documents is not None:
        return _unlinked(documents)
    base = collection_base(private_root)
    from .migrations.mobile_layout import ensure_android_layout
    ensure_android_layout(private_root, base)
    return _unlinked(base / FILES)


def _parts(key):
    parts = key.split('/') if key else []
    if any(part in ('', '.', '..') or '\\' in part or '\0' in part for part in parts):
        raise ValueError('Invalid mobile file reference.')
    return parts


def split_alias(value):
    if isinstance(value, str):
        for prefix in (COPIES_ALIAS, FILES_ALIAS):
            if value.startswith(prefix):
                return prefix, PurePosixPath(*_parts(value[len(prefix):]))
    return None


def storage_reference(private_root, path):
    """Canonicalize an admitted path, leaving external references absolute."""
    from .locations import collection_path, _unlinked
    physical = _unlinked(Path(path).absolute()).resolve()
    if enabled(private_root):
        try:
            copies = collection_path(private_root).resolve()
            if physical.is_relative_to(copies):
                return COPIES_ALIAS + '/'.join(physical.relative_to(copies).parts)
            phone = phone_path(private_root).resolve()
            if physical.is_relative_to(phone):
                parts = physical.relative_to(phone).parts
                if not parts or not reserved_phone_name(parts[0]):
                    return FILES_ALIAS + '/'.join(parts)
        except OSError:
            pass  # A disconnected drive does not invalidate external files.
    return str(physical)


def alias_path(private_root, alias):
    from .locations import collection_path, _unlinked
    prefix, relative = alias
    if prefix == FILES_ALIAS and relative.parts and reserved_phone_name(relative.parts[0]):
        raise ValueError('This folder is managed by Logisticks.')
    root = collection_path(private_root) if prefix == COPIES_ALIAS else phone_path(private_root)
    return _unlinked(root / relative)
