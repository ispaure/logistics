"""Native retention requests keep storage ports separate from presentation.

The package store retains original password-protected ZIPs, whereas the client's
vault retains decoded credentials. Neither request contains a ZIP password.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class NativeCredentialRetention:
    store: object = field(repr=False)
    package: object = field(repr=False)
    remotes: tuple[str, ...]
    generation: int
    crypt_remotes: tuple[str, ...] = ()


@dataclass(frozen=True)
class NativeCredentialForget:
    # Resolve lazily so a broken package index cannot prevent live revocation
    # or erasure of the independent saved-credential vault.
    packages: Callable[[], object] = field(repr=False)
    document_cache_root: Path


@dataclass(frozen=True)
class NativeCredentialMetadata:
    store: object = field(repr=False)
    key: str
    generation: int
    crypt_remotes: tuple[str, ...]
    aliases: dict[str, str] = field(default_factory=dict)


def retain(client, request):
    if not isinstance(request, (NativeCredentialRetention, NativeCredentialMetadata)):
        raise TypeError('Choose an original ZIP and its protected package store.')
    if request.store.client is not client:
        raise ValueError('This package store belongs to another credential client.')
    if request.generation != client.generation:
        raise ValueError('Credentials changed before ZIP retention. Try loading it again.')
    if isinstance(request, NativeCredentialMetadata):
        return request.store.update_crypt_remotes(request.key, request.crypt_remotes, aliases=request.aliases)
    identities = {remote: client.connection_identity(remote) for remote in request.remotes}
    aliases = next((item.get('aliases', {}) for item in getattr(client, 'package_records', ())
                    if item['package_name'] == request.package.name), {})
    aliases = {name: alias for name, alias in aliases.items() if alias in identities}
    return request.store.remember(request.package, identities, aliases=aliases,
                                  crypt_remotes=request.crypt_remotes)


def forget(client, request):
    if request is not None and not isinstance(request, NativeCredentialForget):
        raise ValueError('This runtime forgets all saved credentials together.')
    failure = None
    operations = [client.clear]
    if request is not None:
        def forget_packages():
            store = request.packages()
            if store is not None:
                if store.client is not client:
                    raise ValueError('This package store belongs to another credential client.')
                store.forget()
        from .document_lists import forget_cache
        operations.extend((forget_packages, lambda: forget_cache(request.document_cache_root)))
    for operation in operations:
        try:
            operation()
        except Exception as error:
            failure = failure or error
    if failure is not None:
        raise failure
