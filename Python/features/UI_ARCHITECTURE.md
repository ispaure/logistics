# Feature UI Ownership

Feature-specific UI belongs to the feature that owns the behavior.

Typical structure:

```text
features/<feature>/
├── backend modules
├── ui_contributions.py
└── ui/
    ├── page.py
    └── dialogs.py
```

The generic `ui_new` package owns only application-level presentation:

- Main window / tab host.
- Generic Folders page.
- Generic Servers page.
- Generic Debug page.
- Generic workflow dispatch.
- Shared UI primitives that are not feature-specific.

## Unified feature declarations

New features expose `register() -> Feature(...)` from their package `__init__.py`.
Import `Feature` from `features.contributions`: it extends the reusable
`commonUtils.features.Feature` with Logistics Debug actions, folder/server/source
contributions, workflows and pages. File types and browser capabilities are declared
on that same object. See [the commonUtils author guide](../commonUtils/FEATURES.md).

```python
from commonUtils.features import FileType, BrowserExtension, SelectionAction, FileActivation
from commonUtils.dirUtils import Directory
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

Comics uses this API in `features/comics/ui_contributions.py:register`. Its package
exports `register`; the old `register_file_types` name is a compatibility helper.
The CBZ class owns metadata/thumbnail loading; the declaration owns Edit Metadata,
Compress Comics, reader activation, folder counts and its controller factory.
Both the general browser and the comic library consume the same declaration; the
library supplies its existing controller to keep catalog suggestions and close
coordination with its surrounding controls.

## Startup and refresh

Both launch entry points share the same startup sequence. Qt is created before
feature initialization so startup failures can display their error dialogs.

The registry initializes available features in dependency order: every hard
dependency completes initialization before its consumer. Optional dependencies
do not affect availability or impose an initialization order. All enabled features register their file types before any initialization hook runs.
Initialization runs once per feature per session.
Startup hooks are checked for callability before invoking the first hook, so an
invalid hook is rejected before other features begin their startup work.

Pages populate themselves during construction. The main window refreshes a page
when the user switches to it, rather than triggering a second refresh while
creating the first tab. Contributed page IDs must be unique; the main window
validates them before invoking any page factories.

The Folders page uses `services.folder_sources.discover_folder_sources()` to read
each source provider and its folder list once per refresh. Changing a source or
credential uses that snapshot. An explicit refresh reads the providers again;
there is no process-wide cache of folder listings or contribution sets. Remote
exclusions are applied before deciding which local folders are represented by
a remote. Selection restoration uses the feature and source kind as well as
the displayed label, so equal labels from different features remain distinct.

## Workflows

A feature registers a `WorkflowContribution` with a stable workflow ID and a
lazy handler. The handler imports the feature-owned dialog only when the user
invokes the workflow.

This prevents unrelated feature UI modules from being imported together.

`ui_new.actions.execute_action()` handles actions consistently for Folders,
Servers, and Debug. Disabled actions cannot execute. Workflow actions pass their
data and parent through to the feature-owned handler, whose dialog owns any
confirmation and refresh. Destructive callback actions retain the application
confirmation and refresh their owning page after the callback returns normally.

## Standalone pages

A feature registers a `PageContribution` containing a lazy `create_page`
factory. The main window does not know which feature owns the page or where
its implementation lives.

## Debug

The Debug page provides a core **Open File Browser…** button and renders
`DebugActionContribution` objects from the feature registry. The core button asks
for a folder and opens `ui_new.file_browser.FileBrowserWindow`. If a Debug action references a workflow, the generic workflow
dispatcher resolves the corresponding feature-contributed workflow.

The Debug page never imports feature implementations directly.


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
does not become part of logical folder identity or filesystem layout.


## Shared file types and browser bindings

Declarations register their `FileType` rules with automatic feature ownership.
Legacy `register_file_types()` hooks remain supported and run inside an owner scope.
Registration applies to all future Directory listings and file resolution in the
process, including Directory objects created earlier. Existing File objects retain
their class. The browser re-resolves cached objects after registry revision changes.

`FileBrowser` owns views, navigation, selection, generic details and filesystem
actions. File classes supply panels and thumbnails. A declared BrowserExtension
supplies selection actions, activation and folder fields. `Feature.install_browser`
compiles those capabilities into a reversible layer and creates optional per-window
controller state. Applications still own safe window/controller shutdown. Legacy
file-type action/activation hooks and direct services/providers are also supported.

The general Logistics browser queries `registry.get_browser_extensions()` for
lazy installers. This includes automatically adapted unified declarations and
legacy installers; `ui_new` never imports project types or handlers. The installed
binding forwards its controller's `prepare_close()/idle` protocol. The general
host has no comic library tabs or automatic collection-wide catalog scan; metadata
entry remains available without catalog suggestions.

### Session feature controls

The core Features tab shows installed features, enabled state, requirements, and
enabled dependents. Toggles are session-only and reset on restart. Enabling a feature
enables its hard dependencies first; disabling a dependency with enabled dependents
is refused with their names. Missing packages are listed but cannot be enabled.
`is_feature_available` still describes installed packages/dependencies;
`is_feature_enabled` and `get_enabled_features` describe the active session.
Contribution queries and workflow lookup return only enabled features.

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

General-browser controllers and the comic library respond to toggles. Disabling
Comics removes folder actions and handlers, refreshes selected metadata/covers, and
makes future CBZ resolution generic. Re-enabling reuses controllers. Open readers,
metadata dialogs and running workers remain usable and can finish; controllers stay
owned by their host until its normal worker-safe close. Per-window handlers are
intentional because they own selection, dialog parents and workers. The globally
shared part is feature/type availability, not widget instances.


## Long-running workflows and safe closing

Shared background primitives live in commonUtils, while the feature owns inputs,
password prompts, transaction boundaries and result presentation. Use
`commonUtils.ui.operation_progress.OperationProgress` for progress/cancellation
controls and `commonUtils.ui.operations.Operation` for simpler background callbacks.
[Workflow recipes](../commonUtils/RECIPES.md) demonstrate both the callback contract
and safe owner lifetimes.

Capture validated inputs on the GUI thread; callbacks must not read widgets,
show dialogs or prompt for passwords. OperationProgress completes only after its
worker stops. Route close/Escape to its cancellation request during work and defer
destruction. The browser's panel/thumbnail workers have a separate `stop()/idle`
lifecycle; controllers must account for their own readers/editors/jobs as well.

Choose cancellation boundaries per workflow. Separate ZIP creation checks between
chunks and discards staging before publication. Comic batches finish and verify
the current archive before stopping, preserving completed comics. A returned batch
can contain individual failures even when the outer worker reports no exception;
present both worker errors and per-item results. Disabling a feature removes future
contributions and type resolution without cancelling existing work.

[Application configuration](../../CONFIGURATION.md) describes resource roots and
software provisioning. URLs/hashes/platform policy belong to Logistics; reusable
download, stream and worker mechanisms belong to commonUtils.
