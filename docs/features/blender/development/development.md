# Blender feature

Blender integration prepares a selected Blender release and preset for
launch. A preset can use an installed release or request installation first.
Once the release is ready, Logistics applies any selected add-ons and starts
Blender with the preset's configuration.

## Follow a first launch

In **Blender → Configure Blender… → Presets**, a preset for an uninstalled
release reaches `Python/features/blender/ui/page.py:BlenderPage._launch`.
The focused page fixtures check approval, decline, installation failure and
cancellation, plus the already-installed path. Use their mocked installation
work when changing this flow:

```sh
python3 dev.py test desktop --exact-file Python/tests/blender/test_blender_page.py
```

## Owners and contracts

| Change | Owner under `Python/features/blender/` |
| --- | --- |
| Release config and migration | `settings.py`, `installation/releases.py` |
| Install and isolated launch | `installation/install.py`, `presets/manager.py` |
| Library and preset apply | `addons/library.py`, `addons/scanning.py`, `addons/metadata.py` |
| Special package | [Blue Hole consumer maintenance](blue-hole-maintenance.md) |

Exact `config-<major.minor.patch>.ini` files pin platform checksums. Legacy explicit-file callers still work. Migration preserves the old INI and new overrides, retries on failure, and stays complete after global personal reset.

Install verifies, safely extracts into a sibling workspace, and publishes without overwrite under a version lock. Verify ownership before removing an interrupted lock. Readiness checks marker and executable. DMG copying preserves signed bundle metadata. The preset selects config, scripts, extensions and datafiles through the child environment. Managed launches survive Logistics closure.

Per-preset `.logistics-launch.json` stores the `console` launch option (default
false). `presets/console_launch.py` uses commonUtils' native terminal launcher.
Blender's bundled Python runs the stdlib-only bridge, transferring only explicit
Blender environment variables and recording the real Blender PID and exit status.
Console launches run through the page's worker, including presets with no addons.
Addon selection changes save immediately; rendering a new preset invalidates the
previous selection context before projecting controls, so refreshes do not save.
Manager, page and console regression tests cover persistence, failures and process tracking.

Resolve compatible add-ons by version, then legacy format, then dated revision. Preset packages override provided packages of the same identity/version. Retain undated imports, selected legacy imports and confirmed migration aliases. Quarantine conflicting revisions.

Saving writes pending intent. Under the preset lock, Apply resolves the sources, rejects unmanaged collisions and verifies ZIP snapshots before provisioning or changing preset resources. It keeps a backup of managed resources and moves a recorded local Blue Hole link without following it. Apply repairs missing managed entrypoints, runs Blender preparation and publishes the installed selection only after preparation succeeds and cancellation is checked. Failure or cancellation restores the managed resources and link; add-on side effects outside those resources can survive. Background preparation suppresses imports of GPU-dependent add-ons. Interactive launch activates them while preserving saved preferences. Check preset `blender-addons-error-*.log` or `blender-launch-*.log`.

For targeted regressions, use `test_blender_manager.py` for installation, `test_blender_library.py` for apply, `test_blender_activation.py` for launch and [Blue Hole validation](blue-hole-maintenance.md#validation-limits) for branch and cache behavior.

See [user workflows](../user/user.md) and [mobile availability](../user_mobile/user_mobile.md). Native evidence covers Apple Silicon 4.5.1 and 5.2.2. Hair Tool on 4.5.1 required forced termination on quit. Windows, Linux and Intel Mac acceptance remains open.
