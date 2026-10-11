"""Systemic Git defaults in the repository; accounts/repositories stay private."""
from pathlib import Path
import re
from commonUtils.configuration.ini_schema import parse_value
from commonUtils.configuration.settings import get_setting
from .options import DEFAULTS, validate_options

FIELDS = {key: value for key, value in DEFAULTS.items()
          if type(value) in (bool, int, str) and key != 'diff_font'}
BOUNDS = {'fetch_minutes': (1, 1440), 'commit_guide': (20, 200), 'diff_limit_kb': (16, 16384)}
COLOR_FIELDS = ('added_text_color_str', 'added_background_color_str', 'removed_text_color_str', 'removed_background_color_str')


def color_settings():
    values = {key: get_setting('DiffColors', key, '', path=config_path()) for key in COLOR_FIELDS}
    return {key: value if re.fullmatch(r'#[0-9a-fA-F]{6}', value) else '' for key, value in values.items()}


def config_path():
    return Path(__file__).with_name('config.ini')


def field_key(key):
    if key in ('terminal', 'pull_strategy'):
        return key + '_mode'
    return key + '_' + {bool: 'bool', int: 'int', str: 'str'}[type(FIELDS[key])]


def defaults():
    path = config_path()
    result = {}
    for key, fallback in FIELDS.items():
        bounds = dict(zip(('minimum', 'maximum'), BOUNDS[key])) if key in BOUNDS else {}
        result[key] = get_setting('Git', field_key(key), fallback, path=path, **bounds)
    for key, choices in (('terminal', ('System default', 'Terminal', 'iTerm')), ('pull_strategy', ('ff-only', 'merge', 'rebase'))):
        if result[key] not in choices:
            result[key] = DEFAULTS[key]
    return validate_options(result)


def validate(values):
    parsed = {key: parse_value({bool: 'bool', int: 'int', str: 'str'}[type(default)],
                              values.get(('Git', field_key(key)), str(default)))
              for key, default in FIELDS.items()}
    validate_options(parsed)
    if not values.get(('Git', 'executable_str'), 'git').strip():
        raise ValueError('Choose a Git executable')
    for key in COLOR_FIELDS:
        value = values.get(('DiffColors', key), '')
        if value and not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            raise ValueError(f'{key}: use #RRGGBB, or leave empty to follow the theme')
