"""Source-specific validity captures; no source bytes or persistence cross here."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"


def capture_library(owner):
    reader, epoch = owner.book_reader, owner.book_epoch
    return lambda: (owner.book_reader is reader and owner.book_epoch == epoch
                    and getattr(owner, 'active_host', True))


def capture_provider(owner, view):
    reader = view.crypt_reader
    workspace, session = getattr(view, 'workspace', None), getattr(view, 'session', None)
    token = workspace.token(session.id) if workspace is not None and session is not None else None
    return lambda: (view.crypt_reader is reader and getattr(owner, 'active_host', True)
                    and (token is None or workspace.accepts(token)))
