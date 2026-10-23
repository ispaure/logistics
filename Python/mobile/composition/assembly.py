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
        get_owner._workflow_controller = controller
        existing_factory = getattr(host, factory, None)
        registered = getattr(existing_factory, '_workflow_controller', None)
        if registered is not None and registered is not controller:
            raise ValueError(f'Workflow factory {factory!r} already belongs to {registered.__name__}')
        names = (*controller.METHODS, *controller.FIELDS)
        if len(set(names)) != len(names) or factory in names:
            raise ValueError(f'Duplicate workflow registration in {controller.__name__}')
        # Explicit host methods remain authoritative compatibility entry points.
        # Two controllers must never silently claim the same compatibility name.
        for name in names:
            existing = getattr(host, name, None)
            if isinstance(existing, OwnedAttribute) and existing.factory != factory:
                raise ValueError(f'Workflow attribute {name!r} already belongs to {existing.factory!r}')
        if factory not in host.__dict__:
            setattr(host, factory, get_owner)
        for name in names:
            if name not in host.__dict__:
                setattr(host, name, OwnedAttribute(factory, name))
        return host
    return decorate
