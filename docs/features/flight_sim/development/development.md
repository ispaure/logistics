# Flight Simulator Feature

X-Plane Presets applies desktop X-Plane 12 graphics and window settings for
three historical macOS M3 Max setups.

## Try a preference error change

1. In desktop **Settings → Features**, enable **X-Plane Presets**. From the
   Settings menu choose **Open full hub with sidebar**, then open **Debug**.
   Find **X-Plane 12: M3 Max Standalone** under **X-Plane Presets**. You can open
   and cancel its confirmation to trace the entry without touching simulator
   files.
2. In `Python/features/flight_sim/ui_contributions.py`, that action calls
   `actions.set_xp12_m3_max_standalone()`. Follow it through
   `set_all_xp12_settings()` to `_updated_preferences()` in
   `Python/features/flight_sim/actions.py`. Try appending
   `in {path.name}; check the installation path in Settings.` to the
   missing-or-duplicated key error so the operator can identify the file.
3. In `Python/tests/integrations/test_flight_sim.py`, extend
   `test_missing_key_does_not_change_file` to expect the synthetic file name
   `prefs` in the error. Keep the assertions that the bytes match the original
   and that no recovery copy was created.

Run from the repository root with the desktop environment set up:

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_flight_sim.py
```

Expect five passing tests. The fixture patches the path lookup and exercises
the same preference parser, including the new error, without opening X-Plane
or using a private window preset.

## Contributions and paths

`Python/features/flight_sim/__init__.py` delegates registration to
`ui_contributions.py`. The feature contributes **Installation** settings and
three actions to the shared [Debug page](../../../development/extension-points.md#debug).
The desktop action host confirms destructive actions before calling them.

`detection.py` reads `[XPlane] installation_path` from layered `config.ini`
settings and expands `~` in an explicit path. If blank it uses
`Steam/steamapps/common/X-Plane 12` under the user's Application Support
directory. It appends `Output/Preferences/X-Plane.prf` or
`Output/Preferences/X-Plane Window Positions.prf`. The action needs both files
to exist. The fallback is a fixed path and the helper does not check simulator
versions.

Each callback finds its private window preset under
`LogisticsConfig.path_logistics_software_general / 'x-plane'`. See
[Prepare](../user/user.md#prepare) for the three filenames.

## Preference publication

`_updated_preferences()` requires exactly one line beginning with each
requested key and its trailing space. It accepts nonnegative integers, without
checking the simulator's allowed range for each key. It preserves the UTF-8
byte-order mark, line endings and unrelated lines.

`_publish_preferences()` compares the current bytes to those read earlier,
writes a UUID-suffixed `.previous-…` recovery copy without overwrite, then
calls commonUtils' atomic writer with another content check before replacement.

`set_all_xp12_settings()` validates graphics keys and reads both the existing
window preferences and the preset before publishing anything. It publishes
graphics first and window positions second. If window publication fails, it
restores the graphics original only if the graphics file still matches its
own update at replacement time. A rollback failure reports both failures and
the retained graphics recovery path. The two files publish separately, with
no simulator lock. Close X-Plane before applying a preset. Keep the recovery
copies until both files are checked and follow [Apply and recover](../user/user.md#apply-and-recover)
if manual restoration is needed.

## Fixed graphics presets

| Setting key | Standalone | Flight Desk, internal on | Office |
| --- | --- | --- | --- |
| `renopt_SSAO_04` | 2 | 0 | 2 |
| `renopt_FSR_04` | 0 | 3 | 2 |
| `renopt_MSAA` | 1 | 0 | 1 |
| `renopt_draw_3d_04` | 3 | 2 | 3 |
| `renopt_draw_distance04` | 4 | 3 | 3 |
| `renopt_shadow_quality_04` | 2 | 0 | 2 |
| `renopt_vegetation_quality_04` | 3 | 2 | 3 |

## Platform and validation scope

The focused suite checks missing-key refusal, UTF-8 BOM and CRLF retention,
original-byte recovery copies, external-edit refusal, and rollback after a
window write failure including an external edit during rollback. An explicit
install path allows alternate locations. Compatibility with other machines and
display layouts requires verification in X-Plane.

The feature has no mobile source owner in `mobile_build/tools.py`. See
[mobile availability](../user_mobile/user_mobile.md).
