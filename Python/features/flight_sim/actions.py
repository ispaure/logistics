"""
Actions for the Logistics Flight Simulator feature.
"""

from pathlib import Path

import config


from features.flight_sim import detection


def _updated_preferences(path, values):
    original = path.read_bytes()
    bom = original.startswith(b'\xef\xbb\xbf')
    lines = original.decode('utf-8-sig').splitlines(keepends=True)
    for key, value in values.items():
        if type(value) is not int or value < 0:
            raise ValueError(f'Invalid X-Plane value for {key}: {value}')
        matches = [i for i, line in enumerate(lines) if line.startswith(key)]
        if len(matches) != 1:
            raise ValueError(f'X-Plane setting is missing or duplicated: {key.strip()}')
        index = matches[0]
        line = lines[index]
        ending = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else '\r' if line.endswith('\r') else ''
        lines[index] = f'{key}{value}{ending}'
    updated = ''.join(lines).encode('utf-8')
    return original, (b'\xef\xbb\xbf' + updated if bom else updated)


def _publish_preferences(path, original, updated):
    from commonUtils.persistence import atomic_write_bytes
    from uuid import uuid4
    def unchanged():
        if path.read_bytes() != original:
            raise RuntimeError(f'Preferences changed outside Logistics: {path}')
    unchanged()
    backup = path.with_name(f'{path.name}.previous-{uuid4().hex}')
    atomic_write_bytes(backup, original, overwrite=False)
    atomic_write_bytes(path, updated, validate=unchanged)
    return backup


def set_xp12_setting(line_to_look_for: str, value: int):
    path = detection.get_xp12_preferences_path()
    original, updated = _updated_preferences(path, {line_to_look_for: value})
    _publish_preferences(path, original, updated)
    return True


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
    path = detection.get_xp12_window_positions_path()
    _publish_preferences(path, path.read_bytes(), Path(preset_path).read_bytes())
    return True


def set_all_xp12_settings(preset_path: Path, ssao: int, fsr: int, msaa: int,
                         draw_3d: int, draw_distance: int, shadow_quality: int,
                         vegetation_quality: int):
    from commonUtils.persistence import atomic_write_bytes
    path = detection.get_xp12_preferences_path()
    window = detection.get_xp12_window_positions_path()
    values = {'renopt_SSAO_04 ': ssao, 'renopt_FSR_04 ': fsr, 'renopt_MSAA ': msaa,
              'renopt_draw_3d_04 ': draw_3d, 'renopt_draw_distance04 ': draw_distance,
              'renopt_shadow_quality_04 ': shadow_quality,
              'renopt_vegetation_quality_04 ': vegetation_quality}
    original, updated = _updated_preferences(path, values)
    old_window, new_window = window.read_bytes(), Path(preset_path).read_bytes()
    _publish_preferences(path, original, updated)
    try:
        _publish_preferences(window, old_window, new_window)
    except Exception:
        # Preserve a concurrent editor's changes instead of overwriting them.
        if path.read_bytes() == updated:
            atomic_write_bytes(path, original)
        raise
    return True


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
