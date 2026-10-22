"""Runs in background Blender: configure selection without importing UI/GPU addons."""
import json
import os
from pathlib import Path
import sys

import addon_utils
import bpy

request = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text(encoding='utf-8'))
# --factory-startup prevents saved addons (including Deluxe's selection) from
# importing before this script. Load the real preferences with activation paused,
# so all artist settings and addon ID properties survive without GPU/UI imports.
original_enable = addon_utils.enable
addon_utils.enable = lambda *args, **kwargs: None
try:
    preferences = Path(os.environ['BLENDER_USER_CONFIG']) / 'userpref.blend'
    if preferences.is_file():
        if 'FINISHED' not in bpy.ops.wm.read_userpref():
            raise RuntimeError('Could not load preset preferences')
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
    # Background mode cannot register addons that need a GPU or an interactive UI.
    # Record intent here; launch_addons.py validates activation in interactive Blender.
    # Keep existing entries so their AddonPreferences properties survive the update.
    addons = bpy.context.preferences.addons
    for module in request['enable']:
        if addons.get(module) is None:
            addon = addons.new()
            addon.module = module
    if 'FINISHED' not in bpy.ops.wm.save_userpref():
        raise RuntimeError('Could not save addon preferences')
finally:
    addon_utils.enable = original_enable
