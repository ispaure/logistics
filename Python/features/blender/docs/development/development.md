# Blender feature

The lazy `register()` declaration contributes a standalone Blender page and its
release configuration. Opening/discovering the feature never downloads or launches
Blender. No Blender binaries, packages or addon bundles are distribution assets.
See the [user guide](../user/user.md) for controls and recovery.

## Owners and contracts

- `installation/releases.py` discovers layered `config-<major.minor.patch>.ini` files and selects
  exact version/platform builds. The filename owns the version and platform sections
  own the build identity. Explicit legacy-file callers remain supported. `Release` validates paths and delegates HTTPS/digest
  validation to the shared `DownloadSpec`. SHA-256 values are pinned from Blender's
  official release checksum files, independently for each package.
- `installation/install.py` uses commonUtils `provision()` to download and verify the entire
  archive (`installed_sha256` equals its package hash). Feature adapters extract
  ZIP/TAR bundles or mount/copy/detach DMGs. The existing commonUtils DMG helper
  informed the mount/copy lifecycle; this adapter uses plist mount discovery,
  read-only mounting and `ditto` to retain signed app metadata and symlinks.
  Shared APIs and the existing helper are unchanged.
- A same-parent temporary workspace holds the archive and extracted tree. Publication
  uses shared atomic no-replace renaming for the verified complete bundle.
  A destination created after preflight is preserved. A directory lock
  serializes installation/removal per version. The completion marker records version,
  platform, archive hash and executable path. Readiness checks that marker and the
  executable's existence; it does not rehash the full installation on every launch.
- ZIP extraction rejects traversal, Windows path syntax and symlinks. TAR uses
  Python 3.12's data filter to preserve safe internal links and reject escapes/devices.
  Cancellation checks surround download, extraction members and final publication.
  Native DMG operations have finite timeouts and cleanup runs before retirement.
- `presets/manager.py` derives the per-user root from Logistics' existing preference path
  helper, without changing global resource defaults. Installations and presets are
  version-separated. Preset duplication stages independent copies; both duplication
  and renaming reject destinations created after preflight. Environment
  overrides explicitly select config, scripts, extensions and datafiles in the child.
  Launched instances are tracked for local mutation guards and continue independently
  after Logistics closes. Instances started elsewhere are not tracked.
- `addons/scanning.py` reads legacy AST metadata and modern TOML manifests without imports.
  Inventory, ZIP inspection and installed Blue Hole fallback share the metadata
  parser. It silences only invalid-escape SyntaxWarnings from third-party source
  during AST parsing; syntax errors retain the source filename and application
  warning filters are restored afterward. No addon source is modified or executed.
  Explicit refresh invokes `probe.py` in the selected Blender's embedded Python;
  a temporary JSON file carries the inventory, independent of addon console output.
  The subprocess runs offline with blend-file autoexecution disabled, but normal
  enabled-addon startup still occurs. It never saves preferences. Cancellation or
  timeout kills/reaps the child; failures retain filesystem rows with unknown state.
- `addons/library.py` owns the versioned private ZIP library and preset selection JSON.
  Legacy module names and extension IDs are distinct identities. Literal AST/TOML
  metadata supplies release versions, inclusive minima, exclusive extension maxima
  and platform limits. Resolution selects the highest numeric compatible version.
  Import validates paths, duplicate names, symlinks and bounded metadata/archive size;
  it stages a private copy and rejects conflicting same-version contents. Library
  imports and Blue Hole commit-cache publication use the same no-replace primitive.
- Applying selections copies resolved payloads into preset-owned addon locations,
  preserving unrelated addons and rejecting collisions. Config/scripts/extensions
  are backed up before mutation; `apply_addons.py` removes deselected managed
  preference entries and ensures selected entries exist in bounded background
  Blender, preserving existing preference objects without explicitly enabling
  selected modules. GPU/UI-dependent imports belong to interactive startup. Failure/cancellation
  restores files; successful selection state publishes atomically afterward.
  Launching a preset with managed selections reapplies resolution before launch.
  External side effects of addon startup code are beyond filesystem rollback.
- `ui/page.py` shows LaunchCard configurations and adjacent Manage buttons, and
  management tabs for selection/inventory. Maintenance actions live in More;
  local ZIP imports and the grouped catalog live in the Addon Library settings tab. It uses commonUtils `OperationProgress` for installs, copies, deletions and
  inventory queries. `prepare_close()` requests cancellation and defers destruction;
  `idle` fires only after the worker retires. Preset selection uses filesystem metadata;
  the explicit Refresh action queries Blender. The core rail owns its Blender glyph.
