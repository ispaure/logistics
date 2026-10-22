"""Lazy controller assembly with explicitly enumerated compatibility accessors."""
from services.workflow_host import OwnedAttribute


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
