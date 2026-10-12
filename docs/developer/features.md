# Feature organization and lifecycle

[Developer index](README.md)

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

The generic Folders page always owns a `Local` source. A remote source supplies
remote names plus opaque backend context. That context is carried through the
generic `FolderEntry` model and interpreted only by the feature that owns it.

For rclone, the context is the selected credential `.conf` path. The context
does not change the managed local sync folder name. FUSE separately derives a
mount-path identity from that config path; do not discard it when mounting.

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

Each distributed feature provides canonical `user_docs/README.md` beside its
developer `README.md`. Keep `user_docs/index.md` as a compatibility entry page.
Settings opens `user_docs/README.md` directly when the folder's only Markdown
files are `README.md` and `index.md`; otherwise it uses `index.md`, allowing an
index of multiple pages. Its User Guide button works even when the
feature is disabled or a dependency is missing. Keep these guides focused on
controls, prerequisites, outcomes and recovery; implementation and validation
remain in README.md. Missing guides disable only their help button.

Use relative Markdown links to other user guides or the root USER_GUIDE.md.
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

The [Blender manager](../../Python/features/blender/README.md) is an independent
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