- `ui/layout.py` builds management widgets; the page retains operation and close
  ownership. `addons/ui/page.py` owns the read-only addon catalog. Registration
  and personal settings import these owners lazily. Root `page.py` and
  `library_page.py` remain compatibility imports. Backend managers, installation,
  addon resolution and saved configuration paths are unchanged.

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
A version dropdown selects the file; the editor's visible section tabs select
platforms, using human-readable labels while tab data retains the section keys. Field controls, override/reset behavior, conflict detection and saves
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
(default `Software/Blender_Addons_Library`, `[Resources] blender_addons_path` override) with the
selected preset's `addon-library` ZIP collection. Package metadata is the index:
neither source needs an artist-authored manifest. `for_preset(root)` isolates
imports and resolution; `entries(shared_only=True)` powers the catalog tab.
Preset releases replace provided entries only for matching identity/version;
newest compatible resolution runs over the merged set. Legacy per-user imports
are included only for already selected identities (or requested apply identities),
preserving existing selections without exposing old imports to unrelated presets.
Conflicting duplicate versions inside one source fail explicitly. UI `add()` writes
only the selected preset's library root. Public packaging does not include the ignored addon folder.

Managed inventory stores display names/source. Apply requests sort by casefolded
name and module. Background preparation records enabled preference entries
without registering selected modules. Interactive launch uses sorted
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

`addons/bluehole.py` is deliberately specific to ispaure/BlueHole: allowlisted main/beta/alpha
channels resolve to versioned branches through GitHub's branch API, and commit-pinned codeload ZIPs are
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

## Package revisions and installed status

The shareable library contains one folder per addon, with ZIPs such as
`Anytree/Anytree_2.1.3_2026_10_12.zip`. Identity, numeric version and compatibility
come from package metadata; a trailing `_YYYY_MM_DD` names a package revision.
Resolution chooses the highest declared-compatible numeric version, then the
newest date for that version. Same-version/date packages with conflicting bytes
are rejected. Preset versions override provided packages of the same declared
version; preset imports preserve revision/name in `origin.json`, and their
managed folders include the date. Old undated imports remain discoverable.
Legacy publisher nicknames appended to a version tuple are ignored for numeric
comparison. `_support` is reserved for non-addon backup ZIPs and is not indexed.

ZIP inspection is cached by path and device/inode/size/mtime/ctime fingerprints;
normal changes invalidate the entry. Each refresh resolves its rows from a single
catalog snapshot instead of rehashing the library for every addon row. The cache
is in-memory, bounded and performs no addon imports. First inspection still reads
and hashes every ZIP. Package dates are not proofs of runtime compatibility.

Preset management shows Installed, Latest compatible, Status and Library source.
Installed versions come from files actually found in the preset, with recorded
managed metadata as fallback. Missing files/library packages and pending
installation/removal have separate statuses. Successful apply records numeric
version, package date and package name alongside existing digest/path ownership.
Browsing and saving intent never install addons or query GitHub. Unix executable
bits from ZIP members are retained for bundled addon helper programs.

Blue Hole has a separate `installed_bluehole` snapshot for installed branch,
commit and version. Changing the requested branch preserves the installed
snapshot, including migration from old combined Blue Hole state. The short commit
is displayed with the full commit in its tooltip. During Blue Hole replacement,
`envFiles/default` comes from the new package. All other existing envFiles entries
are restored exactly over the incoming payload from the transaction backup;
user folders are not merged with or overwritten by publisher examples. Failure
restores the complete previous preset as before. Symbolic envFiles roots are
refused; nested user links are retained without copying their targets.

### Grouped addon library settings

Personal feature settings have three tabs: Presets, Versions Definitions, and
Addon Library. `addons/ui/page.py` owns a read-only catalog of shared packages,
grouped by stable identity, collapsed initially, with versions and dated revisions
newest first. ZIP import is a preset-page operation, using its cancellable worker
and close lifecycle. Import completion refreshes choices without changing saved
selections. Shared / Preset provided / User provided (legacy) labels map to
Provided / Preset / Personal storage values. The generated library-inventory.json
is informational only. Preset duplicate/copy operations include the private ZIP
library; deletion removes it with the rest of that preset.

