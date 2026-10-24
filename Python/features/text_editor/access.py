"""Storage permission used by Markdown entry points and local text persistence."""


def can_write(*, provider=None, reader=None):
    """Private local storage is writable; a remote or read-only source never is.

    Some adapters expose their underlying provider. Inspect both layers so a
    local cache or a text-session wrapper cannot turn a remote into an editor.
    The provider still owns capability checks and revision-safe publication.
    """
    seen = set()
    for source in (reader, provider):
        while source is not None and id(source) not in seen:
            seen.add(id(source))
            if getattr(source, 'remote_storage', False) or getattr(source, 'read_only', False):
                return False
            capabilities = getattr(source, 'capabilities', None)
            if capabilities is not None and not capabilities.replace:
                return False
            source = getattr(source, 'provider', None)
    return True
