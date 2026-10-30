"""Explicit process credentials and window-owned retained protection sources.

Sources report existing challenges; they do not validate grants or perform I/O.
The host disposes its window scope. No UI observer inventory defines privacy.
"""
from weakref import WeakSet
from threading import RLock


def unique_gates(gates):
    return tuple({id(gate): gate for gate in gates if gate is not None}.values())


class ProtectionScope:
    def __init__(self, credentials=lambda: ()):
        self._lock = RLock()
        self._credential_sources = {None: (None, credentials)}
        self.windows = WeakSet()
        self.listeners = WeakSet()
        self.active = bool(credentials())
        self._revision = 0

    def credentials(self):
        with self._lock:
            sources = tuple(self._credential_sources.values())
        return unique_gates(gate for _, source in sources for gate in source())

    def register_credentials(self, owner, gates):
        """Register a credential source without giving it ownership of this scope."""
        key = id(owner)
        entry = (owner, gates)
        with self._lock:
            self._credential_sources[key] = entry
        self.changed()
        def release():
            with self._lock:
                if self._credential_sources.get(key) is entry:
                    self._credential_sources.pop(key)
            self.changed()
        return release

    def credentials_changed(self):
        self.changed()

    def window(self):
        window = WindowProtection(self)
        self.windows.add(window)
        return window

    def retain(self, owner, gates, *, protected=None):
        """Keep a resource protected across asynchronous window shutdown.

        The returned bound release owns this scope until actual disposal ends.
        """
        resource = self.window()
        resource.register(owner, gates, protected=protected)
        return resource.dispose

    def protected(self):
        return bool(self.credentials()) or any(window.retained_protected() for window in tuple(self.windows))

    def changed(self):
        # Suppliers may acquire credential locks. Never call them while holding
        # the scope lock: credential publication can enter here in the opposite
        # order. A newer publication supersedes a slow older snapshot.
        with self._lock:
            self._revision += 1
            revision = self._revision
        active = self.protected()
        with self._lock:
            if revision != self._revision or active == self.active:
                return
            self.active = active
            listeners = tuple(self.listeners)
        failure = None
        for listener in listeners:
            try:
                listener.protection_changed(active)
            except Exception as error:
                failure = failure or error
        if failure is not None:
            raise failure


class WindowProtection:
    def __init__(self, process):
        self.process = process
        self.sources = {}
        self.closed = False

    def register(self, owner, gates, *, protected=None):
        if self.closed:
            raise ValueError('The protection scope is closed.')
        key = id(owner)
        entry = (owner, gates, protected)
        self.sources[key] = entry
        self.process.changed()
        def release():
            if self.sources.get(key) is entry:
                self.sources.pop(key, None)
                self.process.changed()
        return release

    def changed(self):
        self.process.changed()

    def retained_gates(self):
        if self.closed:
            return ()
        return unique_gates(gate for _, source, _ in tuple(self.sources.values()) for gate in source())

    def retained_protected(self):
        return bool(self.retained_gates()) or (not self.closed and any(
            protected() for _, _, protected in tuple(self.sources.values()) if protected is not None))

    def gates(self):
        if self.closed:
            return ()
        return unique_gates((*self.process.credentials(), *self.retained_gates()))

    def dispose(self):
        self.closed = True
        self.sources.clear()
        self.process.windows.discard(self)
        self.process.changed()
