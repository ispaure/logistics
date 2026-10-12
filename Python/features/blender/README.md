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
- `library.py` owns the versioned private ZIP library and preset selection JSON.
  Legacy module names and extension IDs are distinct identities. Literal AST/TOML
  metadata supplies release versions, inclusive minima, exclusive extension maxima
  and platform limits. Resolution selects the highest numeric compatible version.
  Import validates paths, duplicate names, symlinks and bounded metadata/archive size;
  it stages a private copy and rejects conflicting same-version contents.
- Applying selections copies resolved payloads into preset-owned addon locations,
  preserving unrelated addons and rejecting collisions. Config/scripts/extensions
  are backed up before mutation; `apply_addons.py` enables/disables only managed
  modules in bounded background Blender and saves preferences. Failure/cancellation
  restores files; successful selection state publishes atomically afterward.
  Launching a preset with managed selections reapplies resolution before launch.
  External side effects of addon startup code are beyond filesystem rollback.
- `page.py` shows LaunchCard configurations and adjacent Manage buttons, a separate
  library view, and management tabs for selection/inventory. Maintenance actions
  live in More; local ZIP import lives on the main page. It uses commonUtils `OperationProgress` for installs, copies, deletions and
  inventory queries. `prepare_close()` requests cancellation and defers destruction;
  `idle` fires only after the worker retires. Preset selection uses filesystem metadata;
  the explicit Refresh action queries Blender. The core rail owns its Blender glyph.

The library manages selected addon files and enabled preferences; unrelated
addons can still be managed directly in Blender. Private addon credentials and
download manifests remain deferred; no URLs or credentials are distributed. Absolute paths inside copied user preferences are preserved. The release
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

`test_blender_library.py` covers metadata-only import, grouped numeric resolution,
exclusive maxima/platforms, unsafe/ambiguous ZIP rejection, import conflicts,
independent presets, ownership guards, update/removal and rollback after failed
Blender enabling. Page tests also cover separate cards, Manage and library views.

On October 12, 2026, a temporary official Apple Silicon Blender 5.2.2 install
also passed real library import/apply for a legacy addon and a modern extension;
both were reported enabled by saved-state inventory, and deselection/removal
completed successfully. The temporary installation, library and presets were
removed. Windows/Linux and Intel macOS addon application remain unverified natively.

## Layered libraries and ordered activation

`AddonLibrary` merges the recursively discovered read-only provided ZIP folder
(default `Addons/blender`, `[Resources] blender_addons_path` override) with the
existing per-user library. Package metadata is the index: neither source needs
an artist-authored manifest. Personal releases replace provided entries only for
matching identity/version; newest compatible resolution runs over the merged set.
Conflicting duplicate versions inside one source fail explicitly. `add()` writes
only the personal root. Public packaging does not include the ignored addon folder.

Managed inventory stores display names/source. Apply requests sort by casefolded
name and module; selected modules are temporarily disabled with `default_set=False`
before enabling, preserving their preferences. Interactive launch uses sorted
`--addons` plus `launch_addons.py`, with the module list in a child-only environment
variable. Blender's CLI is additive and skips already-enabled modules, so the script
rebuilds managed activation order with `default_set=False` and never saves preferences.
Normal Blender initialization can run saved/default modules before this step; this
contract covers the managed reactivation sequence, not every startup callback.

Library tests cover source merging, personal tie precedence, read-only discovery,
missing provided roots, display-name ordering across addon types, CLI arguments,
and non-destructive startup disabling. The earlier private-download contract remains
deferred; folder-backed provided libraries do not require Blender credentials.

First launch provisions a missing release after a short version/destination
confirmation, then applies selected addons and launches the captured preset in the
same worker. Failure or cancellation prevents launch. Cards and Launch Blender
remain usable for uninstalled versions; there is no separate Install button.
Page tests cover approval/decline, install-before-launch, failure/cancellation,
and launching an existing installation without provisioning or a prompt.

## Settings ownership and dedicated Blue Hole integration

`BlenderSettings` places Presets first and nests the existing release editors under Versions Definitions, preserving
scope/override contracts. Personal scope adds Presets, a management-mode BlenderPage.
The navigation page retains launch cards and Settings shortcuts. Both surfaces share
`get_manager()` for launched-process ownership. Card shortcuts pass their version
and name to the retained settings panel. Selection saves persist intent without
provisioning; launch preparation applies it through the existing worker/rollback path.

`bluehole.py` is deliberately specific to ispaure/BlueHole: allowlisted main/beta/alpha
branches resolve through GitHub's branch API, and commit-pinned codeload ZIPs are
normalized to the stable BlueHole module. The private cache is
`addons/bluehole/<branch>/<commit>/addon.zip`; regular numeric library resolution
never substitutes for the selected branch. Every launch rechecks the branch head,
while unchanged commits reuse their cache. Browsing and settings saves do no network I/O.

Preset state records Blue Hole enable/branch/Deluxe choices, resolved commit and a
Deluxe payload digest. Blue Hole is outside the exhaustive addon list. When requested,
Deluxe stamps preset-only preferences/keymaps inside the same rollback transaction
as addon publication, retaining a pre-Deluxe preference copy. Equal payload digests
skip repeated stamping. Disabling Deluxe does not automatically revert existing
preferences. Tests cover commit reuse/changes, archive safety, default choices,
settings tabs, payload stamping/backups, symlink boundaries and customization retention.

The personal Presets tab uses a horizontal splitter with a version-qualified preset list on the left
and details on the right. Item data retains `(version, name)`,
so equal names across versions do not alias. The + action chooses a release/name;
context actions select their target before invoking the existing guarded lifecycle
operations. Hidden version/name selectors remain the launch/manager routing source.
List rebuilding retains the current preset and selects newly created/copied entries.
