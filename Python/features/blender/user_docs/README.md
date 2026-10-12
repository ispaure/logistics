# Blender installations and presets

Open **Blender** from the navigation rail. If it is hidden, enable Blender under
**Settings → Features**. Logistics ships only the manager and its release catalog;
Blender is downloaded on the first launch of a configuration that needs it.

The main page shows one launch card per Blender version and preference preset.
Click a card to launch that configuration. If Blender is missing, confirm its
version and destination; Logistics installs it before launching.
**Configure Blender…** and each card's **Manage** button open the feature's Settings.

Under **Settings → Blender**, **Presets** appears first. The second tab,
**Versions Definitions**, is admin configuration for the catalog of Blender versions
available to install, including their platform packages and download metadata.
In **Personal Settings**, **Presets** creates and manages configurations, selects
addons and provides **Add Addon…** / **Addon Library**. Version/preset editing
is kept off the main launch page. Manage opens the selected card's preset.

## Install a version

Click a configuration card or **Launch Blender** in Manage. If that version is
missing, confirm the download and destination. Logistics installs it and then
launches the selected preset automatically. Cancelling or a failed installation
does not launch Blender. Installed versions launch without a download prompt.
Logistics verifies the official package against its pinned SHA-256 before
extracting it. Progress and cancellation are shown at the bottom of the page. Successful
installation deletes the downloaded package; failure or cancellation discards
temporary staging. Existing installation folders are never silently overwritten.

The catalog includes Blender **4.5.1** and **5.2.2**, the stable release verified
on October 12, 2026. Windows x64/ARM64 and macOS Apple Silicon have both versions;
Intel Macs have 4.5.1. Linux x64 has both versions. These releases have no official
Linux ARM64 package, and 5.2.2 has no Intel Mac package. The manager shows only
packages for your OS/architecture. Blender's own OS and hardware requirements
still apply; a matching package does not guarantee compatibility with older systems.

Release metadata is editable under **Settings → Blender**. Select the exact
**Blender version** from the dropdown, then choose a platform from the list on the
left. The right-hand panel shows only that platform's download URL, SHA-256,
package format, extracted bundle and executable path. **Save Settings** saves edits
for the selected version; switching versions/platforms keeps unsaved edits.

Each version has its own catalog file, such as `config-4.5.1.ini` or
`config-5.2.2.ini` in `Python/features/blender`. The filename fixes the version;
platform section names identify the builds. To add a version, add a matching
`config-<major.minor.patch>.ini` with its official package metadata. The manager
does not silently replace installed releases.

The global Settings scope selects **Personal Settings** or **Default Software
Configuration**. Personal edits save only explicit fields in the matching per-version
personal INI; inherited fields follow software defaults. A matching explicit value
remains an override until **↶** removes it and **Save Settings** commits the reset.
Download URL, hash, format, bundle and executable must describe the same package;
invalid metadata is rejected on Save. Existing personal fields from the old combined
catalog migrate once to the matching version/platform; the old file is retained.
Existing per-version choices take precedence. Migration failures preserve the old
file and retry on a later launch. Switching scopes retains each scope's pending edits.

## Create and launch presets

Open **Settings → Blender → Presets**. The list on the left shows all presets
with their Blender versions. Select one to configure its details on the right.
Click **+**, choose the Blender version and enter the preset name beneath it in
the same dialog, then launch from its card or **Launch Blender**.
Right-click a preset to rename, duplicate, copy it to another version, or delete it.
Deletion still asks for confirmation and keeps the shared addon library intact. Each preset has
independent `config`, `scripts`, `extensions` and `datafiles` folders. Blender's
`userpref.blend` and `startup.blend` belong in `config`; legacy addons belong in
`scripts/addons`, and scripts/keymap presets belong under `scripts/presets`.
Modern extensions retain Blender's repository/extension folder layout.

Blender receives the selected resource paths in its process environment. Normal
Blender preferences outside Logistics are not selected by this launcher. Launching
Blender directly outside Logistics does not automatically use these presets.

The **More…** menu in Manage contains these maintenance actions:

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

## Provided and personal addon libraries

The library combines two sources:

- **Provided:** a read-only collection of addon ZIPs supplied by the studio or
  maintainer. It defaults to `Addons/blender` in the checkout and also supports a
  configured shared folder. ZIPs are discovered recursively; no manifest is needed.
- **Personal:** addon ZIPs the artist imports with **Add Addon…**. The system reads
  metadata, groups releases and handles compatibility; artists do not edit documents.

The library and each preset's resolved release show which source supplies the addon.
The newest declared-compatible release across both sources wins. When the same addon
identity/version exists in both, the personal copy takes precedence for that artist;
other versions in the provided collection remain available. Importing an older
personal version does not hide a newer compatible provided version. The provided
collection is never written, copied into the personal library, or removed by imports.
No addon packages are shipped by this change; supplied ZIPs populate the collection.

**Add Addon…** selects a local `.zip` and copies it into the per-user library at
`addons/blender/<identity>/<addon-version>/addon.zip`. Each legacy module name
or extension manifest ID identifies one addon; releases sharing that identity are
kept together. An identical import is harmless; different contents claiming the
same identity/version are rejected. Different module names remain distinct, even
if their display names match. Keep package/module identities stable across releases.

