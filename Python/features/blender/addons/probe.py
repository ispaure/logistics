"""Run by Blender's own Python, never imported by Logistics.

Only inspect the saved preset; do not save preferences or change addon state.
"""
import json
from pathlib import Path
import sys
import tomllib

import addon_utils
import bpy


def inventory():
    enabled = set(bpy.context.preferences.addons.keys())
    result = []
    for module in addon_utils.modules():
        location = Path(module.__file__).resolve()
        info = getattr(module, 'bl_info', {})
        manifest = location.parent / 'blender_manifest.toml'
        is_extension = module.__name__.startswith('bl_ext.')
        if is_extension and manifest.is_file():
            try:
                info = {**info, **tomllib.loads(manifest.read_text(encoding='utf-8'))}
            except (OSError, ValueError):
                pass
        version = info.get('version', '')
        if isinstance(version, (tuple, list)):
            version = '.'.join(map(str, version))
        result.append({'module': module.__name__, 'name': info.get('name') or module.__name__,
                       'version': str(version), 'kind': 'Extension' if is_extension else 'Legacy addon',
                       'enabled': module.__name__ in enabled, 'path': str(location)})
    return sorted(result, key=lambda item: item['name'].casefold())


if __name__ == '__main__':
    output = Path(sys.argv[sys.argv.index('--') + 1])
    output.write_text(json.dumps(inventory(), ensure_ascii=False), encoding='utf-8')
