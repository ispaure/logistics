# File browser development

This is the Logistics integration guide for adding information panels, thumbnails,
right-click actions and double-click behavior. Reusable APIs and standalone examples
live in the [commonUtils feature guide](https://github.com/ispaure/commonUtils/blob/main/ui/features/README.md) and
[browser reference](https://github.com/ispaure/commonUtils/blob/main/ui/README.md). Keep feature READMEs focused on
their domain rules and link here for browser wiring.

## Ownership and entry points

`commonUtils.ui.file_browser.FileBrowser` owns views, root-bounded navigation,
selection, generic File Information, filesystem actions and background preview/scan
workers. `desktop/file_browser.py:BrowserView` hosts it and installs enabled
Logistics contributions through `registry.get_browser_extensions()`. Feature-owned
hosts can add their own controls around the same component.

The Logistics browser host uses zero outer pane margins and `BrowserIndexStatus`
to compact the shared workspace footer's padding, font, buttons and activity
track. Embedded, standalone and detached browser workspaces use this same
presentation; progress subscriptions and index actions remain owned by
`WorkspaceIndexStatus`. Workspaces likewise uses zero outer margins and places
its source-discovery progress in one horizontal row below all panes. Sources and
Actions share a left column, with a full-height Files pane on the right. Pane
headers are hidden in the fixed layout; dock dividers remain resizable.
The Workspaces Files pane reuses `_browser_view` for Local,
LocalCrypt and remote browsing, retaining normal document activation. See the
[folder source contract](features.md#remote-folder-source-context) for its action
scope, browser retirement and pane-lock policy.

`FoldersPage._entry_browser_source` resolves the selected local/private/remote copy
and retained credential association before the existing browser construction and
mount path. `_show_entry` retains detail generation/cancellation and credential
admission; `_prepare_workspace_actions` mounts its accepted root scope before
submitting/coalescing the retained detail job. `_details_ready` rejects stale or
revoked results before `_mount_action_sections` constructs contributed controls.
Browser replacement, unlock callbacks and retirement remain with the page; the
Qt-independent `FolderController` still captures discovery/detail worker inputs.

Desktop `FoldersPage` filters `Legacy-` workspace names case-insensitively after
source/credential selection, before building the tree. **Settings → Workspaces →
Show Legacy (session only)** starts unchecked and uses an application-owned
`WorkspaceVisibility` object shared by all desktop workspace and Settings pages.
Discovery refreshes and window changes preserve it; no configuration value is
read or written for it.

`desktop.location_context` presents storage identity in document dock titles and
a browser row beneath the navigation controls. `FoldersPage` publishes local
workspace roots from its discovered snapshot; longest-root matching distinguishes
nested workspace names. The configured managed Local root covers files opened
before discovery completes. Provider identity takes precedence over synthetic
paths for remote and LocalCrypt documents. Remote providers expose their crypt
type as `encrypted`; all direct remote document buffers and LocalCrypt views are
private, so their titles carry `(🕵️ Session-Only)`.

`DocumentPane` formats the active filename while leaving the reader/editor's
original title authority intact. Title/idle changes and refreshed root snapshots
update the dock through `title_changed`, including detached containers. Editor
choices, Markdown storage, EPUB/comic sources and PDF file paths supply active
identity; Save As and adjacent-reader navigation are resolved anew. Locked private
guards retain their redacted title. Browser state uses the same context and the
shared mobile folder/cloud geometry, updates on navigation, and clears the remote
name on credential revocation. This presentation never discovers remote folders
or performs provider I/O itself.

Declare new capabilities in the feature's `register() -> Feature`, importing
`Feature` from `features.contributions`. That Logistics declaration extends the
shared declaration with folder/server sources, workflows, pages and Debug actions.
Do not import feature implementations into the generic host or add format checks
there. Built-in Markdown activation explicitly permits editing; documentation
buttons using `open_markdown(path)` get preview-only windows by default (holding Alt enables editing centrally). Pass
`allow_edit=True` only when the caller intends to offer editing. Link navigation
retains the originating window's mode. See [UI architecture](features.md#unified-feature-declarations) for
application discovery and initialization.

## Add a format, panel and context action

In `features/<feature>/files.py`, keep constructors cheap and put format-specific
loading behind file hooks:

```python
from commonUtils.filesystem.files import File
from commonUtils.filesystem import BrowserDetails, BrowserPanel

class ProjectFile(File):
    def browser_panels(self):
        return (BrowserPanel('project.details', 'Project Details', self.details),)

    def details(self):
        return BrowserDetails(fields=(('Name', self.file_name),))

    # Optional: set browser_has_thumbnail = True and implement
    # browser_thumbnail(size), where size uses physical display pixels.
```

In `features/<feature>/ui_contributions.py`, declare rules and operations separately:

```python
from commonUtils.filesystem.directories import Directory
from commonUtils.ui.features import BrowserExtension, FileActivation, FileType, SelectionAction
from features.contributions import Feature

PROJECT_TYPE = 'features.project.files:ProjectFile'

def edit_selection(context):
    # Replace with your feature-owned dialog; import Qt/UI lazily.
    # context.paths contains only the accepted selection.
    print('Edit:', context.paths)

def open_project(context):
    print('Open:', context.path)

def folder_fields(directory, stats):
    return (('Project files', stats.extension_counts.get('project', 0)),)

def register():
    return Feature(
        id='project', label='Project',
        file_types=[FileType(PROJECT_TYPE, extensions=('project',))],
        browser=BrowserExtension(
            actions=[SelectionAction('edit', 'Edit Project Data',
                                     (PROJECT_TYPE, Directory), edit_selection)],
            activation=[FileActivation(PROJECT_TYPE, open_project)],
            folder_fields=folder_fields,
        ),
    )
```

Export `register` from the feature's `__init__.py`. Deferred `module:Class` references
allow discovery before dependencies/UI imports. The registry registers owned types
before initialization; the general browser installs the declaration automatically.
For replacing an existing type rather than introducing a format, use the separate
[`file_type_overrides` declaration](https://github.com/ispaure/commonUtils/blob/main/formats/README.md#replace-an-existing-type-with-your-subclass)
with a subclass of the original type.

## Panels, selection and activation

All applicable panels appear as tabs alongside generic File Information. Return
`BrowserDetails` from loaders, not widgets. Panel/thumbnail loaders execute on
browser workers and must not access Qt widgets or prompt for user input. Report
unavailable/locked previews through returned details; prompt only from an explicit
GUI action. Use shared folder scan results for counts instead of scanning again.

`SelectionAction` declares accepted file classes and/or `Directory`; mixed selections
are filtered before the handler runs. Right-clicking an unselected item targets it
alone. Folder expansion/recursion, deduplication and domain validation remain the
handler's responsibility. Action IDs are unique within the feature; the framework
namespaces them and groups entries under its label. An `is_available(context)`
predicate can hide an action when required configuration is absent; execution
still needs validation because state may change after menu construction.

The shared browser provides inline Rename and Cut/Copy/Paste by default. Logistics
adds Bulk Rename beside Rename for files and folders. Menus put opening and
clipboard actions first, then rename commands, feature tools, and Reveal last.
`SelectionAction.order` (default 100) controls feature/command ordering;
`category='rename'` places a contribution in the rename group. Comic metadata
editing precedes comic compression/encryption; archive and image tools follow,
with folder-maintenance commands last.

`FileActivation` handles matching files, with first matching declaration winning;
folders keep navigation behavior. Panels/thumbnails do not require activation or
an action. For generic built-in browser controls and direct hook signatures, use
[the shared reference](https://github.com/ispaure/commonUtils/blob/main/ui/README.md).

## Controllers, toggles and closing

Use `BrowserExtension.create_controller(host)` for state owned by one window;
handlers receive it as `context.controller`. `context.host` is the dialog parent
and `context.browser` the shared component. Do not put widgets or worker state in
the globally cached feature declaration. A feature-specific host may pass its
existing controller to `Feature.install_browser`; retain the returned binding.
The [shared guide](https://github.com/ispaure/commonUtils/blob/main/ui/features/README.md) documents explicit installation.

Session toggles deactivate owned type rules, actions, activation and folder fields.
Cached browser objects are re-resolved after registry revisions; existing file
instances retain their class. Bindings/controllers remain owned by the host so
open dialogs and jobs can finish, and enabling reuses them. Disabling does not
undo initialization or cancel operations. Legacy installers/hooks remain supported;
new declarations must not mix `browser` with legacy `browser_extensions`.

Actions and activation run on the GUI thread. Capture validated inputs there,
then use shared workers for expensive operations. Refresh the browser after writes.
Hosts must call controller/binding `prepare_close()` and browser `stop()`, ignore
close while work remains, and retry on `idle`. Keep windows and worker owners alive
until completion. The general `FileBrowserWindow` implements this protocol; adding
a custom host requires equivalent handling. See [worker lifecycle and cancellation](architecture.md#long-running-workflows-and-safe-closing).

## Validation

Use disposable fixtures and the [project test commands](getting-started.md).
`test_file_browser_window.py` checks general host installation, toggles and closing;
`test_feature_registry.py` checks discovery/ownership. CommonUtils tests cover
shared selection, panels, registry revisions and declarations. Feature tests should
check their handlers, format data, validation and failure behavior instead of
repeating the shared browser contract. Manually check native menus/previews and
window shutdown on the platforms affected by UI changes.


The embedded `FileBrowserPage` and standalone `FileBrowserWindow` wrap BrowserViews
in `commonUtils.ui.workspaces.workspace.Workspace`. Feature bindings/controllers belong to
one view and move with its dock when detached or reattached. Each view independently
subscribes to feature toggles and participates in cooperative shutdown. Browser
search and storage dialogs use shared directory metadata snapshots/cache; their
workers are included in `FileBrowser.stop()` and `idle` handling.


Archive inspection uses shared `ArchiveFile`/`ZIPFile` information hooks on the
existing preview worker. The [Archives feature](../features/archives/development/development.md) installs its
manager and extraction actions through `SelectionAction`, its ZIP/TAR opening
through `FileActivation`, and per-view routing through `create_controller`.
CBZ activation remains with Comics. Successful writes invalidate the affected
file and reconcile its parent through the existing browser refresh APIs; the
generic host performs no archive-specific dispatch or password prompting.

## Shared provider views

The commonUtils regular and provider browsers now share list, tile and column
presentation. Logistics retains crypt credentials, private-reader routing, transfer
policy and domain-specific comic/EPUB cover loaders. The shared model supports
opaque identities and custom properties; its API belongs to
[commonUtils](../../Python/commonUtils/docs/reference/ui/resource-providers.md#shared-item-presentation).
The mobile UI has not been migrated in this first phase.
