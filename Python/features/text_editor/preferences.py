"""Feature INI defaults layered with private, schema-compatible user preferences."""

from pathlib import Path
from commonUtils.formats.iniType import INIFile
from commonUtils.configuration.settings import get_setting
from commonUtils.filesystem.storage import cache_directory

DEFAULTS = {
    "font_family_str": "",
    "font_size_int": 12,
    "indent_width_int": 4,
    "use_tabs_bool": False,
    "word_wrap_bool": False,
    "line_numbers_bool": True,
    "whitespace_bool": False,
    "auto_indent_bool": True,
    "auto_pairs_bool": False,
    "syntax_highlighting_bool": True,
    "geometry_str": "",
}


class Preferences:
    def __init__(self, path=None):
        self.path = (
            Path(path)
            if path
            else cache_directory(create=False) / "TextEditor" / "preferences.ini"
        )

    def load(self):
        values = {}
        defaults = Path(__file__).with_name("config.ini")
        for key, fallback in DEFAULTS.items():
            bounds = (
                {"minimum": 7, "maximum": 48}
                if key == "font_size_int"
                else {"minimum": 1, "maximum": 16}
                if key == "indent_width_int"
                else {}
            )
            default = get_setting("Editor", key, fallback, path=defaults, **bounds)
            values[key] = get_setting("Editor", key, default, path=self.path, **bounds)
        return values

    def save(self, values):
        ini = INIFile(self.path)
        if self.path.exists():
            ini.read()
        for key, value in values.items():
            if key not in DEFAULTS:
                continue
            ini.set(
                "Editor",
                key,
                str(value).lower() if isinstance(value, bool) else str(value),
            )
        ini.save()
