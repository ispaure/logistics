"""Text-session adapters for ordinary provider-backed app documents."""
from pathlib import Path
from .access import can_write


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


class LocalTextCopies:
    """Verified local text saves for an editor retargeted out of LocalCrypt."""
    encrypted = False

    def __init__(self, provider):
        self.provider = provider

    @property
    def offline(self):
        from commonUtils.runtime.resources.local import LocalFiles
        return isinstance(self.provider, LocalFiles)

    def open(self, key, *, password='', cancelled=lambda: False, read_provider=None):
        from commonUtils.runtime.resources.selection import ResourceTextSession
        session = ResourceTextSession.open(read_provider if read_provider is not None else self.provider,
                                          key, cancelled=cancelled)
        reader = TextReader(session.text.name, session.text.data, key=session.path, revision=session.text.revision)
        reader.read_only = not can_write(provider=self.provider)
        return reader

    def save(self, reader, text, *, cancelled=lambda: False):
        if not can_write(provider=self.provider, reader=reader):
            raise ValueError('Remote Markdown is read-only. Create a local copy before editing.')
        from commonUtils.runtime.resources.selection import ResourceTextSession
        session = ResourceTextSession(self.provider, reader.key, reader.session)
        updated = session.save(text, cancelled=cancelled)
        return TextReader(updated.text.name, updated.text.data, key=updated.path, revision=updated.text.revision)
