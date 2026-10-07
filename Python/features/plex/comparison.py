"""Compare Plex metadata without losing duplicate or incomplete entries."""

from collections import defaultdict, deque
import unicodedata


def _hashes(item):
    return {part['Hash'] for part in (item.media_part or []) if part.get('Hash')}


def _compare(left, right, key, hash_check):
    candidates = defaultdict(list)
    for index, item in enumerate(right):
        identity = key(item)
        if identity is not None:
            candidates[identity].append(index)
    left_hashes = [_hashes(item) for item in left] if hash_check else []
    right_hashes = [_hashes(item) for item in right] if hash_check else []
    assigned_left, assigned_right = {}, {}
    for start, item in enumerate(left):
        identity = key(item)
        if identity is None:
            continue
        # Reassign earlier pairs when necessary: a multi-part item must not
        # consume the only compatible candidate of a later duplicate entry.
        queue = deque([start])
        parents = {start: None}
        visited_right = set()
        found = False
        while queue and not found:
            current = queue.popleft()
            for target in candidates[identity]:
                if target in visited_right:
                    continue
                if hash_check and not left_hashes[current] & right_hashes[target]:
                    continue
                visited_right.add(target)
                owner = assigned_right.get(target)
                if owner is not None:
                    if owner not in parents:
                        parents[owner] = current
                        queue.append(owner)
                    continue
                while current is not None:
                    previous_target = assigned_left.get(current)
                    assigned_left[current] = target
                    assigned_right[target] = current
                    target, current = previous_target, parents[current]
                found = True
                break
    return {
        'Match': [[item, right[assigned_left[index]]] for index, item in enumerate(left) if index in assigned_left],
        'Only in 1': [item for index, item in enumerate(left) if index not in assigned_left],
        'Only in 2': [item for index, item in enumerate(right) if index not in assigned_right],
    }


def diff_metadata_item_cls_lsts_by_guid(left, right, hash_check=False):
    """Match nonempty GUIDs once per item; optionally require a shared media hash."""
    return _compare(left, right, lambda item: item.guid or None, hash_check)


def _episode_key(item):
    if item.tv_series_season_int is None or item.tv_series_episode_int is None:
        return None
    show = item.tv_series_guid
    if not show:
        title = (item.tv_series_title or '').strip()
        if not title:
            return None
        show = unicodedata.normalize('NFC', title).casefold()
    return show, item.tv_series_season_int, item.tv_series_episode_int


def diff_metadata_item_cls_lsts_by_info(left, right, hash_check=False):
    """Match episodes by series identity, season and episode, never missing indices."""
    return _compare(left, right, _episode_key, hash_check)