Metadata is read without importing addon code. Legacy packages use the literal
`bl_info` dictionary in `__init__.py` (or a single root Python file); its `version`
is the addon release and `blender` is the minimum Blender version. Modern
extensions use `blender_manifest.toml`, including `version`, `blender_version_min`,
optional exclusive `blender_version_max`, and optional `platforms`.

The manager chooses the numerically newest addon release whose declared Blender
version range and platform match the configuration. A minimum is inclusive; an
extension maximum is exclusive. Missing requirements appear as unknown in the
library and are not automatically eligible for selection. Declared compatibility
cannot guarantee that an addon works. ZIPs must contain exactly one identifiable
addon; unsafe paths, symbolic links, duplicate paths and oversized packages are
rejected. Unknown versions or metadata constructed by executing Python are rejected.

Open **Settings → Blender → Presets** (or a card's **Manage** shortcut), select
addons under **Addons**, then click **Save Addon Selection**. This saves the choices
without installing or launching Blender. The next launch copies the resolved
releases into that preset, enables them in background Blender and saves preferences.
Close Blender before saving or applying changes. Deselecting an addon disables
and removes its library-managed files from that preset; the source ZIP stays in its provided or personal library.
Existing addons installed outside the library are preserved; conflicting module
paths must be moved manually before the library can manage that addon.

Selected addons are activated automatically in case-insensitive alphabetical order
by their displayed names, using their module names to break ties. The launcher passes
an ordered `--addons` argument and runs a startup script that disables/re-enables
only the managed addons in that order without removing their preference objects.
Blender's ordinary saved/default addons may initialize earlier; the controlled
activation step orders the managed selection and leaves unrelated addons alone.
This can call managed addon startup code again. The interactive startup step does not save preferences. Launch preparation applies
the saved selection and saves its enabled preferences in background Blender.

Launch cards resolve saved selections again, so a newly imported compatible release
is used on the next launch. If a selection no longer has a compatible release,
launch reports the problem; deselect it in Manage. Importing a ZIP alone does not
change existing presets. Copies to another Blender version retain selections and
resolve them for that destination on launch. The manager rolls back preset files
and saved preferences when applying addons fails or is cancelled. Addon startup
code can run during enabling and launch; effects outside the preset cannot be undone.
Blender instances started outside Logistics cannot be tracked; close them yourself.

Private download credentials are planned for `Credentials/blender_addons`, but
credential manifests, private downloads and access management are not implemented.
Use local ZIP imports for now.

## Blue Hole

Blue Hole is a dedicated optional configuration above the normal addon list in
**Presets**; it is omitted from the regular library list. **Enable Blue Hole** is
on by default. Choose **main**, **beta** or **alpha**, and **Deluxe: No / Yes**.
Deluxe defaults to No. Save the selection before launching.

Each launch with Blue Hole enabled checks the selected GitHub branch head. The
manager downloads that exact commit only when it is not already cached, using the
public `ispaure/BlueHole` repository. Branch snapshots have their own commit cache,
so two commits declaring the same addon version still remain distinct. Declared
Blender compatibility is checked before applying the snapshot. No GitHub access
or download happens merely by viewing the page or creating a preset. A failed
update stops launch and preserves the existing preset files/preferences.

Deluxe copies `overlays/deluxe/payload/userpref.blend` into the preset's config
and `payload/keyconfig/BH_Keymaps.py` into its scripts/presets/keyconfig folder,
before applying addon selections. It replaces that preset's preferences; an existing
file is retained as `config/userpref.before-bluehole-deluxe.blend`. The payload is
stamped once, then again only if its contents change, preserving artist changes
between launches. No stops further stamping; it does not undo preferences/keymaps
already applied. Disable Blue Hole to omit it entirely. Existing presets without
an explicit Blue Hole choice inherit enabled/main/No on their next launch.

## Inspect installed addons

Manage's **Installed files** tab lists legacy files and extension manifests without
importing them. Saved enabled state initially reads **Unknown**.
**More… → Refresh Addons** starts Blender in background/offline mode to inspect
saved preferences. It lists addon name, version, type, enabled state, source and
location. Sources are **Preset**, **Bundled** and **External**; the latter two
appear after Blender inspection. **More… → Open Addon Folder** opens the selected
row. Save changes in Blender before refreshing. Inspection does not save or change
preferences, but enabled addons may run their startup code. Failures fall back to
filesystem rows with unknown enabled state.

## Storage and removal

Everything is under the per-user Logistics directory:

| OS | Logistics root |
| --- | --- |
| Windows | `%APPDATA%/Logistics` (home-directory fallback if APPDATA is unavailable) |
| macOS | `~/Library/Application Support/Logistics` |
| Linux | `$XDG_CONFIG_HOME/logistics` or `~/.config/logistics` |

Installations use `software/blender/<exact-version>`. Presets use
`preferences/blender/<exact-version>/<preset>`. These paths are independent of
the older global software/resource directory settings. **More… → Open Installation Folder**
opens the selected installed application.

**More… → Remove Installation** deletes only a complete Logistics-managed installation
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
