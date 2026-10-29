"""Small adapters for private desktop book/comic position contracts."""

from .credential_state import CredentialState


def desktop_state(provider, path, kind):
    from commonUtils.filesystem.storage import cache_directory

    return CredentialState(provider, path, cache_directory(create=False), kind=kind)


class PrivateComicState:
    def __init__(self, pages):
        self.state = desktop_state(pages.document.source, pages.path, "comic")

    def position(self, pages):
        from features.comics.reading_state import _position

        return _position(self.state.load(), pages)

    def save(self, index, pages):
        self.state.save(dict(page=index, name=pages[index], total=len(pages)))
