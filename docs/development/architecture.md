# Application architecture

[Developer index](development.md)

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

The generic `desktop` package owns only application-level presentation:

- Main window / tab host.
- Generic Folders page.
- Generic Servers page.
- Generic Debug page.
- Generic workflow dispatch.
- Shared UI primitives that are not feature-specific.

## Startup and refresh

`Python/mobile` is a separate Toga entry point packaged from curated
sources under `mobile_build/`. It uses portable commonUtils persistence without loading
desktop feature discovery or the Qt facade. Its storage, native import boundaries
and runtime/build gates are described in [mobile preparation](mobile-preparation.md).

The root platform launcher reads `launch_config.ini`, synchronizes the pinned
Python environment and invokes `Python/launch.py`. Startup creates QApplication,
starts the shared indexing participant, applies the theme, loads feature preferences, registers
and initializes enabled features, constructs MainWindow and enters the Qt event loop.

`MainWindow` hosts File Browser, Workspaces, Settings and Debug as core destinations,
then adds declared feature pages. Documents and Workspace actions register shared
hosts, so readers and process jobs can outlive their originating browser pane.
Bulk Rename has one retained application page. `models/` carries folder identities;
`services/` owns discovery, software provisioning, safety policy and indexing lifecycle.

`Python/launch.py` owns the application startup sequence. Qt is created before
feature initialization so startup failures can display their error dialogs.

`desktop.landing.LandingPage` is the initial launch chooser, outside the destination
tab host. Full hub reveals the existing rail; File Browser, Git (`git.workspace`)
and IDE (`ide.workspace`) reuse their pages with the rail hidden. This is a
presentation mode, not a reduced feature-loading or worker lifecycle: all enabled
pages still initialize and participate in safe closing. Launch choice is per window
and is not persisted. Registry refresh updates chooser availability and returns
to the chooser if the selected standalone feature is disabled.

The chooser's Read & edit grid uses the rail's registered document-launcher
snapshot, including the core Markdown launcher. Cards dispatch Open/New callbacks
with `DocumentsPage` as parent; they do not construct editors or readers themselves.
Registry refresh rebuilds the grid when launcher metadata changes. Successful
opens reveal the shared document host with the sidebar by default (the shared
Menus launch preference can disable it); cancellation leaves the
chooser visible. Documents opened from the chooser become the return destination
for the settings menu. The chooser scrolls vertically at compact window heights.
Before its first paint, the chooser polishes child widgets and settles card
height-for-width layouts. The same complete pass handles deferred font and
resize updates: changing fixed card heights alone can paint overlapping rows before
the grid receives its next layout request. Dirty layouts are also settled in
`paintEvent` before children paint, invalidating parent size hints and comparing
positions as well as sizes. Only this chooser's layout requests are flushed under
the reentrancy guard; startup does not process arbitrary application events and
idle layout work stops when the geometry settles. Workspace buttons and document
frames share palette-based hover feedback; document frames retain separate New/Open
actions. `test_landing_appearance.py` checks first-paint positions around the column
breakpoint, every painted row after delayed font/width changes, idle settling, and
rendered hover colors in light and dark themes.
Deferred resize updates reuse an unchanged card grid
instead of rebuilding it, avoiding a second visible layout during startup.

`LaunchSurface` parents an opaque, 36-pixel settings icon above the central stack,
positions it on resize, and raises it when revealing content. It is visible on the
chooser and in sidebar-free views, including Settings and hosted documents/jobs.
Clicking anywhere on the icon opens its menu, which offers Settings, returns to
the retained tool/documents, reveals documents, shows the chooser, or enters the full hub.
The chooser has no document menu context; revealed workspaces use normal menu
routing and retain their existing document/job ownership.

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
`services.folders.sources.discover_folder_sources()` in a worker to read each source
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
`commonUtils.ui.tasks.operation_progress.OperationProgress` for progress/cancellation
controls and `commonUtils.ui.tasks.operations.Operation` for simpler background callbacks.
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

[Application configuration](../user/configuration.md) describes resource roots and
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
`features/books/ui/bookmarks.py`. Their containing pages retain presentation and
public command compatibility.

## Application notifications

