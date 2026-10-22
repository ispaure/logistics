"""Source-specific validity captures; no source bytes or persistence cross here."""


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
