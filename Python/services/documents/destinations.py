"""Captured picker requests and publication; no widgets or navigation state."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from dataclasses import dataclass
from pathlib import Path

from commonUtils.runtime.operations import MutationIncomplete
from commonUtils.runtime.resources.selection import ResourceSelection
from .storage import DocumentResource


@dataclass(frozen=True)
class DestinationPublication:
    destination: str
    status: str
    copies: object = None
    prepared: object = None
    error: Exception | None = None

    def require_reopened(self):
        if self.error is not None:
            raise self.error
        return self.copies, self.destination, self.prepared


@dataclass(frozen=True)
class DestinationRequest:
    provider: object
    folder: str
    filename: str
    data: bytes
    extensions: tuple
    notebook: bool
    creating: bool
    max_bytes: int
    store: object
    source_document: object
    notebook_setup: tuple[str, str] | None = None

    @classmethod
    def capture(cls, provider, folder, filename, data, extensions, *, notebook,
                creating, session_count, session_limit, store, source_document,
                notebook_template='Blank', notebook_format='pro'):
        from features.notebooks.notebook import MAX_ARCHIVE

        maximum = MAX_ARCHIVE if notebook else 1024 * 1024
        if Path(filename).suffix.lower() not in extensions or len(data) > maximum:
            raise ValueError('Choose a text, source or configuration filename; saves are limited to 1 MiB.')
        if creating:
            from services.documents.names import document_name
            if session_count >= session_limit:
                raise ValueError('Close an open document before creating another (limit: 32).')
            document_name(filename)
            if Path(filename).suffix.lower() not in {'.txt', '.md', '.markdown', '.rmdoc'}:
                raise ValueError('Choose a TXT, Markdown or notebook filename.')
            if getattr(provider, 'remote_storage', False):
                raise ValueError('Cloud files are read-only. Create locally and use Push.')
        return cls(provider, folder, filename, bytes(data), tuple(extensions), notebook,
                   creating, maximum, store, source_document,
                   (notebook_template, notebook_format) if creating and notebook else None)

    def resolve(self, *, cancelled):
        model = ResourceSelection(self.provider, mode='save', extensions=self.extensions)
        try:
            return model.resolve(self.folder, self.filename, cancelled=cancelled), None
        except FileExistsError:
            destination = '/'.join(part for part in (model.relative(self.folder), self.filename) if part)
            entry = self.provider.entry(destination)
            if entry['directory']:
                raise ValueError('A folder with this name already exists. Choose another name.')
            if self.creating:
                raise FileExistsError('A destination with this name already exists. Choose another name.')
            return destination, entry['revision']

    def publish(self, destination, revision, *, cancelled):
        from .mobile_storage import document_copies
        try:
            data = self.data
            if self.notebook_setup is not None:
                from features.notebooks.notebook import Notebook
                from features.notebooks.remarkable_export import save_rmdoc

                template, paper_format = self.notebook_setup
                book = Notebook.new(Path(self.filename).stem, template=template, paper_format=paper_format)
                data = save_rmdoc(book, cancelled=cancelled)
            if self.provider.private and self.source_document is not None:
                self.store.privatize(self.source_document)
            copies = None if self.notebook else document_copies(self.provider)

            def reopen():
                if self.notebook:
                    from features.notebooks.notebook import Notebook
                    with self.provider.open(destination) as stream:
                        Notebook.read(stream.read(len(data) + 1))
                    return None
                reader = copies.open(destination)
                if reader.data != data:
                    raise ValueError('The saved file changed after publication.')
                kind, content = reader.page(0)
                return reader, kind, content

            prepared = DocumentResource.publish(self.provider, destination, data,
                max_bytes=self.max_bytes, expected_revision=revision, cancelled=cancelled,
                after_publish=lambda revision: reopen())
            return DestinationPublication(destination, 'published', copies, prepared)
        except MutationIncomplete as error:
            status = 'published-not-reopened' if error.result.destination_published else 'unchanged'
            return DestinationPublication(destination, status, error=error)
        except Exception as error:
            return DestinationPublication(destination, 'unchanged', error=error)