Bottom status footers use commonUtils' `ui.appearance.status_line.StatusLine`,
shared with File Browser indexing. It preserves full messages while displaying a
compact, muted UI-font line. Native reader/editor bars use `style_status_bar`.
Logistics tools retain their own status semantics, progress/cancel controls and
error recovery; only presentation is shared. Settings reset notices are bounded
above the content splitter and do not consume its stretch allocation.

`desktop.notifications.notification_service()` retains a bounded NotificationCenter
for the QApplication. Features publish Notice events through `notify`, with source,
ID, title, plain-text message, outcome, optional details action and native delivery
preference. Stable IDs deduplicate an event; acknowledgement clears unread state.
The main window owns a shared Toast presenter. Workspace actions retains its result
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
Repository panes are embedded `QMainWindow` instances with a central content
widget and a non-native source menu bar. `features/git/ui/menus.py` shares toolbar
and overflow actions with File/Edit/View/Repository/Actions menus and dispatches
text editing to the focused field. The existing workspace router publishes the
active pane's menus in the macOS system bar or a detached window header;
attached Windows/Linux panes keep their own menu bar. Selection and job-state
guards apply to menu commands as well as the existing controls.

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

The main window resolves menu context from the selected destination's active
workspace view (or the page itself for QMainWindow pages). Its
`workspace_menu_document` callback supplies that context to commonUtils' menu
router during deferred focus/activation refreshes, so hidden document workspaces
cannot restore stale menus over a newly selected destination. The shared router
owns native binding and detached-container menu refresh.
Document workspace tab activation also explicitly refreshes the main window's
menu context; the shared router observes native focus-window changes after popups
close, even when widget focus and main-window activation stay unchanged.
The launcher/+ regression also inspects AppKit menu commands under Cocoa. These
checks verify native command routing, not the menu bar drawn by macOS; visible
refresh must also be checked while alternating docked document tabs without
opening the menu bar.
The Cocoa router invalidates the visible native bar after publishing a changed
menu context or returning to the foreground. This addresses the separate AppKit
display refresh failure observed while docked Markdown/Text Editor tabs switched
correctly internally. The redraw applies only to the focused host; see commonUtils'
workspace guide for the native visibility lifecycle.

## Multiple application instances and shared indexing

`launch.main()` initializes Qt and starts `services.folders.ui.indexing.IndexService` before
feature initialization. Every process runs a low-priority participant in the shared
commonUtils index coordinator. There is no application-wide launch lock. The
service also runs when no browser subscribes, so another open process can finish
work submitted by a closing/crashed instance.

Browser requests and progress live in a durable queue beside the index. The shared
library owns deduplication, writer election, checkpoint recovery and scoped reads;
Logistics owns the runner's startup/shutdown and Qt activity signal. Closing a
browser detaches its subscription. On application exit (including startup failure),
the service requests cancellation and waits for its worker to release its locks and
SQLite connections. A blocking filesystem call must return before shutdown finishes.
If all instances close, unfinished requests remain for the next launch.

The coordinator's OS lock elects one runner; the existing index writer lock still
serializes actual index mutations, including older or standalone library consumers.
Neither PID reuse nor an old heartbeat permits takeover of a live lock. Progress
notifications let idle browsers follow newly submitted work without starting an
extra scan. This recovery contract covers directory indexing, not file operations,
transfers, compression or other feature jobs.

## Startup failures

Contribution categories are validated before pages are created, so a settings
entry in a folder-source list fails with a clear feature/category error. MainWindow
tracks each successfully created page as it builds the UI. If a later constructor
fails, it requests worker shutdown and drains a Qt event loop before destroying
the window and re-raising the original error. Shared index cancellation also
handles workers that have exited before their queued GUI completion is delivered.

The macOS launcher supports the system Bash 3.2. Pause flags use portable,
case-insensitive case patterns; avoid Bash 4 lowercase parameter expansion there.

## Document chooser and navigation actions

The main window shares one Settings navigation menu between its floating control
and the destination rail; the header uses the same actions. Visibility is refreshed
before showing menus so the current page/mode is omitted. Release launch channels
are unaffected by these session-only navigation choices.

