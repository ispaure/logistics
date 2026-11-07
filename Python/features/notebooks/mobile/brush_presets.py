"""Device-local shortcuts for the mobile notebook toolbar."""
import json

from ..brushes import BRUSHES, WIDTHS, native_color


PREFERENCE = 'notebook_brush_presets'
MAX_PRESETS = 32
TOOLBAR_PRESET_LIMIT = 2


def validate_preset(preset):
    if not isinstance(preset, list) or len(preset) != 3 or any(type(value) is not int for value in preset):
        raise ValueError('Invalid brush preset.')
    tool, color, width = preset
    native_color(tool, color)
    if width not in WIDTHS.values() or (BRUSHES[tool].get('fixed_width') and width != 1):
        raise ValueError('Invalid brush preset width.')


def read_presets(value):
    presets = json.loads(value)
    if not isinstance(presets, list) or len(presets) > MAX_PRESETS:
        raise ValueError('Invalid brush presets.')
    for preset in presets:
        validate_preset(preset)
    if len({tuple(preset) for preset in presets}) != len(presets):
        raise ValueError('Duplicate brush presets.')
    return presets


def change_preset(preferences, action):
    preset = action.get('preset')
    validate_preset(preset)
    presets = read_presets(preferences.values.get(PREFERENCE, '[]'))
    if action['op'] == 'add-brush-preset':
        if preset in presets:
            return presets
        if len(presets) >= TOOLBAR_PRESET_LIMIT:
            raise ValueError('Remove a brush preset before adding another.')
        presets.append(preset)
    elif preset in presets:
        presets.remove(preset)
    else:
        return presets
    preferences.save(**{PREFERENCE: json.dumps(presets, separators=(',', ':'))})
    return presets
