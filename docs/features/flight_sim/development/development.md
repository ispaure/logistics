# Flight Simulator Feature

See the [desktop workflow](../user/user.md) and
[mobile availability](../user_mobile/user_mobile.md).

## Contributions and paths

`Python/features/flight_sim/__init__.py` delegates registration to
`ui_contributions.py`, which declares feature ID `flight_sim`, label **X-Plane
Presets**, one **Installation** settings contribution and three destructive Debug
actions. The desktop action host asks for confirmation before calling the action.
There is no dedicated feature page.

`detection.py` reads layered settings from `config.ini`. A nonempty
`[XPlane] installation_path` becomes an expanded-user `Path`; otherwise the path is
`Steam/steamapps/common/X-Plane 12` beneath the user's Application Support directory.
The helper appends `Output/Preferences/X-Plane.prf` or
`Output/Preferences/X-Plane Window Positions.prf`. It does not discover installations,
create missing preference files or validate simulator versions.

Preset paths come from `LogisticsConfig.path_logistics_software_general` plus
`x-plane/` and the filenames in the [desktop guide](../user/user.md#prepare).
They are private inputs, not bundled preset downloads.

## Preference publication

`actions.py` owns all mutations. `_updated_preferences()` reads UTF-8 preferences,
retains a leading BOM and each changed line's existing ending, and requires exactly
one line starting with each requested key (including its trailing space). Values
must be nonnegative integers; the code does not validate X-Plane's semantic range.
Unrelated lines remain in order.

`_publish_preferences()` checks that the target still contains the captured bytes,
creates a UUID-suffixed `.previous-…` copy with overwrite disabled, then publishes
through the shared atomic-write API with a further unchanged-content check.
Shared persistence API details belong in commonUtils' own documentation.

`set_all_xp12_settings()` validates graphics keys and reads existing window
preferences and the selected preset before the first publication. It publishes graphics first,
then window positions. If window publication raises, graphics are restored only
if they still equal the just-published update. This preserves detected concurrent
edits, but is not a multi-file transaction or a simulator lock. Recovery copies
remain after success or rollback; no pruning or restore UI is provided here.

## Fixed graphics presets

The callbacks use the following values; they do not benchmark hardware or tune
settings automatically.

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

The shipped workflow targets desktop X-Plane 12 and historical macOS M3 Max setups.
An explicit installation path is configurable, but there is no general simulator
support or demonstrated cross-platform acceptance implied by that setting.
The feature has no mobile adapter or `mobile_sources.json` and is absent from
`mobile_build/tools.py`'s mobile source-owner list.

`Python/tests/integrations/test_flight_sim.py` uses temporary preference fixtures
and mocked paths to cover missing-key refusal without mutation, BOM/CRLF retention,
original-byte recovery copies, detected external edits and graphics rollback when
window publication fails. These tests do not run X-Plane or verify the private
presets against physical displays. The documentation audit inspected source/tests
and ran static checks only; it did not run those regressions or launch a simulator.
