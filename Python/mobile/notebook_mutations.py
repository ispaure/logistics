"""Notebook draft retargeting within the existing verified file-operation plan."""
from hashlib import sha256
from pathlib import Path

from services.documents.storage import DocumentResource
from features.notebooks.notebook import Notebook, MAX_ARCHIVE


class NotebookMutations:
    def __init__(self, app, request):
        from .document_mutations import relative_document
        self.app, self.bindings = app, []
        owners = getattr(app.workspace, 'window_owners', None)
        hosts = list(owners.hosts.values()) if owners else [app]
        for host in hosts:
            for panel in getattr(host, '_notebook_views', {}).values():
                document = panel.document
                resource = document.resource if document else None
                if resource is None:
                    continue
                relative = relative_document(resource.provider, resource.path, request.provider, request.path)
                if relative is None:
                    continue
                if host is not app or panel.busy:
                    raise ValueError('Close the notebook in the other window or wait for its operation before moving it.')
                self.bindings.append((panel, document, relative, app.workspace.token(panel.session.id)))
        for panel, *_ in self.bindings:
            panel.busy = True

    def prepare(self, destination, target, cancelled):
        self.prepared = []
        for panel, document, relative, token in self.bindings:
            path = '/'.join(part for part in (target, relative) if part)
            if Path(path).suffix.lower() != '.rmdoc':
                raise ValueError('Keep the notebook extension, or close it before changing file type.')
            resource = document.resource
            baseline = resource.revision
            if resource.check()['revision'] != baseline:
                raise ValueError('The notebook changed on disk. Reload or use Save As before moving it.')
            data = resource.read(cancelled=cancelled)
            if resource.revision != baseline:
                raise ValueError('The notebook changed while preparing the move.')
            self.prepared.append((panel, document, path, token, sha256(data).digest()))

    def reopen(self, destination):
        updated = []
        try:
            for panel, document, path, token, digest in self.prepared:
                resource = DocumentResource(destination, path, max_bytes=MAX_ARCHIVE)
                try:
                    data = resource.read()
                    Notebook.read(data)
                    if sha256(data).digest() != digest:
                        raise ValueError('The moved notebook changed before reopening.')
                    updated.append((panel, document, resource, token))
                except BaseException:
                    resource.close()
                    raise
            return updated
        except BaseException:
            for _, _, resource, _ in updated:
                resource.close()
            raise

    def apply(self, updated):
        from features.notebooks.mobile.documents import adopt_notebook_document, repository
        from features.notebooks.storage import NotebookDocument
        from services.documents.mobile_storage import remember_notebook_resource
        for panel, previous, resource, token in updated:
            if not self.app.active_host or not self.app.workspace.accepts(token) or panel.document is not previous:
                resource.close()
                continue
            recovery = repository(self.app) if resource.policy.persistent else None
            document = NotebookDocument(previous.book, resource=resource, recovery=recovery,
                                        changed=remember_notebook_resource)
            document.dirty = previous.dirty
            remember_notebook_resource(document)
            adopt_notebook_document(self.app, panel, document)
            panel.session.dirty = document.dirty
        self.app.save_workspace()

    def release(self):
        for panel, *_ in self.bindings:
            panel.busy = False
