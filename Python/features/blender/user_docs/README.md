# Blender installations and presets

Open **Blender** from the navigation rail. If it is hidden, enable Blender under
**Settings → Features**. Logistics ships only the manager and its release catalog;
Blender is downloaded when you choose **Install**.

## Install a version

Select a version and click **Install**. Confirm the download and destination.
Logistics verifies the official package against its pinned SHA-256 before
extracting it. Progress and cancellation are shown below the addon list. Successful
installation deletes the downloaded package; failure or cancellation discards
temporary staging. Existing installation folders are never silently overwritten.

The catalog includes Blender **4.5.1** and **5.2.2**, the stable release verified
on October 12, 2026. Windows x64/ARM64 and macOS Apple Silicon have both versions;
Intel Macs have 4.5.1. Linux x64 has both versions. These releases have no official
Linux ARM64 package, and 5.2.2 has no Intel Mac package. The manager shows only
packages for your OS/architecture. Blender's own OS and hardware requirements
still apply; a matching package does not guarantee compatibility with older systems.

Release metadata is editable under **Settings → Blender → Release downloads**.
An exact version, platform, HTTPS URL, SHA-256, package format, extracted bundle
and relative executable path must describe the same official package. New versions
are added explicitly; the manager does not silently replace an installed release.

## Create and launch presets

Click **Create Preset**, choose a name, then **Launch Blender**. Each preset has
independent `config`, `scripts`, `extensions` and `datafiles` folders. Blender's
`userpref.blend` and `startup.blend` belong in `config`; legacy addons belong in
`scripts/addons`, and scripts/keymap presets belong under `scripts/presets`.
Modern extensions retain Blender's repository/extension folder layout.

Blender receives the selected resource paths in its process environment. Normal
Blender preferences outside Logistics are not selected by this launcher. Launching
Blender directly outside Logistics does not automatically use these presets.

- **Duplicate Preset** makes an independent copy within the selected version.
- **Copy to Another Version** copies to another configured release after an explicit
  confirmation. Check addon and preference compatibility in the destination Blender.
- **Rename Preset** changes its folder name without rewriting preferences inside it.
- **Open Preset Folder** opens its files in your system file manager.
- **Delete Preset** permanently deletes that preset, preferences and addons after
  confirmation. There is no Undo; back up important presets before deletion.

Copying preserves file contents and symlinks. Blender preferences may contain
absolute paths to assets, repositories or scripts: duplicating/renaming a preset
does not rewrite those references. Close Blender before copying, renaming or
deleting its preset. Logistics blocks these operations for instances it launched
while they are running; it cannot track Blender instances started elsewhere.

## Installed addons

Selecting a preset immediately lists legacy addon files and extension manifests
found in that preset, without importing the addon code. **Enabled** initially reads
**Unknown** because filesystem metadata cannot tell us the saved preference state.

Click **Refresh Addons** to start the selected Blender in background/offline mode
and inspect its saved preferences. The list shows name, version (where declared),
legacy addon/extension type, saved enabled state, source and location. Sources are
**Preset**, **Bundled** (inside that installation) and **External** (paths referenced
outside these folders). Bundled and external addons appear after Blender inspection.
Preset files Blender cannot discover remain in the list with unknown enabled state.
Choose a row and **Open Addon Folder** to inspect its files.

Save preference changes in Blender before refreshing: this reads disk state, not
unsaved state in an already-running window. Background inspection performs normal
Blender addon initialization; installed enabled addons may run their startup code.
Logistics' probe does not save preferences, toggle addons or install extensions.
If Blender fails or the query times out, the list falls back to preset files and
explains why enabled state is unknown. Addon install/remove and enable/disable
remain in Blender's own Preferences in this first version.

## Storage and removal

Everything is under the per-user Logistics directory:

| OS | Logistics root |
| --- | --- |
| Windows | `%APPDATA%/Logistics` (home-directory fallback if APPDATA is unavailable) |
| macOS | `~/Library/Application Support/Logistics` |
| Linux | `$XDG_CONFIG_HOME/logistics` or `~/.config/logistics` |

Installations use `software/blender/<exact-version>`. Presets use
`preferences/blender/<exact-version>/<preset>`. These paths are independent of
the older global software/resource directory settings. **Open Installation Folder**
opens the selected installed application.

**Remove Installation** deletes only a complete Logistics-managed installation
after confirmation; presets and their addons remain available for reinstallation.
Close Blender instances using it first. An incomplete/unrecognized folder is kept
for manual inspection rather than deleted automatically. If a previous process
crashed and left a `.version.lock` folder beside an installation, first ensure no
Logistics installation/removal is running, then remove that empty lock folder and retry.

macOS installations mount the downloaded DMG read-only, copy `Blender.app` while
preserving its metadata, then detach the mounted volume. Cancellation during a
native mount/copy waits for that bounded operation to finish before cleanup.
Removal/deletion finish their filesystem operation once begun; partial removal
after a filesystem error may require manual cleanup. Downloads need internet
access and enough disk space for the package, staging and extracted application.
