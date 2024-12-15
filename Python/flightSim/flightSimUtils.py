from commonUtils import fileUtils
from pathlib import Path
import config
import os
from commonUtils import pySideUtils


def get_xp12_dir():
    return Path(fileUtils.get_user_application_support(), 'Steam', 'steamapps', 'common', 'X-Plane 12')


def set_xp12_setting(line_to_look_for: str, value: int):
    # Getting file path to edit
    prefs_file = Path(get_xp12_dir(), 'Output', 'Preferences', 'X-Plane.prf')

    # Fetching existing lines
    prefs_line_lst = fileUtils.read_file(str(prefs_file))

    # Rebuilding lines with proper setting
    updated_prefs_line_lst = []
    for prefs_line in prefs_line_lst:
        if prefs_line.startswith(line_to_look_for):
            updated_prefs_line_lst.append(f'{line_to_look_for}{value}\n')
        else:
            updated_prefs_line_lst.append(f'{prefs_line}\n')

    # Output lines in file
    with open(prefs_file, 'w') as file:
        file.writelines(updated_prefs_line_lst)

    print(f'Successfully Changed XP12 setting "{line_to_look_for}" to "{value}"')


def set_xp12_fsr_setting(fsr_value: int):
    # Change Settings File (FSR Resolution Setting)
    set_xp12_setting(line_to_look_for='renopt_FSR_04 ', value=fsr_value)


def set_xp12_ssao_setting(ssao_value: int):
    # Change Settings File (SSAO)
    set_xp12_setting(line_to_look_for='renopt_SSAO_04 ', value=ssao_value)


def set_xp12_msaa_setting(msaa_value: int):
    # Change Settings File (MSAA)
    set_xp12_setting(line_to_look_for='renopt_MSAA ', value=msaa_value)


def set_xp12_vegetation_quality_setting(vegetation_quality_value: int):
    # Change Settings File (MSAA)
    set_xp12_setting(line_to_look_for='renopt_vegetation_quality_04 ', value=vegetation_quality_value)


def set_xp12_draw_3d_setting(draw_3d_value: int):
    # Change Settings File (MSAA)
    set_xp12_setting(line_to_look_for='renopt_draw_3d_04 ', value=draw_3d_value)


def set_xp12_draw_distance_setting(draw_distance_value: int):
    # Change Settings File (MSAA)
    set_xp12_setting(line_to_look_for='renopt_draw_distance04 ', value=draw_distance_value)


def set_xp12_shadow_quality_setting(shadow_quality_value: int):
    # Change Settings File (MSAA)
    set_xp12_setting(line_to_look_for='renopt_shadow_quality_04 ', value=shadow_quality_value)


def set_xp12_monitor_preset(preset_path: Path):
    if not os.path.isfile(preset_path):
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
    fileUtils.copy_file(preset_path, window_pref_file_path_steam)
    print(f'XP12 Preset Transferred from {preset_path} to {window_pref_file_path_steam}!')


def set_all_xp12_settings(preset_path: Path,
                          ssao: int,
                          fsr: int,
                          msaa: int,
                          draw_3d: int,
                          draw_distance: int,
                          shadow_quality: int,
                          vegetation_quality: int):

    # Set Monitor Preset
    set_xp12_monitor_preset(preset_path)

    # Update SSAO Setting
    set_xp12_ssao_setting(ssao)

    # Update FSR Setting
    set_xp12_fsr_setting(fsr)

    # Update MSAA Setting
    set_xp12_msaa_setting(msaa)

    # Update Draw3D
    set_xp12_draw_3d_setting(draw_3d)

    # Update Draw Distance
    set_xp12_draw_distance_setting(draw_distance)

    # Update Shadow Quality
    set_xp12_shadow_quality_setting(shadow_quality)

    # Update Vegetation Quality
    set_xp12_vegetation_quality_setting(vegetation_quality)


def set_xp12_m3_max_flight_desk_internal():

    # Get preset path
    logistics_cfg = config.LogisticsConfig()
    preset_path = Path(logistics_cfg.path_logistics_software, 'preset', 'X-Plane Window Positions [m3 max, flight desk, internal].prf')

    # Set all xp12 settings
    set_all_xp12_settings(preset_path=preset_path,
                          ssao=0,
                          fsr=3,
                          msaa=0,
                          draw_3d=2,
                          draw_distance=3,
                          shadow_quality=0,
                          vegetation_quality=2)


def set_xp12_m3_max_standalone():

    # Get preset path
    logistics_cfg = config.LogisticsConfig()
    preset_path = Path(logistics_cfg.path_logistics_software, 'preset', 'X-Plane Window Positions [m3 max, standalone].prf')

    # FSR Setting
    fsr_setting = 3

    # Set all xp12 settings
    set_all_xp12_settings(preset_path=preset_path,
                          ssao=2,
                          fsr=0,
                          msaa=1,
                          draw_3d=3,
                          draw_distance=4,
                          shadow_quality=2,
                          vegetation_quality=3)
