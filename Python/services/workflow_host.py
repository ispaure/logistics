"""Explicit application-service access for composed feature workflows."""


class HostAttribute:
    def __init__(self, name, *, writable=True):
        self.name, self.writable = name, writable

    def __get__(self, owner, cls=None):
        return self if owner is None else getattr(owner.app, self.name)

    def __set__(self, owner, value):
        if not self.writable:
            raise AttributeError(f'Host capability {self.name} is read-only')
        setattr(owner.app, self.name, value)

    def __delete__(self, owner):
        if not self.writable:
            raise AttributeError(f'Host capability {self.name} is read-only')
        delattr(owner.app, self.name)


class StateAttribute:
    """Compatibility access to an explicitly named owned state record."""
    def __init__(self, state, name):
        self.state, self.name = state, name

    def __get__(self, owner, cls=None):
        return self if owner is None else getattr(getattr(owner, self.state), self.name)

    def __set__(self, owner, value):
        setattr(getattr(owner, self.state), self.name, value)

    def __delete__(self, owner):
        delattr(getattr(owner, self.state), self.name)


class HostService(HostAttribute):
    """Read-only capability; writable compatibility fields opt in explicitly."""
    def __init__(self, name):
        super().__init__(name, writable=False)


class OwnedAttribute:
    """A writable app compatibility view onto one lazily constructed owner."""
    def __init__(self, factory, name):
        self.factory, self.name = factory, name

    def __get__(self, app, cls=None):
        return self if app is None else getattr(getattr(app, self.factory)(), self.name)

    def __set__(self, app, value):
        setattr(getattr(app, self.factory)(), self.name, value)

    def __delete__(self, app):
        delattr(getattr(app, self.factory)(), self.name)
