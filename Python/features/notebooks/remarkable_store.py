"""Read-only native-ID hierarchy; malformed ancestry never changes tablet data."""
from dataclasses import dataclass, field, replace
from collections.abc import Mapping
from types import MappingProxyType

from commonUtils.runtime.operations import check_cancelled
from .remarkable_ssh import UUID

ROOT = ''
UNFILED = 'unfiled'


@dataclass(frozen=True)
class TabletEntry:
    id: str
    title: str
    parent: str
    directory: bool
    issue: str = ''


@dataclass(frozen=True)
class InventoryRecord:
    """One native ID, with title-free accounting for every received occurrence."""
    id: str
    occurrences: int
    visible: bool
    reason: str
    read_issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class TabletSnapshot:
    entries: Mapping[str, TabletEntry]
    children: Mapping[str, tuple[str, ...]]
    inventory: Mapping[str, InventoryRecord] = field(default_factory=lambda: MappingProxyType({}))
    unidentified_records: int = 0

    @classmethod
    def from_metadata(cls, metadata, *, observations=None, cancelled=lambda: False):
        raw = {key: value for key, value in metadata.items()
               if isinstance(key, str) and UUID.fullmatch(key) and isinstance(value, dict)}
        hidden = {}
        for identity in raw:
            check_cancelled(cancelled)
            current, trail, seen = identity, [], set()
            omitted = False
            while isinstance(current, str) and current:
                check_cancelled(cancelled)
                if current == 'trash':
                    omitted = True
                    break
                if current in hidden:
                    omitted = hidden[current]
                    break
                if current in seen or current not in raw:
                    break
                seen.add(current)
                trail.append(current)
                if raw[current].get('deleted'):
                    omitted = True
                    break
                current = raw[current].get('parent')
            hidden.update((key, omitted) for key in trail)

        entries = {}
        for identity, value in raw.items():
            check_cancelled(cancelled)
            kind = value.get('type')
            if hidden[identity] or kind not in ('DocumentType', 'CollectionType'):
                continue
            directory = kind == 'CollectionType'
            title = str(value.get('visibleName') or ('Untitled folder' if directory else 'Untitled'))
            entries[identity] = TabletEntry(identity, title, ROOT, directory)
        for identity, entry in tuple(entries.items()):
            parent = raw[identity].get('parent')
            if parent is None or parent == ROOT:
                continue
            if isinstance(parent, str) and parent in entries and entries[parent].directory:
                entries[identity] = replace(entry, parent=parent)
            else:
                entries[identity] = replace(entry, parent=UNFILED, issue='Missing or invalid parent folder')

        visited = set()
        for identity in entries:
            current, trail, positions = identity, [], {}
            while current not in (ROOT, UNFILED) and current not in visited:
                check_cancelled(cancelled)
                if current in positions:
                    # One stable break retains the rest of a cyclic subtree.
                    broken = min(trail[positions[current]:])
                    entries[broken] = replace(entries[broken], parent=UNFILED, issue='Cyclic parent folders')
                    break
                positions[current] = len(trail)
                trail.append(current)
                current = entries[current].parent
            visited.update(trail)

        if any(entry.parent == UNFILED for entry in entries.values()):
            entries[UNFILED] = TabletEntry(UNFILED, 'Unfiled (invalid folder links)', ROOT, True,
                                           'Display-only group; the tablet is unchanged')
        entries[ROOT] = TabletEntry(ROOT, 'reMarkable', ROOT, True)
        children = {identity: [] for identity, entry in entries.items() if entry.directory}
        for identity, entry in entries.items():
            if identity != ROOT:
                children[entry.parent].append(identity)
        for items in children.values():
            items.sort(key=lambda key: (not entries[key].directory, entries[key].title.casefold(), key))
        # Transport observations retain malformed records that cannot enter the
        # hierarchy. Never put metadata values or arbitrary filenames in receipts.
        if observations is None:
            observations = ((key, 'read' if key in raw else 'unreadable_metadata') for key in metadata)
        counts, issues, unidentified = {}, {}, 0
        for identity, reason in observations:
            check_cancelled(cancelled)
            if not isinstance(identity, str) or not UUID.fullmatch(identity):
                unidentified += 1
                continue
            counts[identity] = counts.get(identity, 0) + 1
            if reason != 'read':
                issues.setdefault(identity, set()).add(reason)
        inventory = {}
        for identity, count in sorted(counts.items()):
            if identity in entries:
                reason = 'visible'
            elif identity not in raw:
                reason = 'unreadable_metadata'
            elif hidden[identity]:
                reason = 'deleted_or_trashed'
            else:
                reason = 'unsupported_type'
            inventory[identity] = InventoryRecord(identity, count, identity in entries, reason,
                                                   tuple(sorted(issues.get(identity, ()))))
        return cls(MappingProxyType(entries), MappingProxyType({key: tuple(value) for key, value in children.items()}),
                   MappingProxyType(inventory), unidentified)

    def ancestry(self, identity):
        result = [identity]
        while identity != ROOT:
            identity = self.entries[identity].parent
            result.append(identity)
        return tuple(reversed(result))

    def visible(self, query, directory=ROOT):
        """Keep matched folders' descendants and every matching item's ancestry."""
        query = query.strip().casefold()
        if not query:
            return None
        visible = set(self.ancestry(directory))
        pending = [(directory, query in self.entries[directory].title.casefold())]
        while pending:
            identity, ancestor_matches = pending.pop()
            matches = ancestor_matches or query in self.entries[identity].title.casefold()
            if matches:
                current = identity
                while current not in visible:
                    visible.add(current)
                    current = self.entries[current].parent
            pending.extend((key, matches) for key in self.children.get(identity, ()))
        return frozenset(visible)
