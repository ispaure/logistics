"""Private comic resume positions, keyed by resolved file path."""

import hashlib
import json
from pathlib import Path

from commonUtils.configuration.settings import get_setting
from commonUtils.filesystem.storage import cache_directory
from commonUtils.persistence import atomic_write_json


def remember_position():
    return get_setting('Reader', 'remember_position_bool', True,
                       path=Path(__file__).parent.parent / 'books' / 'config.ini')


class ReadingState:
    def __init__(self, comic_path, *, folder=None):
        identifier = hashlib.sha256(str(Path(comic_path).resolve()).encode()).hexdigest()
        self.path = (Path(folder) if folder is not None else cache_directory(create=False) / 'Comics') / (identifier + '.json')

    def position(self, pages):
        try:
            if self.path.stat().st_size > 128 * 1024:
                return 0
            state = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(state, dict):
                return 0
            # Keep the same image after insertions/reordering where possible.
            if state.get('name') in pages:
                return pages.index(state['name'])
            index = state.get('page', 0)
            return max(0, min(index, len(pages) - 1)) if type(index) is int else 0
        except (OSError, ValueError):
            return 0

    def save(self, index, pages):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write_json(self.path, dict(page=index, name=pages[index], total=len(pages)))

    def badge(self, pages=None):
        try:
            if self.path.stat().st_size > 128 * 1024:
                return ''
            state = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(state, dict) or type(state.get('page')) is not int:
                return ''
            total = len(pages) if pages is not None else state.get('total')
            if type(total) is not int or total <= 0:
                return ''
            index = self.position(pages) if pages is not None else max(0, min(state['page'], total - 1))
            return f'{index + 1}/{total}'
        except (OSError, ValueError):
            return ''
