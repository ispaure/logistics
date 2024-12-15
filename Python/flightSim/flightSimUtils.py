from commonUtils import fileUtils
from pathlib import Path
import config
import os
from commonUtils import pySideUtils


def get_xp12_dir():
    return Path(fileUtils.get_user_application_support(), 'Steam', 'steamapps', 'common', 'X-Plane 12')


def set_xp12_monitor_w_internal():

    # Get preset path
    logistics_cfg = config.LogisticsConfig()
    window_pref_file_path_preset = Path(logistics_cfg.path_logistics_software, 'preset', 'X-Plane Window Positions.prf')
    if not os.path.isfile(window_pref_file_path_preset):
        msg = 'Preset file is missing, cannot apply preset!'
        pySideUtils.display_msg_box_ok('XP12 Preset', msg)
        return

    # Get steam path of file
    window_pref_file_path_steam = Path(get_xp12_dir(), 'Output', 'Preferences', 'X-Plane Window Positions.prf')
    if not os.path.isfile(window_pref_file_path_steam):
        msg = 'Preset file is missing from X-Plane 12 installation. is X-Plane installed?'
        pySideUtils.display_msg_box_ok('XP12 Preset', msg)
        return

    # Validated input-output, now transfer file!
    fileUtils.copy_file(window_pref_file_path_preset, window_pref_file_path_steam)
    
    print('XP12 Preset Transferred!')

