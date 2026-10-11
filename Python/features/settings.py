"""Logistics owns the paths; commonUtils owns layered configuration mechanics."""
from pathlib import Path

from commonUtils.configuration.layered import LayeredSettings, register_settings
from commonUtils.configuration.settings import settings_path
from features.preferences import preferences_path


def settings_store(path):
    path = Path(path).resolve()
    root = Path(__file__).resolve().parents[1]
    if path == settings_path().resolve():
        name = Path('commonUtils') / 'settings.ini'
    else:
        try:
            name = path.relative_to(root)
        except ValueError:
            if path == root.parent / 'launch_config.ini':
                name = Path('launch_config.ini')
            else:
                # Feature-owned external configuration retains its own storage.
                return LayeredSettings(path, preferences_path().parent / 'configuration' / path.name)
    return register_settings(path, preferences_path().parent / 'configuration' / name)


def initialize_settings():
    root = Path(__file__).resolve().parents[1]
    paths = [settings_path(), root / 'configFile.ini', root / 'maintenance.ini', root.parent / 'launch_config.ini']
    paths += [path for path in (root / 'features').glob('*/config.ini') if path.parent.name != 'emulation']
    for path in paths:
        settings_store(path)


def validate_configuration(path, values):
    path = Path(path).resolve()
    if path.parent.name == 'git':
        from features.git.configuration import validate
        validate(values)
    elif path.parent.name == 'books':
        from features.books.preferences import THEMES
        for key, low, high in (('line_spacing_int', 100, 220), ('reading_width_int', 480, 1400)):
            if not low <= int(values.get(('Reader', key), low)) <= high:
                raise ValueError(f'{key}: choose a value between {low} and {high}')
        if values.get(('Reader', 'theme_mode'), 'sepia') not in THEMES:
            raise ValueError('Choose a supported reading theme')
    elif path.parent.name == 'text_editor':
        if not 1 <= int(values.get(('Editor', 'indent_width_int'), 4)) <= 16:
            raise ValueError('Indentation width must be between 1 and 16')
