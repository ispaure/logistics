"""Feature defaults in config.ini; private reading positions in the user cache."""
import hashlib
import json
from pathlib import Path
from commonUtils.persistence import atomic_write_json

from commonUtils.filesystem.storage import cache_directory
from commonUtils.configuration.settings import get_setting

THEMES = {'light': ('#ffffff', '#202124'), 'dark': ('#111111', '#eeeeee'),
          'sepia': ('#f4ecd8', '#46392c'), 'slate': ('#202630', '#dde5ee')}

APPEARANCE_KEYS = {'font_family': ('Styling', 'reading_font_family_str'),
                   'font_size': ('Styling', 'reading_font_size_int'),
                   'line_spacing': ('Reader', 'line_spacing_int'),
                   'reading_width': ('Reader', 'reading_width_int'),
                   'theme': ('Reader', 'theme_mode')}


def appearance_store(key):
    from features.settings import settings_store
    from commonUtils.configuration.layered import shared_settings
    return shared_settings() if key in ('font_family', 'font_size') else settings_store(Path(__file__).with_name('config.ini'))


def defaults():
    path = Path(__file__).with_name('config.ini')
    def read(key, fallback, **bounds):
        return get_setting('Reader', key, fallback, path=path, **bounds)
    theme = read('theme_mode', 'sepia')
    return dict(font_size=get_setting('Styling', 'reading_font_size_int', 10, minimum=7, maximum=24),
                font_family=get_setting('Styling', 'reading_font_family_str', 'Arial'),
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
                        'line_spacing': int, 'reading_width': int, 'position': (int, float), 'location': int, 'bookmarks': list,
                        'chapter': int, 'chapters': int}
            return {key: value for key, value in data.items() if key in expected and isinstance(value, expected[key])}
        except (OSError, ValueError):
            return {}

    def save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write_json(self.path, data)

    def badge(self, spine=None):
        state = self.load()
        total, chapter = state.get('chapters'), state.get('chapter')
        if spine is not None:
            if state.get('path') not in spine:
                return ''
            total, chapter = len(spine), spine.index(state['path'])
        if type(total) is not int or type(chapter) is not int or total <= 0 or not 0 <= chapter < total:
            return ''
        return f'Ch {chapter + 1}/{total}'
