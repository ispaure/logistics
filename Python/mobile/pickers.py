"""Logistics document naming and export bounds over native system pickers."""
from pathlib import Path
from commonUtils.ui.native.documents import export_stream, pick_document as select_document


async def pick_document(app):
    return await select_document(app, title='Import text document')


async def export_document(app, name, content, *, max_bytes=None, mime_type=None):
    """Export a copy through an explicit system destination selection."""
    from .documents import document_name, MAX_BYTES
    name = document_name(name)
    limit = MAX_BYTES if max_bytes is None else max_bytes
    if not isinstance(limit, int) or not 0 < limit <= 32 * MAX_BYTES or len(content) > limit:
        raise ValueError(f'Export is limited to {limit // MAX_BYTES if isinstance(limit, int) else 1} MiB.')
    from io import BytesIO
    return await export_stream(app, name, lambda: BytesIO(content), mime_type=mime_type or ('text/markdown' if name.lower().endswith('.md') else 'text/plain'))


async def export_file(app, path, *, mime_type='application/octet-stream'):
    """Stream an existing private download to an explicitly chosen destination."""
    from .documents import document_name
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('The private download is no longer available.')
    return await export_stream(app, document_name(path.name), lambda: path.open('rb'), mime_type=mime_type)
