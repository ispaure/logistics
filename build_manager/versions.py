"""Local monotonic reservations; remote uniqueness remains provider-owned."""
import json
from pathlib import Path

from .locking import workspace_lock


def next_number(path, *, existing=(), minimum=1):
    path = Path(path)
    previous = json.loads(path.read_text()).get('last', 0) if path.exists() else 0
    return max(minimum, previous + 1, max(existing, default=0) + 1)


def reserve_number(path, *, existing=(), minimum=1, maximum, override=None):
    path = Path(path)
    with workspace_lock(path.with_suffix('.lock')):
        number = next_number(path, existing=existing, minimum=minimum)
        if override is not None:
            selected = str(override)
            if not selected.isdigit() or int(selected) < number:
                raise ValueError('Explicit build must be increasing and unused in this local workspace.')
            number = int(selected)
        if number > maximum:
            raise ValueError('Build identifier exceeds the platform limit.')
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'schema': 1, 'last': number}) + '\n')
        temporary.replace(path)
        return number
