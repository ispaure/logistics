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
