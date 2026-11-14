# Mobile workspace drawers and paired documents

Paths are relative to `Python/mobile/`. Use the [host owners](mobile-runtime.md#owners)
for composition and [document storage](document-storage.md#trace-a-mobile-provider-reader)
for provider lifetime.

| To change | Start with |
| --- | --- |
| Drawer, paired session or retained folder view | [Frame and drawer ownership](#frame-and-drawer-ownership), [selection policy](#selection-policy-owner) |
| Source tabs, shortcuts or folder return | [Workspaces sources](#workspaces-source-tabs), [folder ancestry](#ios-workspaces-folder-ancestry), [viewport restoration](#folder-viewport-restoration) |
| Destination stacks and Back | [Home and Documents](#home-and-documents-hub-sections), [Android Back](#android-back-policy), [reader origins](#reader-gestures-and-document-origins) |
| Rotation, fold or system bars | [Rotation](#rotation-and-display-cutouts), [native actions](#adaptive-ios-toolbar-actions), [occlusion](#system-occlusion-clearance) |
| Verify a change | [Native navigation validation](#native-navigation-validation) |

## Frame and drawer ownership

`WorkspaceNavigation` owns destination routes, drawer state and retained pane
references. `WorkspaceFrame` borrows existing widgets for compact, split or
folded presentation and returns them to their owners when membership changes.
Reuse the source tree, editor and browser to preserve input, scroll and focus.
The layout signature includes height for stacked folds; routine keyboard and
search height changes leave other panes mounted. `FileDrawer` owns selected
folder, provider, credential generation and listing. Unmount preserves its
state. Nested pickers retain independent drawers and explicit return edges.
See [listing admission](mobile-runtime.md#folder-listing-ownership).

Transient return selection is opt-in. File browser and tree widgets register
`_clear_return_selection`. `MobileRoutes.trim` records the returned panel and
`render` clears after mounting. Native folder pops and Documents detail use
the same policy. Keep search, folder and scroll, and preserve persistent
chapter, note/page, conversation and Settings selection. A successful folder
open moves the source highlight; failure leaves it in place. Returning to
Workspaces clears that highlight. Composite selection rows use
`appearance.selection_row` for contrast and accessible selected state.

A selected cloud download retires the completed destination picker before
showing progress so Back restores the retained source folder. Test the handoff
with `test_remote_downloads.py` and `test_transfer_feedback.py`.

## Selection policy owner

`workspace_policy.WorkspaceSelection` resolves editable sessions, pins, focus
swaps and pair-picker eligibility independently of native toolkits. Keep the
`pinned` compatibility property. The pane host mounts existing views; it owns
geometry and toolbar projection. Open beside requires supported sessions and at
least 640 usable units. Refresh offers on resize and validate again when invoked.

## Workspaces source tabs

`WorkspacesScreen` retains Local, Cloud and Home Server. `folder_hub.source_choices`
groups copies by remote ownership and retains the logical entry for actions.
Local taps prefer the device copy. Cloud prefers the mapped remote.
Direct SMB belongs to Home Server; imported ZIP remotes, including SMB, belong
to Cloud. Known locked sources remain visible using retained package metadata.
Changing source resets credential filtering to All. Cloud exposes Rclone Remotes
and gives transfer feedback priority over setup; Home Server offers Add share
when unconfigured. Local keeps separate Rclone Copies and On My Phone or On My
Tablet trees. Keep technical filter keys and disk paths when changing captions.

`local_sources.PhoneFiles` browses registered public Documents on iOS and the
dedicated Files root on Android. It hides and protects managed entries.
`CollectionFiles` retains managed copies. Encrypted copies use the scoped
provider and shared folder/lock artwork. Cold unlock initializes the shared
credential workflow and resumes the originating destination. Discovery uses
published metadata so it can refresh while a browser and transfer remain active.
See [Workspaces refresh](mobile-runtime.md#workspaces-refresh).

Read shared `CloudClient.package_records` for credential names and groups.
An individual scene's native selector can lag another scene's changes.
Use current generation and mapped connection identity at invocation. Old
vault labels seed missing group captions; persisted ZIP associations determine
later filtering. Retained session packages require the ZIP password when
reimported. Forgetting credentials removes package keys and cached references.
See [credential lifetime](configuration-and-data.md#rclone-credential-lifetime).

`folder_hub_style` supplies shared row metrics, transparent branches,
noninteractive group labels and guides. Keep stable folder IDs independent of
dash-separated parent captions. `FolderLocationHeader` shows the current
provider, lock state, Search and actions; its arrow means Up inside a provider
and Back at the entry root. Verify source partitioning and retained tree identity
with `test_folder_source_tabs.py`.

## iOS Workspaces folder ancestry

`folder_navigation.FolderNavigation` forms native ancestry after successful
listing. Identity includes provider and path. A workspace shortcut makes its
selected folder the browser entry root, whose Back returns to Workspaces.
Child folders keep intermediate parents. Reveal selects the owning Workspaces
source and builds ancestry, using a scoped provider when needed. It selects the
file without moving the reader or adding a cross-tab return edge.

iOS ordinary files and Rclone Copies use the shared guarded rename when both
roots are on one volume. Different-volume moves use verified streaming. Picker
selection stays on its captured provider even when the visible label changes.
The app's Toga picker adapter reloads native rows before selecting the current
item so the displayed LocalCrypt option and `Selection.value` agree.

`ios_workspace_columns.WorkspaceColumns` puts the retained overview beside the
folder navigation controller, keeping interactive Back confined to its detail.
Opening a document, loading panel or reader tools expands that controller across
the wrapper and hides the overview. Returning restores the existing columns and
folder route. Compact transition and teardown preserve widgets; retire native
callbacks before detaching controllers. Keep Rubicon weak owner semantics.
See `test_folder_navigation.py` and `test_ios_workspace_columns.py`.

## Folder viewport restoration

Capture location before first list. Restore List mode through the native table
offset and Tiles through its ScrollContainer. Keep the search and route context
on Back. `local_search.LocalSearch` prepares cancellable app-private SQLite
filename snapshots for ordinary LocalFiles, CollectionFiles and SharedFiles.
Refresh reruns the active desktop-style keyword/quoted-phrase query and validates
result revisions. Remote, session-only and private providers search in memory.
Navigation retires stale scans. On iOS, a missing historical app Documents path
can resolve to an existing file at the same relative location in the current
registered root. Check `test_local_search.py` for restart reuse and exclusions.

## Home and Documents hub sections

`HomeScreen` and `DocumentsHub` use `HubSections` and shared list controls.
Home shows the first visible open session and latest eligible Recent entry,
excluding identities currently open. Wide layout moves the retained overview
into a second scroll container and keeps Favourites in the main pane.
Documents mounts one collection at a time, with Libraries as the default.
Library scans start on entry. Keep the main browser separate from the menu and
revalidate credentials for retained library shortcuts. Close/Delete refreshes
the visible rows after commit. The [Notes Library guide](../../features/notes_library/development/development.md#mobile-browsing-and-document-lifecycle)
owns note navigation, scoped browsing and Search return. The
[Books & Comics guide](../../features/books/development/development.md#find-the-mobile-books--comics-panel)
owns library discovery.

`RecentDocuments` caps each window's list at ten. Ordinary and saved-credential
references can persist with an optional opened timestamp. Session-only entries
are RAM-only in ordinary history. Password-protected retained credential ZIPs
may restore encrypted Open/Recent metadata through
`features.rclone.mobile.document_lists.CredentialDocumentLists`. Its per-package,
per-window archive uses the authenticated password in native session memory.
Unlock restores references before opening contents. Lock retires readers;
forgetting credentials deletes cached lists across windows. Keep corrupt caches
for recovery and migrate old plaintext references only after encrypted publication.
See [document privacy](document-storage.md#privacy-and-lifetime).

Ordinary local files open with their source provider through `document_imports`;
explicit legacy imports remain readable. Reset → Clear cached documents uses
`cached_documents` and verifies duplicate source bytes before deleting, rechecking
live and durable edits after confirmation. Keep missing originals, unique saved
changes and drafts. Saved imports are separate from managed folders and ordinary
history; inventory deletion checks busy readers and other windows and forgets
matching import and Recent references. See [document actions](document-storage.md#document-action-matrix).

## Android Back policy

`MobileRoutes.install` wires the lifecycle-scoped AndroidX
`NavigationBack` bridge to `system_back`. Visible owners offer one local `back_action()`;
`invoke_back` serializes async actions. Match mounted content, including
ScrollContainers. Wide companion panes yield to detail. Keep separate destination
stacks; ordinary tab selection adds no tab history. An explicit cross-tab action
can carry a return edge. Non-Home roots return to retained Home, whose root
hands exit to Android. Native tab and route publication both update eligibility.
The policy follows [Android navigation principles](https://developer.android.com/guide/navigation/principles)
and [independent back stacks](https://developer.android.com/guide/navigation/backstack/multi-back-stacks).

| Visible state | Back |
| --- | --- |
| Native keyboard, modal or menu | Native dismissal |
| Compact drawer or fullscreen reader | Dismiss controls or leave fullscreen as handled by the visible owner |
| Browser or Find | Clear query, close search, then retrace folder history or return to entry parent |
| Notes or Help | Dismiss compact browser, then follow note/page history and owning route |
| Reader or editor | Dismiss search, chapter list or tools first; main surface requests guarded Close |
| Settings or Chat | Pop detail/category or dismiss compact conversation drawer; root returns Home |
| Transfer review, active details, floating speech | Cancel review; close details or hide speech controls while work/playback continues |

Failed async navigation retains browser history. Checkpoint refusal consumes
Back without popping. Explicit toolbar Back/Cancel keep their route actions.
Uninstall retires pending Back once; the feature still owns its worker drain.
Retired pop, reflow and eligibility callbacks exit without touching native UI.

For a Back change on Android, start at Workspaces → Local in a disposable
folder. Open a child folder, enter Search, then dispatch Back through
`MobileRoutes`. Run from the repository root:

```sh
python3 dev.py test mobile --exact-file mobile_build/tests/native/test_android_back.py
```

Expect search and folder return to consume separate steps, the source route to
survive tab switching, and Home to delegate root Back to Android. The native
bridge is mocked here; check IME and predictive Back cancellation on device.

## Reader gestures and document origins

Open in the selected destination and capture it before async work. Documents is
the shared session list, entered explicitly with commands such as All documents.
Reopening a live session elsewhere trims its old presentation before moving the
same view, retaining drafts and the previous tab's underlying screen.
Managed Edit/Preview share one route; toggling keeps the editor and WebView on
their session. A successful creation removes the form before capturing the
reader's origin; failure keeps it for retry. A cancelled close restores the
current mode. The [host session contract](mobile-runtime.md#session-transition-decisions)
owns save decisions and cross-tab retirement.

`document_sources.opening_status` gives loading a temporary route. Returning
from a cancelled/failed Documents load clears `in_detail` and calls
`route_changed`; retained Apple detail routes only hide destination chrome while
visible. `reader_chrome.sync_document_tabs` reasserts that ownership after
fullscreen and keyboard changes, using the incoming destination during native
selection. Main document Close handles dirty state; secondary tools pop normally.
UIKit disables interactive pop where it could bypass Close.

Fullscreen hides system chrome; only immersive comic images extend beyond
UIKit safe areas. EPUB retains its margins and a Show reading controls action.
Reapply horizontal page-swipe ownership after native navigation. The shared
motion policy skips first/same-page renders and honors Reduce Motion and E Ink.
Close, conceal and suspension release snapshots. EPUB remeasures anchors after
cancelling motion on resize, search or restoration.
Check `test_document_navigation.py`, `test_file_loading.py` and
`test_native_reader_return.py`.

## Content geometry across themes

`scroll_edges.py` keeps final-row clearance inside the scrolling viewport using
measured iOS insets or Android internal padding. Preserve native view padding
when repainting Android backgrounds. Grouped lists keep clipped pressed states
and retain native touch targets. Reset reused UIKit cell corner masks and keep
separator insets bounded. Selected rows keep readable outlines and foregrounds
in High Contrast. Chat reserves actual tab-bar overlap at the composer without
adding a second keyboard inset. Settings retains category selection independently
of Chat and the workspace routes. See the [Settings owner map](mobile-runtime.md#settings-implementation-owners).

Chat uses separate neutral drawer, selected-row, transcript, message and composer
roles. Match the native WebView backing to its HTML canvas for overscroll and
appearance changes. The top fade is noninteractive, and the header stays opaque
with native ellipsis for long titles. Keep the centered composer within the
actual pane and retain the native hamburger. See [Chat ownership](../../features/lm/development/development.md#mobile-ownership).

Settings keeps two independently scrolling panes from 640 usable units.
Widening a compact category remounts its existing controls in the root and
removes only the category route. Narrowing preserves a deliberately selected
category. Defer nested-page migration until Back reaches the category.
`test_settings_navigation.py` checks compact return, seam sizing and retained
values through rotation.

## Rotation and display cutouts

Use allocated content dimensions after system bars and insets. Compact iOS
browser views split at 640 usable points with landscape height of at least 500
points, unless an active reserved fold dictates pane placement. Android E Ink
can pair at 516 usable points. Workspaces normally divides wide space equally;
a flat foldable overview uses 40% for the source pane. Active reserved regions
override ratios. Use their local coordinates and interaction margins. Layout
clears old axis-specific dimensions before remount. Resize keeps route, drawer
state and per-window Settings category; a default wide category need not
become a portrait detail.

`fold_layout` observes hinge changes per window where supported. For the
partially open vertical Duo seam policy, convert the seam into the local
allocation. Home aligns its split to it and comics fit paired portrait pages
on either side, retaining landscape/double-page isolation. Snapshot posture on
the UI thread for worker reads. Ordinary layout covers fully open or unsupported
postures. Host checks cover dimensions, identity and injected fold regions.
See `test_fold_layout.py` and `test_workspace_navigation.py`.

### Native safe areas during rotation

Coalesce iOS container wakeups for bounds, inset and host-position changes.
Account for Home-indicator overlap remaining after container insets even when
the destination bar is vertical. The host uses the real window bounds.
Fullscreen comics and the Chat composer have their own clearance policies.
Keep app reflow deferred until UIKit finishes the native callback. Root and
leaf callbacks discard work after host retirement.

### Storage selector keyboard lifetime

Keep the destination selector mounted while it owns the native picker input
view, including temporary focus loss during listing. Filename entry can compact
the rest of the form for a short viewport. Test portrait and landscape with
`document_storage_tools --probe storage-selector`.

## Adaptive iOS toolbar actions

`ios_toolbar` maps retained Toga controls to native `UIBarButtonItem` objects
and semantic groups. Forward actions and menus to their current owners and
update enabled state without replacing unchanged groups. Root actions follow
`destination_actions`; clear stale reader items while updating the current root.
Title-only roots can hide their bar; titled detail routes keep Back.
Use the deferred Apple selection handler for both legacy Toga and modern iPad
delegate callbacks. Read the settled controller before toolbar projection.
Refresh final item titles/images at cold start and after attachment or vertical
edge changes. A visible vertical bar can require one nonanimated hide/show
per window/edge; preserve keyboard and reader-owned hidden states.

On iPad, active documents temporarily use tab-only mode with the destination
bar hidden, restoring the prior mode/sidebar on return. Android hides the
redundant compact activity bar except when mounting native reader chrome.
Bundled destination artwork comes from desktop `DestinationIcon` through
`mobile_build/build_support/generate_navigation_icons.py`. Retain
`DestinationRail.tools_menu` and the Misc glyph for nested destinations.

## System occlusion clearance

Use container-owned native items, visibility priorities, overflow and
`verticalBarCompressionBehavior` for actions. On vertical bars, allow
optional Search/drawer actions to overflow and keep navigation controls in
their native placement. Use live `additionalOverflowItems` providers.
When vertical bar APIs are present, each navigation controller stays in
its tab and the unused outer navigation controller leaves the window hierarchy
so tab and document bars can coordinate. Restore toolkit ownership on disposal.
Follow [Apple bar guidance](https://developer.apple.com/videos/play/tech-talks/111462/?time=120)
and the [iPhone Duo design guidelines](https://developer.apple.com/design/human-interface-guidelines/designing-for-iphone-duo).

Custom content uses the [UIKit reserved-region API](https://developer.apple.com/documentation/uikit/uiview/reservedregion)
in local coordinates. `control_top_clearance` considers every intersecting
region. Reclaim inset only for a measured free column. Track window position and
bar edge as well as dimensions. Native prompts and titles retain their space.
Home measures whether Open, New and conditional Unlock fit; Unlock falls back to
the native bar when required.

`reader_top_band` can project the existing storage title and all native actions
beside a tall edge reservation if measured space and touch targets fit. Keep
full-width reading below the cluster. Fall back to the native bar for missing,
centered, short or insufficient geometry. Restore title/control ownership on
rotation, fullscreen, prompts or route changes. A simple vertical-reader title
row still identifies the file and storage above reading content. Older systems
use safe insets. Image background extension behind vertical bars stays separate
from interactive page, footer and header geometry.

## Offline documentation wiki

`documentation_ui` mounts commonUtils' `MarkdownWikiView` over bundled
`mobile/help/docs` at the mobile guide. Share the parser with editor previews
and assistant messages. Render HTML inert and allow bundled local links and
heading navigation through the wiki. Use the [documentation hierarchy](../documentation/documentation-hierarchy.md#mobile-packaging)
for packaging and owner rules.

Give the wiki the measured Settings content width. Its 260-point sidebar,
448-point minimum article width and 12-point gap apply after wiki margins.
Narrower layouts expose a browse toggle. Search and expansion survive page
changes. Notes and Help put navigation controls on the article side when wide
and above the active pane when compact. Reparent the retained toolbar without
replacing the WebView or speech owner. Verify with `test_documentation_ui.py`.

## Native navigation validation

Use synthetic local and LocalCrypt fixtures on owned disposable profiles. Check
native IME dismissal, Android predictive cancellation, Save/Discard/Cancel,
iOS edge gestures, storage changes, and return to the same folder/search/scroll.
Check compact bar and rail, both landscape edges, cold entry and repeated
rotation. The release suite's `native_rotation_safe_areas` gate checks retained
route identity and native fixed controls; see [mobile tooling](../build-release/mobile-handbook.md).
Physical touch, VoiceOver, minimum supported iOS, live providers and actual
two-app Split View require their own evidence. Exercise repeated notebook entry
in right-hand Split View while media activity changes, capturing control and
reservation frames in the same window coordinates.

### Verify native shell clearance

With a simulator app build, run from the repository root and use a fresh
ignored output directory:

```sh
mobile_build/.venv/bin/python -m mobile_build.validation.toolbar_conventions_tools \
  --app "/absolute/path/to/Logistics Mobile.app" --output test-results/adaptive-shell \
  --family "iPhone Duo" --adaptive-shell
```

The driver uses a disposable silent media app to check measured system
reservations at idle, playing and stopped. Expect reachable controls with safe
frames as reservations grow and shrink at unchanged window dimensions. Inspect
clipping ancestors when UIKit compresses the bar. Add `--static-shell` for the
layout inventory without external activity. `--system-occlusions --sweep` checks
synthetic reservations. Keep apps, devices and compiler scratch under the
existing managed lifecycle.
