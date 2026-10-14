"""Feature INI defaults layered with private, schema-compatible user preferences."""

from pathlib import Path
from configparser import Error
import logging
from commonUtils.formats.iniType import INIFile
from commonUtils.configuration.settings import get_setting
from commonUtils.filesystem.storage import cache_directory

DEFAULTS = {
    "font_family_str": "",
    "font_size_int": 9,
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
        self.custom = path is not None
        self.path = (
            Path(path)
            if path
            else cache_directory(create=False) / "TextEditor" / "preferences.ini"
        )
        if not self.custom:
            from features.settings import settings_store, migration_ledger
            self.store = settings_store(Path(__file__).with_name('config.ini'))
            legacy = self.path
            self.path = self.store.personal
            already_applied = self.path.exists()
            def migrate():
                if not legacy.exists():
                    return
                from commonUtils.configuration.layered import read_values, shared_settings
                saved = read_values(legacy)
                current = self.store.overrides()
                editor = {identity: value for identity, value in saved.items() if identity not in current
                          and identity[0] == 'Editor' and identity[1] not in ('font_family_str', 'font_size_int')}
                if editor:
                    self.store.save(editor)
                fonts = {('Styling', 'code_' + key): value for (section, key), value in saved.items()
                         if section == 'Editor' and key in ('font_family_str', 'font_size_int')}
                style = shared_settings()
                fonts = {key: value for key, value in fonts.items() if key not in style.overrides()}
                if fonts:
                    style.save(fonts)
            try:
                migration_ledger(self.store).run('text-editor-v1', migrate, already_applied=already_applied)
            except (OSError, UnicodeError, Error, ValueError) as error:
                logging.getLogger(__name__).warning('Could not migrate editor preferences; original file preserved: %s', error)

    @property
    def font_path(self):
        return self.path if self.custom else None

    def load(self):
        values = {}
        defaults = Path(__file__).with_name("config.ini")
        for key, fallback in DEFAULTS.items():
            if not self.custom and key in ('font_family_str', 'font_size_int'):
                from commonUtils.ui.appearance.styling import style_values
                values[key] = style_values()['code_' + key]
                continue
            bounds = (
                {"minimum": 7, "maximum": 24}
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
            if not self.custom and key in ('font_family_str', 'font_size_int'):
                continue
            ini.set(
                "Editor",
                key,
                str(value).lower() if isinstance(value, bool) else str(value),
            )
        ini.save()
