"""Text-session adapters for ordinary provider-backed app documents."""
from pathlib import Path


class TextReader:
    """Mobile presentation adapter for the shared text session."""
    editable = True
    book = None

    def __init__(self, name, data, *, key=None, revision=None):
        from commonUtils.persistence.text import TextSession
        self.session = TextSession(name, data, key=key, revision=revision, max_bytes=1024 * 1024)
        self.name, self.data, self.key, self.revision = name, data, key, revision
        self.kind = Path(name).suffix.lower()
        self.text_snapshot, self.text = self.session.text_snapshot, self.session.text
        self.labels = [name]

    def page(self, index):
        if index != 0:
            raise ValueError('Page does not exist.')
        return 'text', self.text


# Compatibility for existing callers; composition belongs to the document host.
from services.documents.mobile_storage import TextDocumentCopies as LocalTextCopies
