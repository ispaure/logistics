"""Feature defaults in config.ini; private reading positions in the user cache."""
import hashlib
import json
from pathlib import Path
from commonUtils.persistence import atomic_write_json

from commonUtils.storage import cache_directory
from commonUtils.settings import get_setting

THEMES = {'light': ('#ffffff', '#202124'), 'dark': ('#111111', '#eeeeee'),
          'sepia': ('#f4ecd8', '#46392c'), 'slate': ('#202630', '#dde5ee')}


def defaults():
    path = Path(__file__).with_name('config.ini')
    def read(key, fallback, **bounds):
        return get_setting('Reader', key, fallback, path=path, **bounds)
    theme = read('theme_mode', 'sepia')
    return dict(font_size=read('font_size_int', 18, minimum=8, maximum=48),
                font_family=read('font_family_str', 'Georgia'),
                theme=theme if theme in THEMES else 'sepia', remember=read('remember_position_bool', True),
                reading_width=read('reading_width_int', 820, minimum=480, maximum=1400),
                line_spacing=read('line_spacing_int', 150, minimum=100, maximum=220))


class ReadingState:
    """One file per absolute book path: independent windows cannot lose other books.

    State contains reading preferences and up to 50 bookmarks, never book text.
    Changed chapters are validated by the reader before restoring a position.
    """
    def __init__(self, book_path, *, folder=None):
        identifier = hashlib.sha256(str(Path(book_path).resolve()).encode()).hexdigest()
        self.path = (Path(folder) if folder else cache_directory(create=False) / 'Books') / (identifier + '.json')

    def load(self):
        try:
            if self.path.stat().st_size > 128 * 1024:
                return {}
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                return {}
            expected = {'path': str, 'font_family': str, 'theme': str, 'font_size': int,
                        'line_spacing': int, 'reading_width': int, 'position': (int, float), 'location': int, 'bookmarks': list}
            return {key: value for key, value in data.items() if key in expected and isinstance(value, expected[key])}
        except (OSError, ValueError):
            return {}

    def save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write_json(self.path, data)
