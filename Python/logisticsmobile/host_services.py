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

    def __delete__(self, app):
        delattr(getattr(app, self.factory)(), self.name)


def composed_workflow(factory, controller):
    """Install enumerated compatibility accessors; state stays on its controller."""
    def decorate(host):
        def get_owner(app):
            key = '_' + factory
            if key not in app.__dict__:
                app.__dict__[key] = controller(app)
            return app.__dict__[key]
        setattr(host, factory, get_owner)
        for name in (*controller.METHODS, *controller.FIELDS):
            if name not in host.__dict__:
                setattr(host, name, OwnedAttribute(factory, name))
        return host
    return decorate
