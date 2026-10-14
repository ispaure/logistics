"""Process-local exclusive writers for independent system scenes."""


class WindowOwners:
    def __init__(self):
        self.hosts = {}
        self.writers = {}

    def attach(self, key, host):
        if key in self.hosts or len(self.hosts) >= 4:
            raise ValueError('Close a window before opening another (limit: 4).')
        self.hosts[key] = host

    def claim(self, key, identity, *, private=False):
        if private and len(self.hosts) > 1:
            raise ValueError('Close other windows before opening protected content.')
        owner = self.writers.get(identity)
        if owner is not None and owner != key:
            raise ValueError('This item is open in another window. Close it there before opening it here.')
        self.writers[identity] = key

    def release(self, key, identity):
        if self.writers.get(identity) == key:
            del self.writers[identity]

    def detach(self, key):
        self.hosts.pop(key, None)
        self.writers = {identity: owner for identity, owner in self.writers.items() if owner != key}

    def can_add(self):
        return len(self.hosts) < 4 and all(
            not any(session.transient for session in host.workspace.sessions.values())
            and not getattr(host, 'cloud_busy', False)
            for host in self.hosts.values())
