# Blender feature

The lazy `register()` declaration contributes a standalone Blender page and its
release configuration. Opening/discovering the feature never downloads or launches
Blender. No Blender binaries, packages or addon bundles are distribution assets.
See the [user guide](user_docs/README.md) for controls and recovery.

## Owners and contracts

- `releases.py` discovers layered `config-<major.minor.patch>.ini` files and selects
  exact version/platform builds. The filename owns the version and platform sections
  own the build identity. Explicit legacy-file callers remain supported. `Release` validates paths and delegates HTTPS/digest
  validation to the shared `DownloadSpec`. SHA-256 values are pinned from Blender's
  official release checksum files, independently for each package.
- `install.py` uses commonUtils `provision()` to download and verify the entire
  archive (`installed_sha256` equals its package hash). Feature adapters extract
  ZIP/TAR bundles or mount/copy/detach DMGs. The existing commonUtils DMG helper
  informed the mount/copy lifecycle; this adapter uses plist mount discovery,
  read-only mounting and `ditto` to retain signed app metadata and symlinks.
  Shared APIs and the existing helper are unchanged.
- A same-parent temporary workspace holds the archive and extracted tree. Publication
  renames the verified complete bundle into an absent destination. A directory lock
  serializes installation/removal per version. The completion marker records version,
  platform, archive hash and executable path. Readiness checks that marker and the
  executable's existence; it does not rehash the full installation on every launch.
- ZIP extraction rejects traversal, Windows path syntax and symlinks. TAR uses
  Python 3.12's data filter to preserve safe internal links and reject escapes/devices.
  Cancellation checks surround download, extraction members and final publication.
  Native DMG operations have finite timeouts and cleanup runs before retirement.
- `manager.py` derives the per-user root from Logistics' existing preference path
  helper, without changing global resource defaults. Installations and presets are
  version-separated. Preset duplication stages independent copies; environment
  overrides explicitly select config, scripts, extensions and datafiles in the child.
  Launched instances are tracked for local mutation guards and continue independently
  after Logistics closes. Instances started elsewhere are not tracked.
- `addons.py` reads legacy AST metadata and modern TOML manifests without imports.
  Explicit refresh invokes `probe.py` in the selected Blender's embedded Python;
  a temporary JSON file carries the inventory, independent of addon console output.
  The subprocess runs offline with blend-file autoexecution disabled, but normal
  enabled-addon startup still occurs. It never saves preferences. Cancellation or
  timeout kills/reaps the child; failures retain filesystem rows with unknown state.
- `page.py` uses commonUtils `OperationProgress` for installs, copies, deletions and
  inventory queries. `prepare_close()` requests cancellation and defers destruction;
  `idle` fires only after the worker retires. Preset selection uses filesystem metadata;
  the explicit Refresh action queries Blender. The core rail owns its Blender glyph.

The first version lists addons but leaves installing/enabling/removing them to
Blender. Absolute paths inside copied user preferences are preserved. The release
catalog is extensible; missing official platform builds remain unsupported rather
than inventing archives or selecting a different architecture silently.

## Validation

`Python/tests/test_blender_manager.py` covers verified full-bundle installation,
hash failures, cancellation, traversal/link rejection, DMG cleanup, locking,
preset independence, child environments, deletion boundaries and addon fallbacks.
`Python/tests/test_blender_page.py` covers contribution discovery, absence of
startup provisioning, inventory display and worker-close cancellation.

Real OS-specific extraction and Blender startup should also be exercised on each
supported desktop platform. Fixture ZIP/TAR/DMG tests do not substitute for Windows,
Linux and Intel macOS runtime validation.

On October 12, 2026, temporary official Apple Silicon installations of 4.5.1 and
5.2.2 passed download verification, DMG installation, preset resource-path checks,
saved `userpref.blend` placement and legacy addon enabled-state inventory. A modern
extension fixture also passed saved enabled-state inventory in 5.2.2. The temporary
packages, installs and presets were deleted afterward. Windows/Linux/Intel Mac
native runtime checks remain outstanding.

## Release settings presentation and migration

`settings.py` retains a shared LayeredSettingsEditor per version and scope.
A version dropdown selects the file; a platform list selects the editor's hidden
section tab. Field controls, override/reset behavior, conflict detection and saves
remain shared. The validator constructs Release objects for the whole version
before publication, so invalid URL/hash/format/path metadata cannot be saved.
Editors remain alive across version/platform and scope changes; host close checks
all pending editors, and the global personal reset reloads them through the normal
LayeredSettingsEditor lifecycle.

Separate application/personal contributions expose the custom panel in both host
scopes without a second raw INI editor. `initialize_release_settings()` registers
all version files at application settings initialization. The retryable
`blender-release-files-v1` migration copies matching editable fields from legacy
personal `blender/config.ini` sections into per-version INIs, retains the source,
and preserves existing new-format overrides. Migration identity fields are now
represented by filenames/platform sections rather than editable scalar controls.
Global personal reset marks the migration complete to prevent old values returning.

`test_blender_settings.py` covers platform routing, pending buffers, sparse matching
overrides, release validation and retryable migration. All original pinned package
metadata remains unchanged by the file split.
