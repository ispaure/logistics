# Blender feature

## Try a first-launch confirmation change

On desktop, open **Blender → Configure Blender… → Presets**. Make a disposable preset for an uninstalled release. Open its launch card and decline. In `Python/features/blender/ui/page.py:BlenderPage._launch`, revise the prompt while keeping the version, destination and decline path. Update `test_first_launch_prompts_installs_and_launches_configuration` and run from the repo root.

```sh
python3 dev.py test desktop --exact-file Python/tests/blender/test_blender_page.py
```

Expect approval to install before launch, decline/failure/cancellation to stop launch, and an installed release to skip confirmation.

## Owners and contracts

| Change | Owner under `Python/features/blender/` |
| --- | --- |
| Release config and migration | `settings.py`, `installation/releases.py` |
| Install and isolated launch | `installation/install.py`, `presets/manager.py` |
| Library and preset apply | `addons/library.py`, `addons/scanning.py`, `addons/metadata.py` |
| Special package | [Blue Hole consumer maintenance](blue-hole-maintenance.md) |

Exact `config-<major.minor.patch>.ini` files pin platform checksums. Legacy explicit-file callers still work. Migration preserves the old INI and new overrides, retries on failure, and stays complete after global personal reset.

Install verifies, safely extracts into a sibling workspace, and publishes without overwrite under a version lock. Verify ownership before removing an interrupted lock. Readiness checks marker and executable. DMG copying preserves signed bundle metadata. The preset selects config, scripts, extensions and datafiles through the child environment. Managed launches survive Logistics closure.

Resolve compatible add-ons by version, then legacy format, then dated revision. Preset packages override provided packages of the same identity/version. Retain undated imports, selected legacy imports and confirmed migration aliases. Quarantine conflicting revisions.

Saving writes pending intent. Apply verifies ZIP snapshots, refuses unmanaged collisions, repairs missing entrypoints and backs up managed resources before preparation. Failure or cancellation restores files. Add-on side effects can survive. Background preparation suppresses imports of GPU-dependent add-ons. Interactive launch activates them while preserving saved preferences. Check preset `blender-addons-error-*.log` or `blender-launch-*.log`.

For targeted regressions, use `test_blender_manager.py` for installation, `test_blender_library.py` for apply, `test_blender_activation.py` for launch and [Blue Hole validation](blue-hole-maintenance.md#validation-limits) for branch and cache behavior.

See [user workflows](../user/user.md) and [mobile availability](../user_mobile/user_mobile.md). Native evidence covers Apple Silicon 4.5.1 and 5.2.2. Hair Tool on 4.5.1 required forced termination on quit. Windows, Linux and Intel Mac acceptance remains open.
