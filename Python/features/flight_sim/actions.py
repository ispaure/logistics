"""
Actions for the Logistics Flight Simulator feature.
"""

from pathlib import Path

import config

from commonUtils import fileUtils
from commonUtils.debugUtils import Severity, log
from commonUtils.fileTypes import txtType

from features.flight_sim import detection


def set_xp12_setting(line_to_look_for: str, value: int):
    """Set a value in the X-Plane 12 preferences file."""

    prefs_file = txtType.TXTFile(detection.get_xp12_preferences_path())
    prefs_file.read_lines()

    updated_prefs_line_lst = []

    for prefs_line in prefs_file.line_lst:
        if prefs_line.startswith(line_to_look_for):
            updated_prefs_line_lst.append(f'{line_to_look_for}{value}')
        else:
            updated_prefs_line_lst.append(prefs_line)

    prefs_file.line_lst = updated_prefs_line_lst
    prefs_file.write_lines()

    print(f'Successfully Changed XP12 setting "{line_to_look_for}" to "{value}"')


def set_xp12_fsr_setting(fsr_value: int):
    set_xp12_setting(line_to_look_for='renopt_FSR_04 ', value=fsr_value)


def set_xp12_ssao_setting(ssao_value: int):
    set_xp12_setting(line_to_look_for='renopt_SSAO_04 ', value=ssao_value)


def set_xp12_msaa_setting(msaa_value: int):
    set_xp12_setting(line_to_look_for='renopt_MSAA ', value=msaa_value)


def set_xp12_vegetation_quality_setting(vegetation_quality_value: int):
    set_xp12_setting(line_to_look_for='renopt_vegetation_quality_04 ', value=vegetation_quality_value)


def set_xp12_draw_3d_setting(draw_3d_value: int):
    set_xp12_setting(line_to_look_for='renopt_draw_3d_04 ', value=draw_3d_value)


def set_xp12_draw_distance_setting(draw_distance_value: int):
    set_xp12_setting(line_to_look_for='renopt_draw_distance04 ', value=draw_distance_value)


def set_xp12_shadow_quality_setting(shadow_quality_value: int):
    set_xp12_setting(line_to_look_for='renopt_shadow_quality_04 ', value=shadow_quality_value)


def set_xp12_monitor_preset(preset_path: Path):
    """Copy an X-Plane 12 window-position preset into the active preferences."""

    if not preset_path.is_file():
        msg = 'Preset file is missing, cannot apply preset!'
        log(Severity.ERROR, 'XP12 Preset', msg, popup=True)
        return

    window_pref_file_path = detection.get_xp12_window_positions_path()

    if not window_pref_file_path.is_file():
        msg = 'X-Plane 12 window preferences file is missing. Is X-Plane installed?'
        log(Severity.ERROR, 'XP12 Preset', msg, popup=True)
        return

    fileUtils.copy_file(preset_path, window_pref_file_path)
    print(f'XP12 Preset Transferred from {preset_path} to {window_pref_file_path}!')


def set_all_xp12_settings(
        preset_path: Path,
        ssao: int,
        fsr: int,
        msaa: int,
        draw_3d: int,
        draw_distance: int,
        shadow_quality: int,
        vegetation_quality: int):

    set_xp12_monitor_preset(preset_path)
    set_xp12_ssao_setting(ssao)
    set_xp12_fsr_setting(fsr)
    set_xp12_msaa_setting(msaa)
    set_xp12_draw_3d_setting(draw_3d)
    set_xp12_draw_distance_setting(draw_distance)
    set_xp12_shadow_quality_setting(shadow_quality)
    set_xp12_vegetation_quality_setting(vegetation_quality)


def set_xp12_m3_max_flight_desk_internal():
    logistics_cfg = config.LogisticsConfig()
    preset_path = Path(
        logistics_cfg.path_logistics_software_general,
        'x-plane',
        'X-Plane Window Positions [m3 max, flight desk, internal].prf'
    )

    set_all_xp12_settings(
        preset_path=preset_path,
        ssao=0,
        fsr=3,
        msaa=0,
        draw_3d=2,
        draw_distance=3,
        shadow_quality=0,
        vegetation_quality=2
    )


def set_xp12_m3_max_standalone():
    logistics_cfg = config.LogisticsConfig()
    preset_path = Path(
        logistics_cfg.path_logistics_software_general,
        'x-plane',
        'X-Plane Window Positions [m3 max, standalone].prf'
    )

    set_all_xp12_settings(
        preset_path=preset_path,
        ssao=2,
        fsr=0,
        msaa=1,
        draw_3d=3,
        draw_distance=4,
        shadow_quality=2,
        vegetation_quality=3
    )


def set_xp12_m3_max_office():
    logistics_cfg = config.LogisticsConfig()
    preset_path = Path(
        logistics_cfg.path_logistics_software_general,
        'x-plane',
        'X-Plane Window Positions [m3 max, office].prf'
    )

    set_all_xp12_settings(
        preset_path=preset_path,
        ssao=2,
        fsr=2,
        msaa=1,
        draw_3d=3,
        draw_distance=3,
        shadow_quality=2,
        vegetation_quality=3
    )
