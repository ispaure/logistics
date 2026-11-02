"""Desktop host credential scope for video; feature code consumes this policy."""


def session_contexts():
    from features.rclone import session
    return tuple(sorted((path for path in session.paths() if path.suffix == '.session'), key=str))


def require_external(content):
    content.require_external()
    if session_contexts():
        raise PermissionError('Floating and casting are unavailable while session-only credentials are loaded.')


def process_authorization():
    from features.rclone import session
    from features.rclone.desktop_credentials import SessionResumeProof
    contexts = session_contexts()
    if not contexts:
        return None, ()
    # Retain generation checks as well as the opening package's password proof.
    checks = tuple(session.revocation_check(path) for path in contexts)
    return SessionResumeProof(session.package_path(contexts[0])), checks
