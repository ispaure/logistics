"""Mobile host composition for document adapters; formats see provider sessions."""


def document_copies(provider):
    from features.rclone.localcrypt.mobile.resources import encrypted_document
    from features.text_editor.resources import LocalTextCopies
    # Keep native archive/metadata transactions with their storage owner.
    source = encrypted_document(provider, '') if hasattr(provider, 'copies') else None
    if source is not None:
        return source[0]
    if getattr(provider, 'private', False):
        from features.rclone.localcrypt.mobile.resources import encrypted_copies
        return encrypted_copies(provider)
    return LocalTextCopies(provider)


async def confirm_export(app, resource):
    """An OS export or ordinary recovery target publishes outside private storage."""
    if resource is None or resource.policy.persistent:
        return True
    import toga
    return await app.main_window.dialog(toga.ConfirmDialog(
        'Export to unencrypted storage?',
        'This creates a decrypted copy outside private storage. Continue?'))


def notebook_binding(recovery, key):
    from pathlib import Path
    from features.notebooks.notebook import identifier
    return Path(recovery.root) / identifier(key) / 'source.json'


def restore_notebook_resource(recovery, key):
    """Ordinary recovery references only; private sessions never call this adapter."""
    import json
    from commonUtils.runtime.resources.local import LocalFiles
    from services.documents.storage import DocumentResource
    from features.notebooks.notebook import MAX_ARCHIVE
    path = notebook_binding(recovery, key)
    if not path.exists():
        return None, None
    if path.is_symlink() or path.stat().st_size > 16384:
        raise ValueError('Invalid notebook source binding.')
    value = json.loads(path.read_text())
    from pathlib import Path
    if not Path(value['root']).is_dir():
        return None, value
    provider = LocalFiles(value['root'])
    return DocumentResource(provider, value['path'], max_bytes=MAX_ARCHIVE), value


def remember_notebook_resource(document):
    """Host policy permits ordinary references; format code supplies no paths."""
    from commonUtils.persistence import atomic_write_json
    resource = document.resource
    if resource is None or not resource.policy.persistent or document.recovery is None:
        return
    atomic_write_json(notebook_binding(document.recovery, document.key),
        dict(root=str(resource.provider.root), path=resource.path,
             revision=resource.revision, dirty=document.dirty), durable_directory=True)
