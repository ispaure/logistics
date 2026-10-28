"""Portable output consent policy. No toolkit, platform imports or device discovery."""
from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class Output:
    identity: str
    label: str
    bluetooth: bool = False


def output(platform, identity, label, *, bluetooth=False):
    # Device addresses/UIDs never enter preferences, status text or diagnostics.
    key = sha256((platform + ':' + identity).encode()).hexdigest() if identity else ''
    return Output(key, ' '.join(str(label).split())[:120] or 'Audio output', bluetooth)


def approvals(raw):
    rows = json.loads(raw)
    if not isinstance(rows, list) or len(rows) > 128:
        raise ValueError('Invalid approved Bluetooth devices.')
    result = {}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'id', 'name'}
                or not isinstance(row['id'], str) or len(row['id']) != 64
                or any(c not in '0123456789abcdef' for c in row['id'])
                or not isinstance(row['name'], str) or not 0 < len(row['name']) <= 120
                or any(ord(c) < 32 for c in row['name']) or row['id'] in result):
            raise ValueError('Invalid approved Bluetooth device.')
        result[row['id']] = row['name']
    return result


class OutputPolicy:
    def __init__(self):
        self.route = None  # None means unknown, never permission to play.
        self.revision = 0
        self.manual_play = False

    def observe(self, route):
        route = tuple(sorted(route, key=lambda item: item.identity)) if route else None
        # Names can change without changing output identity or authorization.
        changed = (None if self.route is None else tuple((x.identity, x.bluetooth) for x in self.route)) != (
            None if route is None else tuple((x.identity, x.bluetooth) for x in route))
        self.route = route
        if changed:
            self.revision += 1
            self.manual_play = False
        return changed

    def pending(self, approved):
        return tuple(item for item in self.route or () if item.bluetooth and item.identity not in approved)

    def identified(self):
        return bool(self.route) and all(item.identity for item in self.route)

    def permitted(self, approved):
        return self.identified() and not self.pending(approved) and self.manual_play

    def request_play(self, approved):
        self.manual_play = self.identified() and not self.pending(approved)
        return self.manual_play

    def pause(self):
        self.manual_play = False