`DocumentChooser` reuses LandingPage's Read & edit cards without launch-mode controls.
DocumentsPage installs one in each empty workspace's existing docking target;
`+` presents a retained chooser tab in the requesting workspace. Registered launcher
callbacks run through `launch_document` and `creation_scope`, retaining detached
container routing and the document service owner. Successful synchronous opens
retire the chooser tab; cancelled opens keep it. Choosers refresh on feature changes.
FolderActionsPage disables document creation because its tabs belong to workflows.

## Enabled launch catalogs and responsive choosers

Page contributions with a navigation icon enroll in the host's focused launch
catalog; `launch_description` optionally overrides the feature description. The
main window resolves these declarations to retained enabled pages and updates cards
on registry notifications. Disabled entries are removed from launch cards and the
Settings category tree, while Features still exposes enable/disable controls and
retained editors still participate in close/reset handling.

`desktop.navigation.catalog` owns core Markdown plus enabled document-launcher
registrations for all document-choice surfaces. `DocumentLauncherContribution.description`
is displayed on cards. Chooser windows remain workspace-owned utility tabs; they
are excluded from document entries and counts without changing their close/detach
lifecycle. The scroll viewport sizes content up to 1440 pixels, chooses one/two/three
columns and enables ordinary vertical scrollbar/wheel navigation for long catalogs.

## Application update handoff

`services.updates` owns Logistics repository/channel policy, protected roots,
layered Updates settings and restart launchers. `desktop.updater.UpdateController`
checks on an owned worker and offers the accent-colored button only on the landing
page. Label changes resize and reposition the offer so preparation text fits.
Tests constructing windows
perform no network checks; production startup calls `start_updates()`.

Preparation validates a checksum-labelled published release and creates a private
AppData staging directory. Git installations fetch the release commit and its
pins; extracted installations use the packaged managed-file manifest. Installation
is delegated to a copied stdlib-only commonUtils transaction helper only after
Qt exits and indexing stops. Ordinary close guards handle pending documents/jobs;
a veto discards the pending update. The helper waits for process exit before
revalidation, application and launcher restart, recording failures for startup
notifications. Recovery staging is retained. A rollback failure requires manual
recovery; it never launches a partially restored installation.

The controller validates receipt object/field types before consuming them.
Malformed receipts remain available for inspection and cannot prevent startup;
valid failure receipts notify once. If update settings become invalid or change
during preparation, the completed staging directory is discarded and the current
application stays open for a later check.

Shared updater API contracts live in commonUtils `runtime/updates/README.md`.
Logistics uses release discovery; Blue Hole uses branch commit discovery and owns
its addon-specific extraction, preset resources and Deluxe overlay behavior.

Book and comic metadata editors are feature-owned top-level dialogs. Browser and
reader actions show them directly rather than registering them with the document
host; feature controllers retain their normal save, worker and shutdown lifecycle.
Reading windows continue to use the shared document host.

`desktop.fullscreen.WindowFullscreen` keeps F11 and the Logistics fullscreen menu
command scoped to the main OS window across destination changes. Its application
event filter accepts unmodified F11 at ShortcutOverride and handles KeyPress once,
avoiding ambiguity with embedded reader actions. Dialogs retain their own keys.
The existing ReaderFullscreen controller synchronizes native window state,
reader buttons and the host menu, including restoration of maximized state.

## Desktop launch and destination projection

`desktop.navigation.catalog.LaunchCatalog` builds one `LaunchSnapshot` from core
pages and present contributed pages. Landing cards, destination targets and rail
identity consume that snapshot; document choosers consume its document-launcher
map. Core Markdown remains built in, with enabled feature launchers added in
registered order. Workspace actions follow contributed destinations, preserving
the previous landing order. Absent/disabled pages are not launch targets.

Stable `git`/`ide` keys and other feature command identities remain compatible.
The shell owns widgets, menus and activation; the catalog projects declarations
rather than creating a second feature registry. Keep `DestinationRail.tools_menu`
and the Misc `tools` glyph as the reserved nested-destination fallback.
`test_document_launchers` and main-window/navigation checks
cover visibility, order, chooser routing and disabled features.
