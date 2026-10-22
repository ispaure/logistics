"""Pure detached source/copy projection shared by desktop and mobile Folder Hub."""
from dataclasses import dataclass
from pathlib import PurePath

NETWORK_PACKAGES = frozenset({'network shares', 'session network shares'})


def credential_source(package):
    # Keep the full supplied identity: equal labels/stems do not prove ownership.
    return ('package', str(package)) if package is not None else ()


def source_category(feature, package=None):
    return ('Home Server' if feature == 'rclone' and package is not None
            and PurePath(str(package)).stem.casefold() in NETWORK_PACKAGES else 'Cloud')


class CredentialScope(frozenset):
    def __new__(cls, remotes, source):
        value = super().__new__(cls, remotes)
        value.source_identity = credential_source(source)
        return value

    def __reduce__(self):
        return type(self), (tuple(self), self.source_identity[1])

    def __eq__(self, other):
        return (frozenset.__eq__(self, other) and self.source_identity == other.source_identity
                if isinstance(other, CredentialScope) else frozenset.__eq__(self, other))

    def __ne__(self, other):
        return not self == other

    __hash__ = frozenset.__hash__


@dataclass(frozen=True)
class FolderCopy:
    identity: object
    name: str
    source_identity: tuple = ()
    category: str = 'Local'
    available: bool = True
    locked: bool = False
    payload: object = None


@dataclass(frozen=True)
class FolderProjection:
    identity: object
    name: str
    copies: tuple
    available: bool
    locked: bool


def project_catalog(copies, *, grouping='logical'):
    """Group by explicit source/scope or physical copy, never by displayed labels.

    Input order expresses adapter preference (for example loaded sync context
    before retained context). Equal physical copies are kept once in local views.
    """
    if grouping not in {'logical', 'physical'}:
        raise ValueError('Unknown folder catalog grouping.')
    groups = {}
    for copy in copies:
        key = copy.identity if grouping == 'physical' else (copy.source_identity, copy.name)
        members = groups.setdefault(key, [])
        if not any(previous.identity == copy.identity for previous in members):
            members.append(copy)
    return tuple(FolderProjection(key, members[0].name, tuple(members),
                                  any(item.available for item in members),
                                  all(item.locked for item in members))
                 for key, members in groups.items())
