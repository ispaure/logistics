"""Private comic resume positions, keyed by resolved file path."""

import hashlib
import json
from pathlib import Path

from commonUtils.configuration.settings import get_setting
from commonUtils.filesystem.storage import cache_directory
from commonUtils.persistence import atomic_write_json
from commonUtils.runtime.streams import read_up_to

MAX_STATE_BYTES = 128 * 1024


def remember_position():
    return get_setting('Reader', 'remember_position_bool', True,
                       path=Path(__file__).parent.parent / 'books' / 'config.ini')


def _position(state, pages):
    try:
        # Keep the same image after insertions/reordering where possible.
        if state.get('name') in pages:
            return pages.index(state['name'])
        index = state.get('page', 0)
        return max(0, min(index, len(pages) - 1)) if type(index) is int else 0
    except (OSError, ValueError):
        return 0


class ReadingState:
    def __init__(self, comic_path, *, folder=None):
        from services.documents.history_controls import PositionLease
        self._position_lease = PositionLease()
        self.comic_path = Path(comic_path).resolve()
        self.root = Path(folder) if folder else cache_directory(create=False)
        identifier = hashlib.sha256(str(self.comic_path).encode()).hexdigest()
        self.path = (Path(folder) if folder is not None else cache_directory(create=False) / 'Comics') / (identifier + '.json')

    def _load(self):
        if not self._position_lease.valid():
            return {}
        try:
            with self.path.open('rb') as stream:
                content = read_up_to(stream, MAX_STATE_BYTES + 1)
            if len(content) > MAX_STATE_BYTES:
                return {}
            state = json.loads(content.decode('utf-8'))
            return state if isinstance(state, dict) else {}
        except (OSError, ValueError):
            return {}

    def position(self, pages):
        return _position(self._load(), pages)

    def save(self, index, pages):
        if not self._position_lease.valid():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._position_lease.publish(lambda: atomic_write_json(self.path, dict(page=index, name=pages[index], total=len(pages)),
                          max_bytes=MAX_STATE_BYTES))

    def badge(self, pages=None, *, revisions=None):
        from services.documents.progress import open_progress

        try:
            progress = open_progress(None, self.comic_path, self.root, kind='desktop-comic')
            state = progress.load()
            if progress.can_import_legacy:
                state = self._load()
            progress.retire()
            if revisions is not None and 'member_revision' in state:
                state['page'] = verified_comic_index(state, pages, revisions)
            if type(state.get('page')) is not int:
                return ''
            total = len(pages) if pages is not None else state.get('total')
            if type(total) is not int or total <= 0:
                return ''
            index = _position(state, pages) if pages is not None else max(0, min(state['page'], total - 1))
            return f'{index + 1}/{total}'
        except (OSError, ValueError):
            return ''


def open_comic_progress(comic, folder=None):
    from services.documents.progress import open_progress

    source = comic.document.source
    path = comic.path
    root = folder or cache_directory(create=False)
    progress = open_progress(source, path, root, kind='desktop-comic')
    record = progress.load()
    if progress.can_import_legacy:
        if comic.document.private:
            from services.documents.reader_positions import desktop_state

            previous = desktop_state(source, path, 'comic')
            legacy = previous.load()
            if previous.locked_state:
                progress.load_status = 'locked'
                progress.retire()
        else:
            legacy = ReadingState(path, folder=folder)._load()
        if legacy.get('name') in comic.progress_pages:
            record = comic_location(comic, comic.pages.index(legacy['name']))
            progress.save(record)
    return progress, verified_comic_index(record, comic.pages, comic.progress_pages)


def verified_comic_index(record, pages, revisions):
    name, signature = record.get('name'), record.get('member_revision')
    if name in revisions and revisions[name] == signature:
        return pages.index(name)
    index = record.get('page')
    if type(index) is int and 0 <= index < len(pages) and revisions[pages[index]] == signature:
        return index
    return 0


def comic_location(comic, index):
    name = comic.pages[index]
    return dict(page=index, name=name, total=len(comic.pages), member_revision=comic.progress_pages[name])
