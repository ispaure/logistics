# Blender installations and presets

Enable **Blender** in **Settings → Features**, then open it on the desktop
navigation rail. Each card launches a Blender version with its own preference
preset. **Manage** opens that preset in Settings. See
[mobile availability](../user_mobile/user_mobile.md).

## Install a version

Click a launch card. For a missing installation, confirm the package and
destination. Logistics verifies the pinned SHA-256 before extracting, then
launches the preset. Failed or cancelled installs clear temporary staging.

The bundled catalog offers **4.5.1**, **5.2.2** and **5.3.0** on Windows
x64/ARM64, Apple Silicon and Linux x64. Intel Macs have **4.5.1**. Blender’s own hardware and OS requirements
apply. In **Settings → Blender → Versions Definitions**, choose a version and
platform to edit its URL, SHA-256, format, bundle and executable. All five must
describe the same package. To clear a personal override, use **↶** and
then **Save Settings**. New software definitions use `config-<major.minor.patch>.ini`
under `Python/features/blender`.

## Create and launch presets

In **Settings → Blender → Presets**, click **+**, select a version and name it.
Launch from its card or **Launch Blender**. Presets have independent `config`,
`scripts`, `extensions` and `datafiles` directories. Use
**More… → Open Preset Folder** to access `config/userpref.blend`, legacy
`scripts/addons` or other preset files.

Close Blender before duplicating, copying to another version, renaming or
deleting a preset. Copies include its private addon ZIPs, preserve symlinks and
keep absolute paths stored inside preferences. Deleting permanently removes
that preset and its private files. Use Logistics to launch with its resources.

## Shared and preset-provided addons

- **Shared** ZIPs are discovered recursively under
  `Software/Blender_Addons_Library` by default.
- **Preset provided** ZIPs come from **Presets → Add Addon…** and are private
  to the selected preset. Available legacy imports already selected by a preset
  appear as **User provided (legacy)**.

Select addons, then **Save Addon Selection**. On launch, Logistics applies the
newest declared-compatible release, preferring the preset’s ZIP at equal
identity/version. Legacy `bl_info` and modern `blender_manifest.toml` metadata
must identify one addon and its compatibility. Minimum versions are inclusive,
extension maxima exclusive. Unsafe, ambiguous or conflicting ZIPs are rejected.
Matched legacy/extension packages share a selection, but Blender preference
migration depends on the addon.

Close Blender before applying changes. Deselecting removes managed addon files
on the next launch and keeps the ZIP. Move conflicting unmanaged module files
manually. Versions that change replace package files, so back up important data
stored inside them. Managed addons activate alphabetically in interactive
Blender and can run their own startup code.

Failed or cancelled preparation restores preset files and preferences. Use
`blender-addons-error-*.log` for preparation failures or
`blender-launch-*.log` for activation failures. Deselect or update a failed addon
before relaunching. If no compatible ZIP remains, deselect it in Manage.

## Blue Hole

Under **Presets**, **Enable Blue Hole** defaults to on. With **Source → GitHub**,
select **main**, **beta** or **alpha** and save. Launch resolves the newest
compatible Blender baseline (for example `blender-4.5.1/main`), checks its head
and downloads that exact commit if needed. An incompatible update stops launch.
On network failure, an already installed compatible copy can launch with a
warning showing its actual commit. Deluxe changes wait for a successful online
update. First installs need internet access.

For unpublished work, use **Source → Local → Browse…** and select the Blue Hole
checkout or worktree. macOS/Linux use symlinks and Windows uses a junction.
Close Blender before switching branches. **Apply Changes** can write
`keymaps/deluxe-defaults.json` in the linked checkout. Switching to GitHub
replaces the link on launch. A GitHub update replaces the installed keymap catalog.

On Blender **5.2.2 and newer**, use **Blue Hole → Updates & Deluxe → Enable
Deluxe Keymaps** and save preferences. Back up and review existing Deluxe
keymaps before switching to the built-in **Blender** preset.
On older versions, **Deluxe: Yes** replaces preset preferences and installs
`BH_Keymaps.py` when the payload changes. The prior preferences are retained as
`config/userpref.before-bluehole-deluxe.blend`. Turning Deluxe off stops applying
that payload.

Disabling Blue Hole preserves custom environments under `addon-data/bluehole`.
Re-enabling restores them. Updates refresh `envFiles/default`.

## Inspect installed addons

**Installed files** reads addon files without running them. **More… → Refresh
Addons** reads saved enabled state through background Blender and can run addon
startup code. Save preferences before refreshing. Use **Open Addon Folder** to
inspect the selected row. Failed inspection leaves enabled state unknown.

## Storage and removal

Files live under `%APPDATA%/Logistics` on Windows,
`~/Library/Application Support/Logistics` on macOS or `$XDG_CONFIG_HOME/logistics`
on Linux (normally `~/.config/logistics`). Installations use
`software/blender/<exact-version>` and presets use
`preferences/blender/<exact-version>/<preset>`.

Close Blender, then choose **More… → Remove Installation** to remove a complete
managed installation while keeping its presets. A stale `.version.lock` folder
can be removed after checking that no installation or removal is running.

## Available packages and installed addons

In **Addon Library**, expand shared entries to inspect ZIP dates and compatibility.
Set `Resources.blender_addons_path` to use a different shared folder. In a preset’s
**Addons** list, compare **Installed** with **Latest compatible** and check the
**Library** column for its source. Refresh after replacing ZIPs. **Currently
installed** shows Blue Hole’s resolved branch and commit or Local checkout.
