"""Explicit application-service access for composed feature workflows."""


class HostAttribute:
    def __init__(self, name):
        self.name = name

    def __get__(self, owner, cls=None):
        return self if owner is None else getattr(owner.app, self.name)

    def __set__(self, owner, value):
        setattr(owner.app, self.name, value)

    def __delete__(self, owner):
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
