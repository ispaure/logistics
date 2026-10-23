# Feature organization and lifecycle

[Developer index](development.md)

## Where new code belongs

Use the feature as the primary owner. Follow this convention when the feature
needs these layers; do not create empty packages for small integrations:

```text
Python/features/<stable_id>/
    __init__.py              # lightweight, lazy registration
    config.ini               # feature defaults, when needed
    <domain modules>.py       # behavior named for its purpose
    ui/                      # desktop presentation
    mobile/                  # mobile presentation/adapters, when supported
    mobile_sources.json      # selected mobile sources, when supported
    README.md                # short link to docs/development/development.md
    docs/
        docs.md
        development/development.md
        user/user.md
        user_mobile/user_mobile.md  # when supported
    user_docs/index.md       # compatibility link to docs/user/user.md
```

The developer landing should begin with a small change-to-module/test table:
where to change presentation, domain behavior, saved state and mobile adapters,
with the actual focused test filenames. Link to the shared [validation commands](testing.md)
rather than copying environment setup into every feature. Every documentation
folder needs its own landing and parent links; see [documentation ownership](documentation-hierarchy.md).

Follow factories in `__init__.py` to find canonical implementations. Old root-level
modules may forward imports to `ui/`; keep compatibility where needed and put
new behavior in the implementation. Do not create duplicate feature packages for
core browser/Markdown hosting or Bulk Rename, which retains its existing `desktop`
owner. Registry/settings infrastructure also retains its current `features/`
paths; see [infrastructure ownership](feature-infrastructure.md).

Portable domain modules should import without Qt, Toga or the application host.
Presentation depends on domain logic and explicit host contracts. The host owns
navigation and application lifecycle; reusable mechanisms belong in commonUtils.
For mobile changes, update the owner's payload manifest and run packaging checks.
Feature IDs, saved keys, tests and shell packages are not renamed as incidental
cleanup.

## Unified feature declarations

