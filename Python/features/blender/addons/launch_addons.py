"""Runs in the interactive Blender process after normal startup/CLI processing."""
import json
import os

import addon_utils

# --addons is additive and skips already enabled addons. Rebuild the managed
# activation sequence without deleting preference objects or changing disk state.
modules = json.loads(os.environ.pop('LOGISTICS_BLENDER_ADDONS'))
for module in reversed(modules):
    addon_utils.disable(module, default_set=False)
for module in modules:
    errors = []
    addon_utils.enable(module, default_set=False, persistent=True, handle_error=lambda: errors.append(module))
    if errors or not addon_utils.check(module)[1]:
        raise RuntimeError(f'Could not enable {module}')
