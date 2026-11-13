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

## SQLite inspection boundary

The shared browser contributes **Inspect SQLite…** without changing activation.
Logistics opts ordinary local files into explicit editing through
`_sqlite_write_allowed`; encrypted-copy paths remain provider-owned. The host
passes the current directory-index and job-database paths as read-only policy.
Shared access checks additionally reject protected local roots, network mounts,
links, unsupported providers and recognizable managed-index schemas. No database
is copied out of remote/private storage for SQLite editing. Native mobile has no
SQLite editor. The [shared SQLite API](../../Python/commonUtils/docs/development/reference/integrations/sqlite.md)
owns SQL, identity checks and transactions; its
[Qt integration guide](../../Python/commonUtils/docs/development/reference/ui/sqlite_browser/sqlite_browser.md)
owns worker and dialog contracts. Directory-index schemas, queues, snapshots and
retention remain under their existing owners.

`BrowserView.close_in_background` is conditional on the SQLite controller's
retirement readiness. A dirty editor veto keeps its browser tab attached; a
clean worker can retire in the background. SQLite close checks precede feature
shutdown so cancelling a prompt does not stop unrelated feature controllers.
`tests/files/test_sqlite_browser_host.py` exercises the real host action, filter,
save/reopen, protected policy and dirty workspace close. Existing browser and
launch suites cover the normal host paths; native platform acceptance remains
separate from offscreen host tests.

## Browser presentation

### Directory-index admission and foreground demand

| Surface | Trigger and scope | Cache and worker ownership |
| --- | --- | --- |
| Desktop Files | Open/navigation reconcile the visible folder; initial discovery can recurse. Refresh covers the subtree. Search and size views read saved snapshots. | Launch-owned Qt `IndexService`, commonUtils platform-cache database and durable queue. Each view retires its own subscription. |
| Mobile Files | Opening Search or changing its location prepares the recursive ordinary-local scope. Settled typing reads saved results, joining preparation when no snapshot exists. | App-private `Cache/directory-index.sqlite3`; one leased host runner, independent query/preparation cancellation. |
| Desktop/mobile Notes filenames | A settled nonempty query validates the library root. Navigation supplies priority hints without starting a scan. | Same ordinary database/coordinator as Files on that host; separate scoped readers and query-generation fences. |
| Notes Files, Calendar, content and links | Navigation lists a folder; Calendar and backlink discovery visit their bounded inventories; content search reads eligible bodies; direct/suffix links retain specialized lookup. | Provider-owned work. LocalCrypt inventories reuse its fingerprinted RAM/optional sealed names; content and direct links retain separate freshness checks. |

The ordinary queue and elected-runner lock sit beside the index as
`directory-index.jobs.sqlite3` and `directory-index.jobs.lock`. Private, session-only,
virtual and remote providers never enter these ordinary stores. LocalCrypt sealed
records use the provider's credential-bound `Cache/LocalCryptNames` owner instead.

The desktop launch-owned `IndexService` registers its commonUtils coordinator
with `services.directory_index`. Mobile hosts acquire a process-shared lease for
their app-private index; a second iPad scene shares the same runner. The mobile
thread starts only when a scan is submitted. Closing one scene removes only its
lease; the last close requests cooperative retirement. Idle or locked hosts pause
admission, and an active sibling scene may continue work.

Eligible ordinary Notes filename queries and mobile Files preparation use this
same coordinator. Names-only validation is distinct from the browser's ordinary
metadata check. Compatible same-root and covered descendant requests share work;
pending requests can expand to an ancestor without dropping followers. Explicit
refresh and mutation notifications preserve their existing semantics. Saved reads
use separate SQLite snapshots and do not wait for a busy writer.

The host selects jobs using visible-folder/search hints after a 150 ms quiet
period. An unrelated traversal can yield cooperatively after an initial 500 ms
turn; a deferred job becomes eligible for a fair turn after five seconds. Resumed
turns double their guaranteed duration so atomic reconciliation, whose unfinished
transaction rolls back on cancellation, can eventually commit. Backgrounding all
scenes still interrupts promptly at the next cooperative boundary. These
are scheduling intervals, not UI latency guarantees or interruption of blocking
provider I/O. commonUtils retains checkpoints and elects a single runner; host
policy chooses which compatible work runs next. Navigation, close and privacy
transitions retire the corresponding hints.

Mobile cached filename matches stream in batches of 50, with each path admitted
through the provider before publication. Later cumulative updates are throttled;
the query/route/privacy generation rejects obsolete callbacks. The status stays
in progress until the final result, including a partial marker when necessary.
Cold search follows preparation and may reuse available partial snapshots;
corrupt-cache reads fall back to live provider search. LocalCrypt and other
private or virtual namespaces remain outside the ordinary index and job queue.

Focused coverage includes shared receipt overlap/recovery, host fairness and
scene leases, warm publication while a writer is held, changed/deleted/link hits,
and lock/unlock/navigation fences. Platform timings and raw probe evidence remain
local validation artifacts, not part of this guide.

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
source/credential selection, before building the tree. The Rclone Copies and
Cloud dropdowns filter credential names beginning with `Legacy`, ignoring case.
Hiding the selected credential resets the filter to **All**. **Settings → Workspaces →
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
[commonUtils](../../Python/commonUtils/docs/development/reference/ui/resource-providers.md#shared-item-presentation).
The mobile UI has not been migrated in this first phase.
