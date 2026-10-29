"""Explicit process credentials and window-owned retained protection sources.

Sources report existing challenges; they do not validate grants or perform I/O.
The host disposes its window scope. No UI observer inventory defines privacy.
"""
from weakref import WeakSet
from threading import RLock


def unique_gates(gates):
    return tuple({id(gate): gate for gate in gates if gate is not None}.values())


class ProtectionScope:
    def __init__(self, credentials):
        self._lock = RLock()
        self.credentials = credentials
        self.windows = WeakSet()
        self.listeners = WeakSet()
        self.active = bool(credentials())

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
        # Credential publication can originate on a worker; UI effects run after
        # the snapshot lock is released. Callbacks always consult current facts.
        with self._lock:
            active = self.protected()
            if active == self.active:
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
