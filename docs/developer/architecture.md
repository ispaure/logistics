# Application architecture

[Developer index](README.md)

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

## Startup and refresh

The root platform launcher reads `launch_config.ini`, synchronizes the pinned
Python environment and invokes `Python/launch.py`. Startup creates QApplication,
acquires the per-user lock, applies the theme, loads feature preferences, registers
and initializes enabled features, constructs MainWindow and enters the Qt event loop.

`MainWindow` hosts File Browser, Folder Hub, Settings and Debug as core destinations,
then adds declared feature pages. Documents and Folder Actions register shared
hosts, so readers and process jobs can outlive their originating browser pane.
Bulk Rename has one retained application page. `models/` carries folder identities;
`services/` owns discovery, software provisioning, safety policy and instance locking.

`Python/launch.py` owns the application startup sequence. Qt is created before
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

The Folders page resolves declarations on the GUI thread, then uses
`services.folder_sources.discover_folder_sources()` in a worker to read each source
provider and its folder list once per refresh. Availability detectors and action
descriptors also run in a worker; widget factories run on the GUI thread. Providers
and detectors must be noninteractive and must not create or access Qt widgets.
Refresh/selection changes discard stale results; closing cancels work and waits
for completion. Changing a source or
credential uses that snapshot. An explicit refresh reads the providers again;
there is no process-wide cache of folder listings or contribution sets. Remote
exclusions are applied before deciding which local folders are represented by
a remote. Selection restoration uses the feature and source kind as well as
the displayed label, so equal labels from different features remain distinct.

## Long-running workflows and safe closing

Shared background primitives live in commonUtils, while the feature owns inputs,
password prompts, transaction boundaries and result presentation. Use
`commonUtils.ui.operation_progress.OperationProgress` for progress/cancellation
controls and `commonUtils.ui.operations.Operation` for simpler background callbacks.
[Workflow recipes](https://github.com/ispaure/commonUtils/blob/main/ui/operation_progress.md) demonstrate both the callback contract
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

## Independent text documents

Text Editor retains one window per document through a QApplication-parented
EditorService. Browser controllers forward opens and receive saved-path events;
closing the originating browser leaves hosted documents alive. Open files reuse
an existing owner. Each EditorWindow contains a document stack and optional split
views; document tabs belong to the shared dock workspace in DocumentsPage.

The document host asks `request_document_close()` for `CloseOutcome.ACCEPTED`,
`VETOED`, or `PENDING`. An owner implementing `request_close()` distinguishes a
user's Cancel decision from asynchronous retirement. It exposes `idle` when work
stops. Plain windows retain native close vetoes; legacy `prepare_close()` can defer
closure. The host does not inspect private worker/cache fields. Save prompts,
subordinate dialogs and cancellation boundaries remain the owner's responsibility.

## Reusable presentation and persistence

- `commonUtils.ui.outline.OutlineEntry` carries ID, label, depth and opaque target.
  OutlineList and OutlineTree present Markdown headings, EPUB chapters and book
  bookmarks. The reader resolves activation; entries are not filesystem objects.
- `reader_chrome.reading_spin` and `show_reader_popup` standardize appearance
  controls and screen-bounded placement. Readers supply ranges and callbacks.
- `text_commands.wrap_selection` shares one-step, UTF-16-aware wrapping across
  code/source/formatted editors. Selection and character-format policies are explicit.
- `entry_views` shares extended selection and typed sorting. ArchiveContents keeps
  its member model and list-only view; FileBrowser keeps its filesystem/index model.
- `commonUtils.persistence.atomic_write_bytes` validates before staging and before
  publication; atomic_write_json adds serialization and optional limits/directory
  durability. Format rules, encoding, symlink policy and schemas belong to callers.
- `operations.ResultWorker` retains result/error until finished. GitWorker supplies
  cancellation/redaction policy; BookTask supplies an interruption predicate.
  Operation preserves its existing callback signal; OperationProgress remains the
  owner-facing finish-safe progress API.

Git job lifecycle is in `features/git/ui/jobs.py`; EPUB bookmark commands are in
`features/books/bookmarks.py`. Their containing pages retain presentation and
public command compatibility.

## Application notifications

`ui_new.notifications.notification_service()` retains a bounded NotificationCenter
for the QApplication. Features publish Notice events through `notify`, with source,
ID, title, plain-text message, outcome, optional details action and native delivery
preference. Stable IDs deduplicate an event; acknowledgement clears unread state.
The main window owns a shared Toast presenter. Folder Actions retains its result
panes and badge, and forwards completion/native notice presentation to the service.
Archives publishes create/edit/extract/test outcomes through the same service.
Cancellation is distinct from failure. Native delivery is optional; retained
results do not depend on a system notification service. Widget-bound details
callbacks are weak and checked for a live Qt owner.

Notifications are passive results. Password prompts, destructive confirmations
and save/discard/cancel decisions remain feature-owned dialogs.

## Repository and document workspaces

Git follows the same pane ownership model: `GitPage` retains repository panes in
the shared `Workspace`; `RepositoryView` owns each repository's toolbar, draft,
preview, log and sequential job owner. Horizontal tab drags reorder; dragging out
detaches the existing pane. Qt toolbar actions remain available in overflow menus
on narrow panes. Switching tabs does not discard drafts or move command targets.

The Documents icon stays visible in the scrollable icon rail, even when no
files are open. It toggles a Qt popup overlay with editor buttons and a grouped
document tree; opening the overlay does not change the active workspace page. Features contribute `DocumentLauncherContribution` entries with
a stable editor ID, title, icon, lazy opener and optional new-document callback.
The optional callback enables the shared New/Open menu; readers use Open directly. Their windows declare
`document_editor_id` and `document_editor_name`; the rail groups retained windows
by that ID and reveals the original window/buffer when selected. Closed documents
retire their rows; detached documents retain a Bring back action. Bulk Rename is
a persistent utility entry outside the document hierarchy. Archive readers use
retained document windows, with independent sessions per archive.

Floating workspace docks use regular Qt Window flags, native borders and
minimize/maximize controls, rather than tool-window flags. The native handle has
no transient parent. Closing remains cooperative and never owns application
quit; dragging the inner tab header or double-clicking it restores docking.
The OS controls snapping/taskbar presentation; macOS groups application windows
under the Logistics Dock icon.

## Single application instance

`launch.main()` initializes Qt, then acquires a per-user QLockFile in the shared
commonUtils Temp directory before initializing features or constructing a window.
The lock path is shared across checkouts. Duplicate launches use commonUtils.ui
for an informational dialog and return exit status 0. Real lock I/O failures remain
errors. Ownership lasts through the event loop and is released in `finally`, even
when startup fails. Qt's long-lived-lock timeout is disabled, so an old live owner
is retained while dead process owners can be detected. See the
[Qt lock documentation](https://doc.qt.io/qt-6/qlockfile.html).

## Startup failures

Contribution categories are validated before pages are created, so a settings
entry in a folder-source list fails with a clear feature/category error. MainWindow
tracks each successfully created page as it builds the UI. If a later constructor
fails, it requests worker shutdown and drains a Qt event loop before destroying
the window and re-raising the original error. Shared index cancellation also
handles workers that have exited before their queued GUI completion is delivered.

The macOS launcher supports the system Bash 3.2. Pause flags use portable,
case-insensitive case patterns; avoid Bash 4 lowercase parameter expansion there.