Unchanged managed packages (same module/path/ZIP digest with an installed entrypoint) remain in place during apply. Activation still runs; a missing entrypoint triggers repair. Changed or deselected regular addon packages are replaced/removed as before.

Blue Hole artist environments are stored in the preset’s `addon-data/bluehole/envFiles`, excluding default. Apply snapshots the current installed environments before removal and restores them on reinstall. This storage participates in resource rollback and follows preset copy/delete.

Catalog scans quarantine unreadable packages and conflicting identity/version/date entries, exposing per-file errors while retaining healthy addons. Selected identities without a valid compatible package still fail before mutation. Preset choices are cleared and their owner context invalidated before refresh; saving is guarded until the current preset completes a successful refresh.

Before modifying a preset, changed ZIPs and Deluxe payload ZIPs are copied into the private transaction workspace and inspected against the resolved SHA-256. Extraction and Deluxe stamping read only those verified snapshots. A concurrent source change before copying aborts without mutation; a later change cannot alter installed contents.

Remote Blue Hole check/download failures raise UpdateUnavailable. Apply can retain
a recorded, present, declared-compatible installed copy without a cached ZIP. It
preserves the actual installed branch/commit independently of requested settings,
skips offline Deluxe stamping, and surfaces a launch warning. Missing, unknown or
incompatible installed copies cannot fall back. Cancellation and invalid downloaded
packages are not treated as network failures.

Blue Hole channels resolve to `blender-<major.minor.patch>/<main|beta|alpha>`.
The published families are `blender-4.5.1` and `blender-5.2.2`, each with all three
channels. Resolution uses the managed release being launched: 4.5.1 selects its
own family and 5.2.2 selects its own family. Regression tests cover all six choices
through both branch resolution and update/cache handling. The 5.2.2 family starts
from 4.5.1 alpha; availability does not imply completed Blender compatibility.
The resolver paginates GitHub branches, filters the requested channel and chooses
the highest baseline at or below the exact Blender version. It then requests the
URL-encoded branch endpoint and downloads by immutable commit. No compatible
baseline fails explicitly. Temporary legacy channel names remain readable during
migration; the original 4.5.1 channel cache is reused when commits match. Addon.branch
and installed_bluehole record the actual qualified branch, while preset intent
remains a channel. Offline fallback accepts both legacy and versioned records and
rejects a baseline newer than the preset's Blender version. GitHub's default branch
is independent of Logistics resolution.

## Workflow ownership

`installation/` owns release discovery and installation. `presets/manager.py` owns preset/process policy. `addons/` owns scanning, metadata, library and embedded Blender scripts; `addons/ui/` owns catalog presentation. Feature-level `ui/` composes installation/preset controls.

## GPU-dependent addon activation and diagnostics

Background registration is unsuitable for GPU/UI-dependent addons: Hair Tool
4.5.1 creates GPU shaders during import and Blender rejects that in background
mode. Preparation saves selection entries without explicitly importing them;
the process starts with `--factory-startup`, then reloads the real preset
preferences while `addon_utils.enable` is temporarily suppressed. This preserves
artist settings and saved addon ID properties without running saved selections
(including those in the Deluxe preference payload). The original activation
function is restored in a `finally` block. Interactive
`launch_addons.py` performs ordered reactivation. Its error callback accepts
Blender's exception argument and chains the original cause into the module error.
Interactive failures do not roll back the already prepared selection.

Each interactive launch writes a
unique `blender-launch-*.log` in the preset. Failed background preparation saves
its full output as `blender-addons-error-*.log` outside resource rollback folders.
The bounded UI excerpt starts at the first traceback rather than showing only
unregistration noise; it includes the exit code and full log path. Log persistence
failure retains the excerpt and reports the storage error. These diagnostic logs
are retained until manually removed or the preset is deleted.

`test_blender_activation.py` covers preference-only preparation, preserved existing
entries, interactive exception chaining, verbose shutdown logs and log-save errors.

On October 21, 2026, the local Apple Silicon Blender 4.5.1 reproduced Hair Tool's
background GPU import failure. After the fix, disposable presets passed background
preparation of all 22 compatible shared addons, repeat preparation with removals,
and all 22 plus cached Blue Hole 6.9.21 with Deluxe enabled. An interactive verifier
confirmed Hair Tool, Angle Tool and AnyTree enabled with spaces and Unicode in the
preset path. The verifier completed, but Blender did not finish quitting within
45 seconds, so the test process was killed and temporary presets were removed.
This is macOS activation evidence; Windows runtime validation remains outstanding.
