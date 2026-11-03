"""Prepared document ownership before a platform publishes its new view."""
from dataclasses import dataclass, field
from .notes import MAX_NOTE, breadcrumb_folders, document_kind


@dataclass
class PreparedDocument:
    path: str
    kind: str | None
    folder_pages: dict = field(default_factory=dict)
    data: bytes = b''
    resources: object = None
    resource: object = None
    snapshot: object = None
    notebook: object = None
    preview: object = None
    rendered: object = None

    def close(self):
        """Dispose an unpublished result, including late cancelled reads."""
        for name in ('resources', 'resource', 'notebook', 'preview'):
            owned = getattr(self, name)
            setattr(self, name, None)
            if owned is not None:
                getattr(owned, 'close', lambda: None)()
        self.data, self.rendered, self.snapshot = b'', None, None


def prepare_document(library, path, *, current='', resolve_link=False,
                     cancelled=lambda: False, stage=lambda message: None,
                     notebooks_enabled=True):
    """Read a desktop document without publishing UI or changing history."""
    from commonUtils.runtime.operations import check_cancelled
    from services.documents.storage import DocumentResource
    provider = library.provider
    path, _, data = library.load_note(path, current=current, resolve_link=resolve_link,
                                    cancelled=cancelled, stage=stage)
    result = PreparedDocument(path, document_kind(path))
    try:
        folders = breadcrumb_folders(library.root, path)
        result.folder_pages = library.folder_pages(
            [{'path': folder, 'directory': True} for folder in folders], cancelled=cancelled)
        if result.kind is None:
            from .file_preview import FilePreview
            result.preview = FilePreview.open(provider, path, cancelled=cancelled)
            result.rendered = result.preview.page()
        elif result.kind == 'text':
            from commonUtils.persistence.text import decode_bytes
            result.resource = DocumentResource(provider, path, max_bytes=MAX_NOTE)
            result.snapshot = decode_bytes(result.resource.read(cancelled=cancelled), path=provider.root / path)
        elif result.kind == 'notebook':
            if not notebooks_enabled:
                raise ValueError('Enable Notebooks to open Remarkable Documents.')
            from features.notebooks.notebook import Notebook, MAX_ARCHIVE
            from features.notebooks.storage import NotebookDocument
            result.resource = DocumentResource(provider, path, max_bytes=MAX_ARCHIVE)
            result.notebook = NotebookDocument(Notebook.read(result.resource.read(cancelled=cancelled)),
                                               resource=result.resource)
            result.resource = None  # The notebook now owns this lease.
        else:
            from services.documents.markdown import prepare_markdown
            stage('Preparing embedded media…')
            result.data, result.resources = prepare_markdown(provider, provider.root / path, data=data,
                cancelled=cancelled, image_source=library.image_source(path, cancelled=cancelled))
        check_cancelled(cancelled)
        return result
    except BaseException:
        result.close()
        raise
