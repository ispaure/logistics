"""Nonsecret credential snapshots and folder-group projection, without widgets.

Labels are presentation only. Every group retains its complete package identity,
including when two packages have the same basename or remote names.
"""
from dataclasses import dataclass
from pathlib import Path

from services.folders.catalog import CredentialScope
from services.folders.policy import visible_name

NETWORK_PACKAGES = frozenset({'Network shares', 'Session network shares'})


@dataclass(frozen=True)
class PackageSnapshot:
    """Nonsecret package metadata; aliases map original names to bridge names."""
    name: str
    remotes: tuple[str, ...]
    saved: bool
    aliases: tuple[tuple[str, str], ...]


class CredentialCatalog:
    def __init__(self, records):
        self.packages = tuple(
            PackageSnapshot(
                name=record.get('package_name', ''),
                remotes=tuple(record.get('remotes', ())),
                saved=bool(record.get('saved')),
                aliases=tuple(record.get('aliases', {}).items()),
            )
            for record in records
        )

    def visible_remotes(self, names, exclusions):
        originals = {alias: original for package in self.packages for original, alias in package.aliases}
        return sorted((name for name in names if visible_name(originals.get(name, name), exclusions, remote=True)),
                      key=str.casefold)

    def label(self, fallback=''):
        if not self.packages:
            return 'Credential package: ' + (fallback or 'none')
        return 'Loaded:\n' + '\n'.join(package.name + (' (Persistent save)' if package.saved else ' (Session-Only)')
                                      for package in self.packages)

    def groups(self, available, *, visible):
        groups = {'All': None}
        available = set(available)
        for package in self.packages:
            if package.name in NETWORK_PACKAGES or not visible(Path(package.name).name):
                continue
            remotes = set(package.remotes) & available
            name = Path(package.name).name
            base = name[:-4] if name.lower().endswith('.zip') else name
            title = base
            number = 2
            while title in groups:
                title = f'{base} ({number})'
                number += 1
            groups[title] = CredentialScope(remotes, package.name)
        return groups


@dataclass(frozen=True)
class AssociationUpdate:
    saved: list[dict]
    sessions: list[dict]


def remember_association(previous, sessions, name, remotes, *, session_only):
    """Keep session-only associations out of the persisted preference projection."""
    saved = [item for item in previous if item['zip'] != name and not item['session_only']]
    sessions = [item for item in sessions if item['zip'] != name]
    association = dict(zip=name, remotes=list(remotes), session_only=session_only)
    if session_only:
        sessions.append(association)
    else:
        saved.append(association)
    return AssociationUpdate(saved[-32:], sessions)
