"""Dependency ordering and availability, independent of registration and settings."""
from collections.abc import Callable, Sequence, Mapping
from types import ModuleType


def available(feature_name: str, feature_map: Mapping[str, ModuleType],
              dependencies: Callable, resolving: tuple[str, ...] = ()) -> bool:
    feature = feature_map.get(feature_name)
    if feature is None or getattr(feature, 'FEATURE_LOAD_ERROR', None):
        return False
    if feature_name in resolving:
        chain = ' -> '.join((*resolving, feature_name))
        raise RuntimeError(f'Circular Logistics feature dependency: {chain}')
    return all(available(name, feature_map, dependencies, (*resolving, feature_name))
               for name in dependencies(feature))


def initialization_order(features: Sequence[ModuleType], name_of: Callable,
                         dependencies: Callable) -> list[ModuleType]:
    """Visit hard dependencies first, preserving discovery order where possible."""
    feature_map = {name_of(feature): feature for feature in features}
    if len(feature_map) != len(features):
        raise ValueError('Duplicate Logistics feature names in initialization list.')
    ordered, initialized = [], set()

    def visit(name, chain=()):
        if name in initialized:
            return
        if name in chain:
            raise RuntimeError('Circular Logistics feature dependency: ' + ' -> '.join((*chain, name)))
        if name not in feature_map:
            raise RuntimeError('Missing Logistics feature dependency: ' + ' -> '.join((*chain, name)))
        feature = feature_map[name]
        for dependency in dependencies(feature):
            visit(dependency, (*chain, name))
        initialized.add(name)
        ordered.append(feature)

    for feature in features:
        visit(name_of(feature))
    return ordered
