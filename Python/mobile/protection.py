"""Application-owned process scopes and per-window retained protection.

A native credential runtime supplies gates and publication notifications. It does
not create the scope. Separate runtimes (including isolated hosts) remain isolated.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from threading import RLock
from weakref import WeakKeyDictionary, ref
from services.protection import ProtectionScope

_processes = WeakKeyDictionary()
_lock = RLock()


def for_credentials(credentials):
    """Compose one process scope for the shared credential runtime, before any view."""
    with _lock, credentials.lock:
        scope = _processes.get(credentials)
        if scope is None:
            source = ref(credentials)
            scope = ProtectionScope()
            def gates():
                current = source()
                return current.privacy_gates() if current is not None else ()
            scope.register_credentials(object(), gates)
            credentials.protection_observers.add(scope)
            _processes[credentials] = scope
        return scope


def for_app(app):
    scope = getattr(app, '_protection', None)
    if scope is None:
        from features.rclone.mobile.cloud import CloudClient
        app._protection = scope = for_credentials(CloudClient.credential_state).window()
    return scope
