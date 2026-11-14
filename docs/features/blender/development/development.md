# Blender feature

Manage Blender installations and isolated presets on desktop. A preset selects
a Blender release, preferences and add-ons. Opening Logistics or browsing the
feature leaves installation for the first confirmed launch. See the
[user guide](../user/user.md) for workflows and [mobile availability](../user_mobile/user_mobile.md)
for the platform boundary.

## Try a first-launch confirmation change

On desktop, enable **Blender** in **Settings → Features** and select it in the
rail. Use **Configure Blender… → Presets** to make a disposable preset for a
release that is available for your platform and has yet to be installed.
Click its launch card and decline the download. The prompt should identify
the version and destination. If every compatible release is already installed,
use the synthetic fixture below to exercise the missing-installation path.

Try changing the question to **Download and install Blender {version} before launching?** in
`Python/features/blender/ui/page.py` (`BlenderPage._launch`, reached through
`_launch_card`). Preserve the destination and the decline path. Update the
expected prompt in `test_first_launch_prompts_installs_and_launches_configuration`.
Run from the repository root after [desktop setup](../../../development/setup/getting-started.md):

```sh
python3 dev.py test desktop --exact-file Python/tests/blender/test_blender_page.py
```

Expect 21 passing tests. The launch fixtures mock installation and Blender.
Acceptance installs before launching the captured preset. Decline, failure and
cancellation prevent launch. An already installed release skips the prompt.
On relaunch, the missing-release card should show the revised prompt.

## Owners and contracts

Paths below are relative to `Python/features/blender/`.

| Change | Start here |
| --- | --- |
| Feature and Settings registration | `__init__.py:register` contributes the desktop page and separate application/personal panels. |
| Launch cards, Manage, and worker lifetime | `ui/page.py:BlenderPage` owns actions and delegates composition to `ui/layout.py`. `ui/addon_panels.py` owns the preset's Addons, Installed files and Blue Hole controls. |
| Release metadata, settings or extraction | `installation/releases.py`, `settings.py` and `installation/install.py`. |
| Preset isolation and Blender process environment | `presets/manager.py:BlenderManager`. The launch page and Settings share the manager for process ownership. |
| Package metadata, library and apply | `addons/scanning.py`, `addons/metadata.py` and `addons/library.py`. `addons/ui/page.py` owns the grouped read-only library catalog. |
| Blue Hole sources, compatibility and recovery | [Blue Hole consumer maintenance](blue-hole-maintenance.md). |

`BlenderPage` retains its operation through `prepare_close()`, requests
cancellation and emits `idle` after retirement. `BlenderManager` keeps installs
and presets version-separated under the per-user root. The child environment
selects the preset's config, scripts, extensions and datafiles. A launched
Blender continues independently after Logistics closes. Local mutation guards
track only instances started by the manager. Preset copy and rename use
guarded publication and preserve absolute paths in copied preferences.

## Release settings presentation and migration

`config-<major.minor.patch>.ini` identifies the exact release. Platform
sections identify build architecture, archive, extracted bundle and executable.
Legacy explicit-file callers remain supported. The pinned SHA-256 is the
official release archive checksum for that specific package. An absent build
leaves that version unavailable for the host platform.

`BlenderSettings` retains a shared `LayeredSettingsEditor` per version and
scope. The version selector chooses the file, and each platform tab carries
its section key. Validation constructs every `Release` for the selected
version before saving. Pending changes survive switching versions, platforms
and scopes. The `blender-release-files-v1` migration copies matching fields
from legacy personal `blender/config.ini`, keeps that file, and preserves
existing new-format overrides. A failed migration can retry. Global personal
reset marks it complete so older values stay reset.

## Installation and recovery

`installation/install.py` uses commonUtils `provision()` to verify the full
archive. ZIP extraction rejects traversal, Windows path syntax and symlinks.
TAR uses Python 3.12's data filter to preserve safe internal links. The DMG
adapter follows the commonUtils DMG helper's mount/copy lifecycle, using
plist mount discovery, read-only mounting and `ditto` to retain signed app
metadata and symlinks. Native mount operations have finite timeouts and
cleanup runs before the worker retires.

A directory lock serializes version install and removal. Extraction stages in
a same-parent workspace, then publishes the complete bundle atomically without
replacing a destination created after preflight. Readiness checks the version,
platform, archive hash and executable path in the marker, plus the executable
on disk. It does not rehash the installed tree. A cancelled install leaves the
launch pending for a later attempt. Read the operation error before retrying
a failed verification or destination collision. If an interrupted process
leaves a lock folder, remove the reported lock only after confirming that no
Logistics operation owns it.

