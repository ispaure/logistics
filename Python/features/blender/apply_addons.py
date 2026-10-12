"""Runs only in Blender: apply the requested library selection and save preferences."""
import json
from pathlib import Path
import sys

import addon_utils
import bpy

request = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text(encoding='utf-8'))
if request['extensions']:
    repos = bpy.context.preferences.extensions.repos
    repo = next((item for item in repos if item.module == 'logistics'), None)
    if repo is None:
        bpy.ops.preferences.extension_repo_add(name='Logistics', type='LOCAL', use_custom_directory=True,
                                              custom_directory=request['extensions'])
        repo = repos[-1]
        repo.module = 'logistics'
    repo.custom_directory = request['extensions']
    repo.use_custom_directory = True
    repo.enabled = True
bpy.utils.refresh_script_paths()
addon_utils.modules_refresh()
for module in request['disable']:
    addon_utils.disable(module, default_set=True)
# Preserve addon preference objects while deliberately rebuilding activation order.
for module in reversed(request['enable']):
    addon_utils.disable(module, default_set=False)
for module in request['enable']:
    errors = []
    addon_utils.enable(module, default_set=True, persistent=True, handle_error=lambda: errors.append(module))
    if errors or not addon_utils.check(module)[1]:
        raise RuntimeError(f'Could not enable {module}')
if 'FINISHED' not in bpy.ops.wm.save_userpref():
    raise RuntimeError('Could not save addon preferences')
