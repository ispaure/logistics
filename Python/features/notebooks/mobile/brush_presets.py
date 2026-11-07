"""Device-local shortcuts for the mobile notebook toolbar."""
import json
from uuid import uuid4

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
    entries = json.loads(value)
    if not isinstance(entries, list) or len(entries) > MAX_PRESETS:
        raise ValueError('Invalid brush presets.')
    presets = []
    for entry in entries:
        if isinstance(entry, list):
            validate_preset(entry)
            entry = {'id': 'legacy-' + ','.join(map(str, entry)), 'brush': entry}
        if (not isinstance(entry, dict) or set(entry) != {'id', 'brush'}
                or not isinstance(entry['id'], str) or not 1 <= len(entry['id']) <= 64):
            raise ValueError('Invalid brush preset identity.')
        validate_preset(entry['brush'])
        presets.append(entry)
    if len({entry['id'] for entry in presets}) != len(presets):
        raise ValueError('Duplicate brush preset identities.')
    return presets


def change_preset(preferences, action):
    op = action['op']
    presets = read_presets(preferences.values.get(PREFERENCE, '[]'))
    if op != 'remove-brush-preset':
        brush = action.get('preset')
        validate_preset(brush)
    if op == 'add-brush-preset':
        if any(entry['brush'] == brush for entry in presets):
            return presets
        if len(presets) >= TOOLBAR_PRESET_LIMIT:
            raise ValueError('Remove a brush preset before adding another.')
        presets.append({'id': uuid4().hex, 'brush': brush})
    else:
        entry = next((entry for entry in presets if entry['id'] == action.get('id')), None)
        if entry is None:
            if op == 'remove-brush-preset':
                return presets
            raise ValueError('This brush preset was removed.')
        if op == 'remove-brush-preset':
            presets.remove(entry)
        else:
            entry['brush'] = brush
    preferences.save(**{PREFERENCE: json.dumps(presets, separators=(',', ':'))})
    return presets
