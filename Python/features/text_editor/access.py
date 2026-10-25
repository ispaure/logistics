"""Compatibility entry for the host-owned document write policy."""


def can_write(*, provider=None, reader=None):
    from services.documents.storage import document_writable
    return document_writable(reader, provider)
