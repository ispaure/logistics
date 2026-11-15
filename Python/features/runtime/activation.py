"""Validate startup hooks and activate their owner-scoped registrations once."""

from dataclasses import dataclass
from collections.abc import Callable


@dataclass(frozen=True)
class StartupHooks:
    name: str
    register_types: Callable[[], None] | None
    initialize: Callable[[], None] | None


class FeatureActivation:
    def __init__(self):
        self.initialized = set()

    @staticmethod
    def _startup_hooks(feature, name, definition):
        if definition is None:
            register_types = getattr(feature, 'register_file_types', None)
            initialize = getattr(feature, 'initialize', None)
        else:
            register_types = definition.register_types
            initialize = definition.initialize

        for label, hook in (('register_file_types', register_types), ('initialize', initialize)):
            if hook is not None and not callable(hook):
                raise TypeError(f"Feature '{feature.__name__}' {label} must be callable.")
        return StartupHooks(name, register_types, initialize)

    def activate(self, features, *, name_of, definition_of):
        # Validate the full plan before running any hook. All formats must be
        # registered before any initializer can look up a file type.
        plan = [self._startup_hooks(feature, name_of(feature), definition_of(feature))
                for feature in features]
        from commonUtils.formats.registry import file_types, register_builtin_file_types

        register_builtin_file_types()
        pending = [hooks for hooks in plan if hooks.name not in self.initialized]
        for hooks in pending:
            if hooks.register_types is not None:
                with file_types.owner_scope(hooks.name):
                    hooks.register_types()
        for hooks in pending:
            if hooks.name in self.initialized:
                continue
            if hooks.initialize is not None:
                hooks.initialize()
            self.initialized.add(hooks.name)
