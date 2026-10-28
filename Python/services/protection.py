"""Explicit process credentials and window-owned retained protection sources.

Sources report existing challenges; they do not validate grants or perform I/O.
The host disposes its window scope. No UI observer inventory defines privacy.
"""
from weakref import WeakSet


class ProtectionScope:
    def __init__(self, credentials):
        self.credentials = credentials
        self.windows = WeakSet()

    def window(self):
        window = WindowProtection(self)
        self.windows.add(window)
        return window

    def protected(self):
        return bool(self.credentials()) or any(window.retained_gates() for window in tuple(self.windows))


class WindowProtection:
    def __init__(self, process):
        self.process = process
        self.sources = {}
        self.closed = False

    def register(self, owner, gates):
        if self.closed:
            raise ValueError('The protection scope is closed.')
        key = id(owner)
        entry = (owner, gates)
        self.sources[key] = entry
        def release():
            if self.sources.get(key) is entry:
                self.sources.pop(key, None)
        return release

    def retained_gates(self):
        if self.closed:
            return ()
        return tuple(dict.fromkeys(gate for _, source in tuple(self.sources.values())
                                   for gate in source() if gate is not None))

    def gates(self):
        if self.closed:
            return ()
        return tuple(dict.fromkeys((*self.process.credentials(), *self.retained_gates())))

    def dispose(self):
        self.closed = True
        self.sources.clear()
        self.process.windows.discard(self)