## Package revisions and installed status

`AddonLibrary` combines the read-only provided ZIP folder
(`Software/Blender_Addons_Library` by default, configurable via
`[Resources] blender_addons_path`) and the preset's `addon-library`.
Preset packages take precedence for the same identity and numeric version.
Legacy personal imports remain available for already selected or requested
identities. `_support` is reserved for non-addon backup ZIPs.

Inspection reads literal AST or TOML metadata without importing add-ons.
It applies the declared platform, inclusive minimum and exclusive extension
maximum. Resolution picks the highest compatible numeric version, then
prefers legacy format at a tied version, then the newest `_YYYY_MM_DD`
revision. Undated imports remain readable. Confirmed legacy-to-extension
pairings retain selections across package replacement. Zen UV has a
publisher-confirmed rename rule. Conflicting bytes for one identity,
version and revision are quarantined. Healthy entries remain visible.
A selected identity without a valid compatible package fails before mutation.

Inspection caches file fingerprints and refresh uses one catalog snapshot.
The preset UI distinguishes actual installed versions from latest compatible
versions and pending selections. Installed metadata provides a fallback for
the filesystem inventory. An explicit inventory refresh runs `probe.py` in
background Blender with offline and blend-file autoexecution restrictions.
Normal enabled add-ons may still run on startup. A timed-out or cancelled
probe is reaped and leaves filesystem rows with unknown activation state.

## Apply preparation and publication

Saving in **Presets** calls `AddonLibrary.save_pending_selection` under the
preset installation lock. It publishes intent in `.logistics-addons.json`
and preserves installed records. Only a successful refresh of the active
preset enables saving. Imports are private to that preset and copy/delete
with it.

On launch, `AddonLibrary._apply` resolves packages, rejects unmanaged
destination collisions and takes verified SHA-256 snapshots of changed ZIPs
before modifying resources. An entrypoint with the same path and digest
stays in place. Missing entrypoints trigger repair. Extraction and any
legacy Deluxe stamping use verified snapshots. Apply backs up config,
scripts, extensions and managed add-on data. A preparation error or
cancellation restores them. Final selection publication is atomic.
External side effects from add-on code fall outside filesystem rollback.

## GPU-dependent addon activation and diagnostics

`apply_addons.py` prepares saved selection entries in background Blender.
The background runner uses `--factory-startup`. The script reloads preset
preferences while temporarily suppressing `addon_utils.enable` to preserve
saved preference objects without importing GPU-dependent modules such as
Hair Tool. It restores the activation function when preparation ends.

`BlenderManager.launch` supplies sorted `--addons` and a child-only module
list. After normal startup and CLI processing, `launch_addons.py` reactivates
managed modules in display-name order with `default_set=False`. The script
keeps saved preference objects and performs no disk save. Interactive
activation failures leave the prepared selection on disk.

Look for `blender-addons-error-*.log` on failed preparation and
`blender-launch-*.log` on interactive launch. These logs live in the preset
outside resource rollback directories. The bounded preparation excerpt
starts at the traceback and includes the exit code and full log location,
or a storage error if log publication fails.

## Validation

| Change | Focused fixture under `Python/tests/blender/` |
| --- | --- |
| Version catalog, installation publication, child environment and cancellation | `test_blender_manager.py` |
| Release settings, pending edits and retryable migration | `test_blender_settings.py` |
| Compatibility, library isolation, verified apply, rollback and offline fallback | `test_blender_library.py` |
| Saved preference entries, interactive error chaining and log failures | `test_blender_activation.py` |
| Blue Hole version families, cache and unsafe archives | [Blue Hole validation](blue-hole-maintenance.md#validation-limits) |

Qt fixtures use a private manager and empty provided library, with workers
retired before fixture directories are removed. Fixture archives and mocked
launches exercise the Logistics contracts. Native extraction, GPU-dependent
registration and actual add-on behavior require checks on the target release,
platform and architecture. Previous native evidence covers Apple Silicon
installation and preset startup on 4.5.1 and 5.2.2, plus representative legacy
and extension inventory. The Hair Tool interactive verification on 4.5.1
required forced termination during quit. Native Windows, Linux and Intel Mac
acceptance remains outstanding.
