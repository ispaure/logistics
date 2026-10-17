"""Explicit read-only host dependencies and compatibility state access.

Controllers enumerate the services they use; they never forward unknown names
or publish their workflow state onto the application object.
"""


class HostService:
    def __init__(self, name):
        self.name = name

    def __get__(self, owner, cls=None):
        return self if owner is None else getattr(owner.app, self.name)


class OwnedAttribute:
    """Expose legacy app attributes while keeping state on one workflow owner."""
    def __init__(self, factory, name):
        self.factory, self.name = factory, name

    def __get__(self, app, cls=None):
        return self if app is None else getattr(getattr(app, self.factory)(), self.name)

    def __set__(self, app, value):
        setattr(getattr(app, self.factory)(), self.name, value)
