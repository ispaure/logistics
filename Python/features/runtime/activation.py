"""Validate startup hooks and activate their owner-scoped registrations once."""
from types import ModuleType
from collections.abc import Callable


class FeatureActivation:
    def __init__(self):
        self.initialized = set()

    def hooks(self, features: list[ModuleType], definition_of, name: str) -> list[Callable[[], None]]:
        """Validate the full startup plan before invoking any feature hook."""

        hooks = []
        for feature in features:
            definition = definition_of(feature)
            hook = (definition.register_types if name == 'register_file_types' else definition.initialize) if definition is not None else getattr(feature, name, None)
            if hook is None:
                continue
            if not callable(hook):
                raise TypeError(f"Feature '{feature.__name__}' {name} must be callable.")
            hooks.append(hook)
        return hooks


    def activate(self, features, *, name_of, definition_of):
        # Validate all hooks before starting any work.
        self.hooks(features, definition_of, 'register_file_types')
        self.hooks(features, definition_of, 'initialize')
        from commonUtils.formats.registry import file_types, register_builtin_file_types
        register_builtin_file_types()
        for feature in features:
            definition = definition_of(feature)
            hook = definition.register_types if definition is not None else getattr(feature, 'register_file_types', None)
            if hook is not None and name_of(feature) not in self.initialized:
                with file_types.owner_scope(name_of(feature)):
                    hook()
        for feature in features:
            name = name_of(feature)
            if name not in self.initialized:
                definition = definition_of(feature)
                hook = definition.initialize if definition is not None else getattr(feature, 'initialize', None)
                if hook is not None:
                    hook()
                self.initialized.add(name)
