"""Shared desktop and mobile document write capability."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"


def can_write(*, provider=None, reader=None):
    from services.documents.storage import document_writable
    return document_writable(reader, provider)