New features expose `register() -> Feature(...)` from their package `__init__.py`.
Import `Feature` from `features.contributions`: it extends the reusable
`commonUtils.ui.features.Feature` with Logistics Debug actions, folder/server/source
contributions, workflows and pages. File types and browser capabilities are declared
on that same object. See [the commonUtils author guide](https://github.com/ispaure/commonUtils/blob/main/ui/features/README.md).

The following declaration assumes feature-owned handlers/factories named below;
see the browser guide for a complete registration example.

```python
from commonUtils.ui.features import FileType, BrowserExtension, SelectionAction, FileActivation
from commonUtils.filesystem.directories import Directory
from features.contributions import Feature, WorkflowContribution

def register():
    return Feature(
        id='project', label='Project', requires=('images',),
        file_types=[FileType('features.project.files:ProjectFile', 'project')],
        browser=BrowserExtension(
            actions=[SelectionAction('edit', 'Edit Project Data',
                ('features.project.files:ProjectFile', Directory), edit_selection)],
            activation=[FileActivation('features.project.files:ProjectFile', open_project)],
            create_controller=create_controller,
        ),
        workflows=[WorkflowContribution('project.manage', open_management_dialog)],
    )
```

Handlers accept `ActionContext`, whose `paths`/`selection` are already filtered to
accepted types and whose `host`/`controller` belong to the current window. No named
service registration is required. Handler/controller factories should import UI
lazily. Deferred `module:Class` references let the registry inspect requirements
before importing classes that need those dependencies.

`registry.get_feature_definition` caches one declaration per feature module. Its
id, label, requirements, type rules, initialization and UI contributions all come
from that declaration. Startup registers owned types before any initializer runs;
browser hosts install bindings from the declaration and retain their controllers
across toggles. Legacy FEATURE_* metadata, register_file_types/get_contributions
hooks and BrowserExtensionContribution installers remain supported for features
not yet migrated. A declaration cannot mix `browser` with legacy
`browser_extensions` installers.

For panels, right-click actions, activation and per-window controller wiring,
see [File browser development](file-browser.md).

## Configuration ownership

Feature-specific configuration belongs inside the feature package:

```text
features/<feature>/config.ini
```

A value should remain in the root Logistics configuration only when it is
application-level/core configuration or when multiple independent features
directly read the same setting.

A feature depending on another feature does not make the dependency's private
configuration shared. The owning feature remains responsible for exposing the
behavior or data needed by dependent features.

## Remote folder source context

Remote features may contribute multiple selectable Folders sources through
`RemoteFolderSourceContribution`.

The Folders page owns fixed `Local`, `Cloud` and `Home Server` categories. A remote source supplies
remote names plus opaque backend context. That context is carried through the
generic `FolderEntry` model and interpreted only by the feature that owns it.

For rclone, the context is a selected credential `.conf` or `.session` path,
or a `CopyContext` carrying the saved copy’s package association. The context
does not change the managed local sync folder name. FUSE separately derives a
mount-path identity from that config path; do not discard it when mounting.

The desktop category adapter is `services/folders/workspaces.py`. Local merges
physical copies by path while retaining the provider context used by sync tools.
The Local Source dropdown filters that merged list into Dropbox, Rclone and
Others, defaulting to Rclone; there is no combined All option locally. Classification uses provider ownership and physical paths: managed Local
folders and rclone-supplied LocalCrypt copies belong to Rclone, Dropbox sources
belong to Dropbox, and remaining copies belong to Others. Refresh preserves the
filter and selected entry; changing tabs resets Local to Rclone and remote
credential filters to All. Source/filter changes clear folder selection; tree
rebuilds only restore an explicit selection and never choose the first entry.
A missing or hidden selection clears both browser and action scope.
Loaded rclone contexts appear online; `CopyContext` records also keep locked
online destinations visible. The adapter groups saved copies by credential ZIP
and remote, preferring loaded account snapshots. Unassociated rclone folders
receive a credential-required Cloud placeholder. Matching honors the provider’s
optional local-folder fallback, so an already matched remote does not also get
a placeholder. Unlocking rediscovers the account’s
other remotes while preserving its selection. Home Server uses mobile's explicit network-share package names, not protocol
inference. Encrypted remote metadata is read on the discovery worker.

`FoldersPage` owns a full-height browser stack beside the source tree and action
details. Actions sit below Sources in the left column. Required credential
unlocks gate action detection; stale unlock results cannot publish credentials.
The selected tree entry owns the action scope; browser navigation never rewrites
it. Browser construction waits for page visibility. Replaced views cancel work and
remain owned until `idle` and `prepare_close()` permit deletion; page shutdown
waits for discovery, detail detection and every retained browser.

`desktop/pages/workspace_panes.py` supplies resizable native dock panes. Set
`WORKSPACE_PANES_LOCKED = False` or construct `FoldersPage(panes_locked=False)` to
experiment with moving/detaching them. The default hides the fixed pane headers
and removes closing, moving and floating controls. Split dividers remain usable. This is a code setting,
not a persisted user preference. `services/folders/appearance.py` owns portable
folder paths and lock colours shared by desktop and mobile; it is included in the
mobile services manifest. `WorkspaceTree` paints the expanded hierarchy guides,
without a top-level branch gutter, using 20-pixel nested indentation, 18-pixel
icons and compact rows. Embedded browser creation turns its preview toggle off
for ordinary, encrypted and remote views; retained browsers keep the user's
subsequent toggle choice during refresh. Locked session locations are intercepted
before browser construction and hosted by rclone's `WorkspaceUnlockView` in Files.
Its password validation runs off the GUI thread. Cancelled or retired views never
publish credentials, and worker-owning views stay retained until idle.

## Shared file types and browser bindings

[File browser development](file-browser.md) is the central Logistics guide for
file types, preview panels, context menus, activation, controllers and safe closing.
The reusable API and standalone examples live in the
[commonUtils author guide](https://github.com/ispaure/commonUtils/blob/main/ui/features/README.md).

### Persistent feature controls

The core Features tab shows installed features, enabled state, requirements, and
enabled dependents. Enabled choices are saved in private feature preferences and loaded before startup initialization. Enabling a feature
enables its hard dependencies first; disabling a dependency with enabled dependents
is refused with their names. Discovered packages with import errors or missing hard dependencies are listed
but cannot be enabled.
`is_feature_available` still describes installed packages/dependencies;
`is_feature_enabled` and `get_enabled_features` describe the active session.
Contribution queries and workflow lookup return only enabled features.

Related engines may declare `FEATURE_GROUP = '<leader module name>'` to share
one user-facing settings entry. `FeatureState.members` retains their runtime
names; toggling either the leader or a legacy member applies to the whole group.
Requirements and dependents are presented at group level, while file-type
ownership, controllers and configuration files remain attached to each engine.
Books & Comics uses this to keep the existing `books` and `comics` APIs intact.

Features remain imported. Their initializers run once per session; disabling does
not unmount remotes or reverse other initialization effects. Declared format rules receive the declaration id as their owner automatically.
Legacy registration hooks run inside `file_types.owner_scope(feature_name)`;
explicit late registrations outside a declaration must pass that owner id. Disabling an
owner removes its rules from resolution and bumps the registry revision; enabling
restores the same rules and precedence. Rules remain in the ownership ledger and
can still be permanently removed with `unregister`. A failed enable restores enabled
state and format activation; it cannot undo arbitrary initializer side effects.

Registry observers update main tabs and active core page actions. Disabled feature
pages are hidden and retained, then reused on enable so existing state/work can
survive. Hidden core pages refresh when selected. Browser hosts update immediately:
commonUtils `Feature.install_browser`/`Feature.set_enabled` coordinate declared bindings and
format rules. Lower-level `install_extension`, `set_extension_enabled`, and
`remove_extension` manage owner-scoped services, action/activation providers and
folder fields, restoring
previous handlers where extensions overlap. Logistics decides feature availability;
commonUtils contains no project-specific dependency logic.

## User documentation

Each distributed feature owns a `docs/docs.md` wiki landing, `docs/user/user.md`
for desktop usage and `docs/development/development.md` for implementation and
validation. Features available on mobile also have `docs/user_mobile/user_mobile.md`.
Keep `user_docs/index.md` and package README files as short compatibility links.
Settings opens the canonical user guide with the feature's entire docs tree even
when the feature is disabled or a dependency is missing. Missing guides disable
only their help button. Separately installed features can retain their legacy
`user_docs` entry until their own repository migrates.

Every folder has a same-named landing (`banana/banana.md`). Begin every page
with an H1, below optional YAML properties, and mention each child page in its
parent's text. Use relative links. User guides explain prerequisites, controls,
outcomes and recovery; developer guides explain ownership, contracts and checks.
Application-wide UI and Workspaces workflows live in the root Logistics wiki;
Bulk Rename stays with its existing `desktop` owner. Shared APIs and external
feature internals remain documented in their own repositories.

The shared `commonUtils.ui.markdown` viewer owns rendering, local link history and
Back/Forward. Normal guide clicks open preview-only windows; Alt-click opts into
editing. Editing-enabled windows start in Formatted mode, including general
file-browser Markdown activation.

## Add a feature

1. Add a direct package under `Python/features/<stable_id>` with `__init__.py`.
   Discovery sorts eligible packages, ignores underscore-prefixed folders and
   records import failures as unavailable features instead of hiding the app.
2. Expose `register()` returning `features.contributions.Feature` with a unique
   ID, label and only real hard dependencies. Keep UI imports in factories/handlers.
3. Declare types/browser bindings and application contributions for the workflow.
   Use [extension contracts](extension-points.md) instead of adding feature imports
   to the generic shell or copying shared widgets.
4. Put defaults beside the feature and private state in an appropriate user path.
   Retain old public keys/interfaces when compatibility is required.
5. Add user documentation and its in-app entry link, focused fixture tests and
   a root/index link. Exercise availability, toggles, worker close and failure paths.

All distributed packages currently expose unified declarations. Legacy metadata
and hooks remain compatibility paths; do not remove them just because a migrated
caller no longer needs them. Optional dependencies do not order startup or enable
the optional package automatically.

## Current cross-feature dependencies

| Consumer | Required/optional relationship |
| --- | --- |
| Comics | Requires Images for its compression pipeline |
| Books & Comics settings group | Presents Books and Comics together without merging runtime identities; EPUB does not require Calibre |
| FUSE | Requires rclone and selected credential context |
| Plex | Requires rclone and a paired local folder/remote context |
| YouTube Downloader | Declares rclone optional; local downloading remains independent |
| Git | Can open working files through enabled Text Editor; repository commands still use Git |
| Archives and Comics | Share archive access but retain separate activation and mutation policies |

Most other features are independent registry entries with external runtime
prerequisites, not dependencies on another Logistics feature. Do not equate an
installed feature package with a working external executable, credential or service.

The [Blender manager](../features/blender/development/development.md) is an independent
page with feature-owned pinned releases and whole-application installation adapters.
It reuses verified download mechanics, stores installations/presets in the per-user
Logistics root and queries the selected Blender for saved addon state. Its catalog
contains metadata only; it does not add Blender packages to Logistics releases.

## Feature selection presentation

Feature packages expose `FEATURE_DESCRIPTION` beside their registration entry
point. The registry includes the visible group leader's description in
`FeatureState`; Settings uses it on selection cards and category tooltips. Display
labels come from declarations; stable feature IDs, package paths and saved choices
remain unchanged when labels are clarified.

Software feature selection uses `FeatureDefaults.disabled_list-str`. Personal
choices are sparse `FeatureOverrides.<stable_id>_bool` fields. Presence means an
explicit override even when its value matches the default; setting a toggle never
writes untouched choices. Dependencies get enabled overrides only if activation
had to change them. Per-card reset removes its group's engine keys, applies their
individual software defaults and enforces dependency policy. Page-wide personal
reset removes all feature overrides. Cards and category tree items are retained
across enable/disable notifications to preserve focus and scroll position.

`feature-overrides-v2` migrates legacy personal disabled-list snapshots atomically:
only differences from current defaults become sparse keys, existing new-format
keys take precedence, and the old list is removed. Matching snapshot choices were
not distinguishable from untouched values, so they inherit after migration.
Unknown differing feature IDs are preserved. Failed publication keeps the old
selection effective and leaves the migration pending for retry. Completion stays
outside resettable configuration alongside the existing migration ledger.

## Runtime owner boundary

`features.application.registry` is the explicit application-owned registry instance;
callers use it directly. The former forwarding module has been removed.
`FeatureRegistry` composes preference state, dependency functions, activation and
contribution collection under `features.runtime`; see the
[infrastructure owner map](feature-infrastructure.md#registry-runtime-ownership).
Discovery, feature IDs, preference schemas and declaration identities remain
unchanged. Enabling/disabling still uses dependency checks and rollback; splitting
these owners does not make a disabled feature's active workers disappear.
