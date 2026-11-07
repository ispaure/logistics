"""Identify redundant legacy imports without treating editing recovery as cache."""
from pathlib import Path

from .resource_imports import ResourceImports


def import_index(app):
    from services.documents.locations import collection_path
    try:
        collection = collection_path(app.private_root)
    except (OSError, ValueError):
        collection = None
    return ResourceImports(app.private_root, collection_root=collection)


def inventory(app):
    books, failures = app.reader_manager().catalog.library_store.stored_files()
    items = [dict(item, provider='library') for item in books]
    imports = import_index(app)
    if imports.error:
        failures.append(('text imports', imports.error))
        return items, failures
    keys = {value['resource'] for value in imports.items.values() if value['provider'] == 'managed-text'}
    for key in keys:
        try:
            document = app.store.open(key)
            size = sum(app.store.path(key, suffix).stat().st_size for suffix in ('.data', '.json'))
            items.append(dict(id=key, name=document.name, kind='text / Markdown',
                              size=size, provider='managed-text'))
        except (OSError, ValueError, KeyError, TypeError) as error:
            failures.append((key, str(error)))
    return sorted(items, key=lambda item: item['name'].casefold()), failures


def live_edits(app, item):
    if item['provider'] == 'managed-text':
        for owner in app.text_views.values():
            if owner.document is not None and owner.document.id == item['id']:
                if (owner.document.modified or owner.document.conflict
                        or owner.editor.value != owner.document.snapshot.text
                        or getattr(owner.document, 'private', False)):
                    return True
    else:
        for owner in app.reader_manager().controllers.values():
            if owner.session.resource == item['id']:
                initial = getattr(owner, 'book_metadata_initial', {})
                fields = getattr(owner, 'book_metadata_fields', {})
                if owner.book_busy or any(fields[name].value != value for name, value in initial.items()):
                    return True
    return False


def original_text_paths(app):
    """Resolve old hashed references only inside their original local roots."""
    import os
    imports = import_index(app)
    wanted = {key: value['resource'] for key, value in imports.items.items()
              if value['provider'] == 'managed-text'}
    if not wanted:
        return {}
    found = {}
    roots = [imports.collection_root, imports.shared_root, imports.received_root,
             Path(app.private_root) / 'Downloads', Path(app.private_root) / 'LocalFiles']
    candidates = [path for path in Path(app.private_root).iterdir() if path.is_file()]
    seen = set()

    def admit(path):
        try:
            if path.is_symlink():
                return
            key = imports.identity(path)
            if key in wanted:
                found.setdefault(wanted[key], []).append(path)
        except (OSError, ValueError):
            pass

    for path in candidates:
        admit(path)
    for root in roots:
        if root is None or not root.is_dir() or root.is_symlink() or root in seen:
            continue
        seen.add(root)
        for parent, folders, files in os.walk(root, followlinks=False):
            folders[:] = [name for name in folders if not (Path(parent) / name).is_symlink()]
            for name in files:
                admit(Path(parent) / name)
    return found


def duplicate_source(app, item, text_paths):
    """Recheck bytes; missing originals, saved changes and drafts are retained."""
    from commonUtils.runtime.streams import file_sha256
    from .document_sources import local_document_path
    if item['provider'] == 'library':
        store = app.reader_manager().catalog.library_store
        if store.edit_journal(item['id'], create=False).exists():
            return False
        record, _ = store.read_record(item['id'])
        source = record.get('source_path')
        if not source:
            return False
        paths = [local_document_path(app, source)]
        copy = store.path(item['id'], '.cbz' if record['kind'] == 'comic' else '.epub')
    else:
        document = app.store.open(item['id'])
        if document.modified or document.conflict:
            return False
        paths = text_paths.get(item['id'], ())
        copy = app.store.path(item['id'], '.data')
    digest = file_sha256(copy)
    for source in paths:
        if source.is_file() and not source.is_symlink() and source.resolve() != copy.resolve():
            before = source.stat()
            if before.st_size == copy.stat().st_size and file_sha256(source) == digest:
                after = source.stat()
                if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
                        after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    return True
    return False
