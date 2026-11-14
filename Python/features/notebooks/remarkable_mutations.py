"""Revision-bound native metadata plans; no connection or device writes.

Plans use raw records, never the browser's repaired display hierarchy. A device
adapter must still obtain writer exclusion, verify every guard, publish safely
and verify native acceptance before reporting a completed operation.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json

from .remarkable_ssh import MAX_SIDECAR, UUID


@dataclass(frozen=True)
class MetadataRevision:
    identity: str
    sha256: str


@dataclass(frozen=True)
class MetadataChange:
    identity: str
    operation: str
    before: bytes
    after: bytes
    guards: tuple[MetadataRevision, ...]

    @property
    def changed(self):
        return self.before != self.after


def _identity(value):
    if not isinstance(value, str) or not UUID.fullmatch(value):
        raise ValueError('Choose a native document or folder ID.')
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate native metadata fields prevent modification.')
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError('Non-finite native metadata values prevent modification.')


def _decode(data):
    if not isinstance(data, bytes) or len(data) > MAX_SIDECAR:
        raise ValueError('Choose a bounded, immutable native metadata record.')
    try:
        value = json.loads(data, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError('Malformed native metadata prevents modification.') from error
    if not isinstance(value, dict) or value.get('type') not in {'DocumentType', 'CollectionType'}:
        raise ValueError('Unsupported native metadata type.')
    if not isinstance(value.get('visibleName'), str) or len(value['visibleName']) > 512:
        raise ValueError('Invalid native name prevents modification.')
    parent = value.get('parent')
    if parent not in ('', 'trash'):
        _identity(parent)
    if 'deleted' in value and type(value['deleted']) is not bool:
        raise ValueError('Invalid native deletion state.')
    modified = value.get('lastModified')
    if not isinstance(modified, str) or not modified.isascii() or not modified.isdecimal() or len(modified) > 19:
        raise ValueError('Unsupported native modification timestamp.')
    return value


def plan_metadata_change(records: Mapping[str, bytes], identity: str, operation: str, *,
                         modified_ms: int, title: str | None = None, destination: str | None = None) -> MetadataChange:
    """Prepare rename/move/trash/restore for explicit native records and ancestry.

Unknown fields survive. Every consumed record becomes a revision guard, including
source/destination ancestors. Missing or malformed ancestry fails closed. Restore
uses an explicit destination; it never guesses the previous parent from Trash.
"""
    _identity(identity)
    if operation not in {'rename', 'move', 'trash', 'restore'}:
        raise ValueError('Unsupported native metadata operation.')
    if type(modified_ms) is not int or not 0 <= modified_ms < 2**63:
        raise ValueError('Choose a valid native modification time.')
    if (operation == 'rename') != (title is not None):
        raise ValueError('Only rename accepts a new name.')
    if (operation in {'move', 'restore'}) != (destination is not None):
        raise ValueError('Move and restore require an explicit destination.')
    guards, decoded, originals = {}, {}, {}

    def record(key):
        _identity(key)
        if key not in decoded:
            data = records.get(key)
            if data is None:
                raise ValueError('A native record is missing; refresh before modifying it.')
            decoded[key] = _decode(data)
            originals[key] = data
            guards[key] = MetadataRevision(key, sha256(data).hexdigest())
        return decoded[key]

    def live_ancestry(key, *, forbid=None):
        seen = set()
        while key:
            if key == 'trash':
                raise ValueError('Restore the containing folder before modifying this item.')
            if key == forbid or key in seen:
                raise ValueError('A folder cannot contain itself or one of its ancestors.')
            seen.add(key)
            parent = record(key)
            if parent['type'] != 'CollectionType':
                raise ValueError('The native destination or ancestor is not a folder.')
            if parent.get('deleted'):
                raise ValueError('The native destination or ancestor is deleted.')
            key = parent['parent']

    current = record(identity)
    directly_trashed = current['parent'] == 'trash' or current.get('deleted', False)
    if operation == 'restore':
        if not directly_trashed:
            raise ValueError('Choose an item directly in Trash to restore.')
    else:
        if directly_trashed:
            raise ValueError('Restore this item before modifying it.')
        live_ancestry(current['parent'], forbid=identity)

    changed = dict(current)
    if operation == 'rename':
        if (not isinstance(title, str) or not title.strip() or len(title) > 512
                or any(ord(character) < 32 or character in '\x7f\x85\u2028\u2029' for character in title)):
            raise ValueError('Choose a nonempty name without control characters, up to 512 characters.')
        changed['visibleName'] = title
    elif operation == 'trash':
        changed['parent'] = 'trash'
    else:
        if destination != '':
            _identity(destination)
        live_ancestry(destination, forbid=identity)
        changed['parent'] = destination
        if operation == 'restore' and changed.get('deleted'):
            changed['deleted'] = False

    before = originals[identity]
    if changed == current:
        after = before
    else:
        modified = max(modified_ms, int(current['lastModified']) + 1)
        if modified >= 2**63:
            raise ValueError('Native modification time is out of range.')
        changed['lastModified'] = str(modified)
        after = (json.dumps(changed, ensure_ascii=False, allow_nan=False, indent=4) + '\n').encode('utf-8')
        if len(after) > MAX_SIDECAR:
            raise ValueError('Updated native metadata exceeds the size limit.')
    return MetadataChange(identity, operation, before, after, tuple(guards[key] for key in sorted(guards)))


def verify_metadata_revisions(change: MetadataChange, records: Mapping[str, bytes]) -> None:
    """Check the target and all decision-making ancestors before publication."""
    for guard in change.guards:
        actual = records.get(guard.identity)
        if not isinstance(actual, bytes) or sha256(actual).hexdigest() != guard.sha256:
            raise ValueError('The tablet item or its folder changed; refresh and review the operation again.')
