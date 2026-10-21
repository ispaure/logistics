# Mobile workspace drawers and paired documents

Saved local file references from iOS Documents recover after an app container
relocation: if the historical path is missing, reopening and Show in folder use
the same relative file under the currently registered Logistics Documents root.
Recovery requires an existing file and applies only to iOS application Documents
paths; unrelated missing paths keep their original identity.

## Content geometry across themes

`appearance._set_android_background` preserves native view padding whenever a
surface, high-contrast outline or original button background is installed.
Drawables can otherwise overwrite the control's content insets. Icon-and-title
buttons use a 12-unit horizontal inset on both platforms; iOS Settings reserves
32 points at the trailing edge for its overlaid disclosure. Theme and icon
refreshes retain those insets. Decorative startup and speech speed labels stay
borderless rather than acquiring outlines against tightly fitted text.

`hub_ui.document_group` owns one rounded surface per Home/Document list section.
Its rows and close buttons are transparent and borderless; inset dividers
separate complete rows, including their status text. Both native backends clip
pressed states to the group's corners. Home includes its See all action inside
the Recent group; Documents keeps independent All open, Recent and Saved groups.
`document_list` creates a group only when it has document rows. Empty-state and
search-result messages use transparent, borderless muted labels directly on the
page, including in high contrast. Home keeps its empty Recent label outside the
group containing See all. The library button uses the explicit action label
**Open Books & Comics library**.
Group construction preserves the existing document identities and callbacks.

`folder_hub_style.folder_scroll` reserves the Android tree scrollbar's native
width plus a 4-dp gap in the content layout (at least 8 dp), on the scrollbar's
layout-direction edge. The bar remains inside the viewport: changing native
inset padding alone would not reduce Toga's independently sized content width.
This applies to the workspace hierarchy, independently of native file lists.

The [mobile spacing evidence](mobile-evidence/2026-10-20-mobile-outline-spacing.json)
records the source audit, synthetic native phone/tablet checks and validation
limits. `test_workspace_surfaces.py` covers background-padding preservation and
the iOS disclosure reservation.

Native file lists use 16-unit outer group corners and inset separators. Android
clips list drawing and child selection to the group's visible extent, ending
short groups at the final row; high contrast adds a black outline with the same extent and rounded
corners. UIKit masks only the first and last cells' outer corners and clears
those masks when cells are recycled into the middle. Its empty footer is
installed after Toga publishes the initial data source, since assigning the
footer can synchronously query row counts. Every UIKit row, including the last
and single-row groups, keeps the same bounded separator inset: oversized leading
insets also shift native cell content and can hide the final entry on iPhone.
See the [native group checks and Boox
deployment](mobile-evidence/2026-10-20-rounded-file-lists.json).

## iOS Workspaces folder ancestry

Wide `WorkspaceFrame` layouts use a 16-unit gutter unless an active UIKit
reserved division supplies the actual fold and its interaction margins.
`fold_layout` queries regions in each view's coordinates, without assuming a
window midpoint or using interface orientation to infer the fold axis. Hinge
notifications coalesce resize work even when the hinge status stays unchanged.
Horizontal divisions stack panes; vertical divisions separate columns.
Restore clears axis-specific dimensions and margins before compact layout.

`pane_layout.panes` allocates the usable space. Flat Duo and Android e-ink file
browsers prefer one third for workspace navigation and two thirds for browsing,
with a 180-point preferred navigation minimum, 320-point maximum, and a
320-point browser minimum. Compact widths retain the drawer presentation.
E-ink file browsing can keep both panes from 516 usable points in portrait.
Active fold bounds override this ratio. Other paired documents retain their
balanced layout. Home/Documents sections and Settings also consume active
reserved regions. Geometry and retained-owner contracts are covered by
`test_fold_layout.py`, `test_workspace_navigation.py` and
`test_settings_navigation.py`; host tests do not establish native pose behavior.

`folder_navigation.FolderNavigation` adds a native route for each ancestor of a
successfully listed Workspaces folder. A local workspace shortcut starts its
stack at the selected folder: Back from that folder returns to the retained
Workspaces overview, and subfolders return to their parent within that workspace.
Browse All Files starts at the storage root. Other direct reveals retain their
folder ancestry.
Local, LocalCrypt, remote and full-page workspace browsers publish successful
locations with `record`; failed listings do not advance the stack. UIKit Back,
interactive pops and explicit route Back restore the ancestor location into the
retained browser owner. Before entering a child, the parent controller receives
a read-only native list from the already loaded tree, retaining search, sort,
selection and scroll state. That list remains visible throughout UIKit's Back
animation and the subsequent asynchronous refresh; Back never needs to wait for
filesystem or network access to display the parent rows.
Native file tables disable automatic content-inset adjustment because their
destination container already accounts for the navigation bar. This keeps the
parent preview and live list aligned during UIKit transitions.
Reader pops to the same folder keep its existing widgets without listing again.
Before a reader or its loading route is pushed, the host captures the visible
folder viewport. Replacing a loading route preserves that original capture.
Back restores the offset after native return and the final adaptive reflow:
UIKit can otherwise move a retained table by one row without changing its bounds
or insets. Queued restores are scoped to the returning folder route, so another
navigation action keeps its own viewport. iOS omits the browser's separate parent button; Android
keeps its existing parent and system Back policy. Embedded document drawers keep
their existing navigation policy. Home's full-page picker uses a scoped folder
stack above its opening screen, with an explicit Cancel to trim that scope.
Nested picker invocations keep separate browser owners, so cancelling the newer
picker retains the older browser beneath its reader.

Ancestor controllers hold read-only browser previews rather than empty panels.
Direct deep entry prepares parent listings asynchronously without changing the
active folder. Previously visited folders additionally retain a native snapshot
of their visible layout for the interactive transition. Back keeps this content
visible until the fresh parent listing is ready. Trimming routes cancels preview
work and releases its widgets/snapshots; credential invalidation clears private
previews and snapshots before they can be revealed.
Native folder pages put their folder title, storage subtitle, Search and folder
actions in UIKit's navigation bar, including ancestor previews. Existing buttons
are reattached from the live browser after Back restores a parent. Preview
headers are only mounted on inactive ancestors, so their disabled Search and
missing commands cannot replace the active browser toolbar.
The live buttons retain their callbacks and anchored native menus inside a single trailing custom
bar group with 48-point-wide controls. The content header has no idle action row;
it appears only for an operation status or an open search field. Home pickers
omit a source selector when only one source is available; it reappears when
additional sources can be chosen.


`document_sources.folder_action` supplies **Show in folder** only for resolvable
sources. Provider readers resolve the current provider/key at invocation and
check private-session availability. Imported local text/books retain a source
reference in memory for the current run, without changing the hashed durable
import index. Reveal selects Workspaces, builds its folder ancestry and selects
the file; it does not move the reader or create a cross-tab return edge. Sources
outside ordinary browser roots use a scoped provider.

Library imports without an original source reference reveal their stored EPUB or
CBZ copy. Reveal selects Local, Cloud or Home Server from the live source before
building the folder ancestry, so returning to Workspaces retains the correct tab.
The shared document action-menu policy orders reading, appearance, file operations,
navigation and close/delete commands consistently. iOS uses inline UIMenu sections;
Android uses popup groups with dividers on supported Android versions. Fallback
pages insert dividers between the same groups. Available commands remain format
specific. `Open beside another document` is offered only at widths of at least
640 logical pixels and for sessions supported by the editable pane host. Resize
refreshes retained menus; the picker also rejects compact invocation.

`Mobile/tests/test_folder_navigation.py` covers native ancestor controllers,
multi-level pop callbacks, guarded Back, retained reader return, Home reveal,
file selection and unsaved provider drafts. These mocked native and dummy-host
checks do not certify physical iOS gesture rendering.

## Home and Documents hub sections

`hub_ui.HubSections` retains the existing controls and moves Recent between the
compact page and a second scroll container. Home keeps its heading and Open/New
actions together, with five recent entries and a Documents link in the trailing
section. Documents keeps search and All open together; the trailing section holds
closed Recent entries, other saved text documents and library access. Open entries
are excluded from Recent, with the active session first in All open. Search updates
the retained list containers without replacing the input or changing sessions.
Saved text inventory uses cached metadata summaries and refreshes when the host
publishes a new inventory; listing it does not decode stored file contents.
Each wide section scrolls independently. Narrow layouts restore the
original section order without rebuilding sessions or changing routes.

Reflow uses the destination's measured native allocation, with a two-section
threshold of 700 points. `fold_layout.seam_fraction(..., include_open=True)`
forces and aligns the two sections in partially or fully open Duo landscape,
converting the physical center into the hub's coordinates to account for rails
and asymmetric safe areas. Each section has its own 16-point content margins,
keeping controls away from the crease. Tab rendering, viewport changes and hinge
status changes reflow retained hubs. Open reader routes keep their own layouts.

`test_hub_documents` checks section ownership, compact restoration and retained
hub reflow. The disposable `hub_landscape_probe` checks native bounds and scroll
independence in both landscape directions and portrait; its partial hinge status
is injected, so it does not certify a physical folding gesture. On 2026-10-20,
the iOS 27.1 Duo simulator passed ten hub/pose samples plus retained-control
rotation checks for both tabs. Both landscape directions aligned section edges
to the physical center within one point, with full-height independent scrolling
and controls contained within their section. The 79 focused hub, unlock,
workspace, fold and private-session tests passed.

## Native iPad tab selection

The app installs a retained `UITabBarControllerDelegate` for iPad sidebar/tab
presentation. Modern iPad tab selection can change the visible controller
without invoking Toga 0.5.7's legacy `tabBar:didSelectItem:` notification. Both
notification paths use the existing deferred, coalesced selection handler so the
Python destination, toolbar ownership and native selection agree. Toolbar rendering
uses the explicitly rendered destination while selection callbacks are still
committing the incoming tab. Reader title/action ownership is tracked per native
controller; returning to a non-reader page clears that controller's reader title,
actions and status prompt before its workspace header is restored. Home's Open
file action captures its destination before awaiting credential restoration and
abandons the open if the user navigates elsewhere during that wait.

## Managed document modes

Managed text/Markdown Edit and Preview presentations share the `editor` route in
both destination-local stacks and the native Documents secondary stack. Workspace
chrome is prepared for the visible mode before route identity is normalized.
Default Markdown opening presents Preview directly; toggling modes replaces the
retained panel content without adding a controller. One native Back/pop therefore
returns to the opening screen, while the editor buffer and preview WebView remain
owned by the same text session.

## File loading panels

`document_sources.opening_status` presents a temporary `file-loading:` route with
the filename, file icon and indeterminate loading bar. The centered filename
label can shrink within the panel's horizontal margins; long names use native
middle truncation while keeping the full label text. Reopen, provider reading,
local imports and library readers share it; nested calls in the same async task
reuse the panel. Loading does not advance the navigation generation, so provider
completion still detects Back or another navigation action during I/O.
`loading_progress` carries the active opening reporter through `asyncio.to_thread`.
Local text reads, document/book imports and library integrity reads publish
actual bytes consumed, using descriptor size or provider metadata when available.
The panel shows **Reading N%** only with a known positive total; unknown totals
show **Reading file…**. On completion of the read it switches to an indeterminate
**Preparing document…** stage for validation, decoding and first-page rendering.
Random-access PDF/archive opening and encrypted operations without byte callbacks
remain indeterminate. Reports are coalesced on the UI loop and ignored after
their opening scope closes or another scope replaces it.
The ready view replaces the loading route in `MobileRoutes.show` or the native
Documents secondary column. Failure removes the temporary route and reveals the
retained origin. Cleanup never selects a tab the user has left. Library readers
prepare their first page before presenting their view.

`Mobile/tests/test_file_loading.py` checks the panel contents and replacement
across Home, Documents and Workspaces, failure recovery and Back during loading.

## Compact Android top chrome

`logisticsmobile.navigation.install_android_navigation_appearance` hides the
redundant activity ActionBar after startup restores native chrome. Page headings
and in-page Back controls remain owned by their existing screens. Both bottom
navigation and the tablet rail use this policy. Logistics supplies its own
`DestinationRailView` subclass of Material's rail: 56 dp wide, 26 dp outline icons,
48 dp buttons, top-aligned primary destinations and bottom-aligned Settings.
Explicit 4 dp item margins leave room for the icon and 40 dp rounded selection
indicator inside each button. High contrast / E Ink draws a 1 dp black divider
along the rail's full content edge; theme refresh removes it in normal mode.
Labels remain available to accessibility and native long-press tooltips. The menu
fills the rail's actual height so the footer's touch and accessibility bounds
follow its visual placement; short windows fall back to Material's menu layout.
`navigation.create_android_destination_rail` copies the existing menu icons and
preserves item IDs. Initial tablet installation and later width transitions use
the shared adapter's normal selection/keyboard rebinding. The app
window title remains available as metadata. Reader fullscreen and keyboard
chrome snapshots therefore normally capture an already hidden activity bar.
Home uses an 8-point content top margin without an additional heading top margin.

`Mobile/tests/test_navigation_contrast.py` checks initial tablet installation,
late rail creation, and preserved selection appearance with mocked Android APIs.
`Mobile/tests/test_hub_documents.py` checks the Home heading inset. Physical Boox
layout still requires device validation.

## Android Back policy and panel audit (2026-10-18)

`logisticsmobile.routes.MobileRoutes` specializes the shared route host at
the Android dispatcher entry point. It installs the existing lifecycle-scoped
AndroidX `NavigationBack` bridge with `system_back`; explicit toolbar Back and
Cancel pop their route directly. Document routes stay within the opening
destination on both platforms. UIKit keeps the shared delegate and split handling.
The app module is included in `mobile_sources.json`.

The policy follows Android's [fixed start destination and navigation principles](https://developer.android.com/guide/navigation/principles)
and [independent destination stacks](https://developer.android.com/guide/navigation/backstack/multi-back-stacks).
Tab changes preserve local stacks without accumulating tab-selection history.
Document opening retains the selected destination and pushes above its existing
panel. Home and Workspaces no longer hand document activation to Documents.
Explicit cross-destination actions can still retain a return edge; ordinary tab
selection does not create one.
Each non-Home root returns to the retained Home root; Home's root disables the
callback and delegates exit to Android. Both native tab selection and route
rendering update callback eligibility, including Material's pre-commit selection
ordering. The existing AndroidX bridge is retained; custom predictive transition
animations are not implemented by this policy.

| Audited panel | System Back behavior |
| --- | --- |
| Home | Pop any detail; otherwise defer to Android |
| Workspaces and workspace actions | Pop detail to the retained Workspaces page, then Home |
| Local, LocalCrypt and Remote browser | Clear query, close search controls, follow bounded browser history; direct entry falls back to parent |
| Documents and ordinary text/Markdown | Close compact drawer/Find, then pop detail; keep session and draft |
| Notes Library and documentation | Close compact browse surface, retrace note/page history, then pop the owning route |
| Imported EPUB/comic | Close compact chapter list or fullscreen, then pop tools/reader to its origin |
| Provider EPUB/comic/PDF | Close visible find, chapter or PDF tools, leave fullscreen, then return to origin |
| Chat | Close compact conversation drawer; pop configuration/actions; root returns Home |
| Settings | Pop nested help/connections/storage/saved-file pages and compact category before returning Home |
| Transfer review | Cancel the comparison before popping its route; never confirm execution through Back |
| Active transfer details | Pop details while leaving work running |
| Floating speech controls | Hide controls without stopping playback |
| Native keyboard/dialog/menu | Retain native dismissal ownership |

Visibility checks walk the mounted widget tree, including ScrollContainer content,
so retained hidden owners do not consume Back from another panel. Wide companion
sidebars do not consume a detail Back. Asynchronous folder/note returns are
serialized until completion; failed browser navigation retains its history.
Checkpoint refusal consumes Back without popping or changing tabs. Returning Home
runs destination selection and route rendering, restoring body ownership and chrome.

`Mobile/tests/test_android_back.py` covers these policies with real app panels,
synthetic local files/books/PDFs, remote navigation fixtures, and a mocked Java
listener boundary. These host tests do not certify physical gestures, IME ordering
or predictive animations. The local QA emulator could not boot for this audit:
its Android 35 system image lacks the initial system image.

Validation: 101 targeted mobile host checks passed across Android Back, shared
navigation, adaptive workspaces, Settings, file workflows, documentation, Notes
Library, PDF and transfers, plus all seven mobile packaging checks. Test modules
were run in isolated processes after the combined dummy-backend runs became
unusually slow. Ruff and whitespace checks passed. The packaging omission test
now checks the missing module rather than depending on which importer is visited
first. This is targeted verification, not a completed full mobile/native suite.

## Document hub and recent sessions

Destination-tab visibility ignores retained iOS secondary routes while
`AdaptiveWorkspace.in_detail` is false. UIKit keeps these routes when Back or
**All documents** returns to the list, including in the collapsed iPhone split
controller; their presence alone must not hide the list's destination tabs.
Visible reader details and their secondary controls still hide destination tabs.
`test_document_chrome.py` covers list return and resuming the retained detail.
The [native reopening evidence](mobile-evidence/2026-10-20-reader-reopen.json)
records iPhone/iPad list-tab restoration, recovery from a deliberately blank EPUB
WebView at its saved passage, and file-browser open/close. It does not establish
what caused an intermittent blank reader on a physical device.

`HubUI.recent_items` merges the bounded recent history with visible workspace
sessions. Provider `history_source` and credential `cache_source` references map
back to live owners by source identity, so an open file appears once and its
current title and dirty status take precedence over history metadata. Unrecorded
session-only entries participate in memory without adding plaintext history.
Recent remains bounded to ten entries; the collapsed **Open · count** switcher
provides access to every visible open session with the existing guarded Close
actions. The card preference applies to Recent; the switcher always uses rows.

Recent activation resolves live owners again at press time and dispatches through
`session_opener`; closed entries use the existing reopen commands. Rendering
neither opens private contents nor unlocks credentials. Status badges distinguish
open sessions, live unsaved drafts and recovered drafts; ordinary documents have
a stored baseline even before their first explicit Save. No storage schema or
credential-list encryption changes are required. Workspaces, private-session and UX
workflow tests exercise identity deduplication, retained edits and closed-draft
recovery using the dummy native backend.

## Notes Library

`features.text_editor.notes` owns rooted containment, immediate-folder filtering,
marker detection and bounded revision-checked note reads for both desktop and
mobile. Desktop Text Editor contributes **Open Notes Library** to location
actions through `notes_actions` and hosts `ui.notes_library` in Documents.
`logisticsmobile.notes_actions` resolves the selected Local, LocalCrypt, mapped
copy or Remote scope without opening its file browser; a background root probe
adds the command to the location's Push/Pull actions page only when `.obsidian`
is a directory. Probes perform no filesystem mutations, and generation/navigation
checks discard stale results.

`logisticsmobile.obsidian` retains the native adaptive folder/page reader and
owns a transient `notes-library` Documents session. Its hamburger, history,
parent navigation and read-aloud controls stay with the reader. Closing the
library removes its session; private catalog revocation clears its tree, speech
and preview. iOS private previews use a nonpersistent WebView and Android disables
browser disk caching/storage. Private HTML above 2 MiB is refused before toolkit
loading. No plaintext staging directory is created.

Remote adapters advertise `remote_storage`; neither UI creates a search field
for them. Root detection and explicit folder expansion use immediate listings,
with no recursive enumeration, prefetch or remote search. Local name filtering
only examines loaded rows. `Mobile/tests/test_notes_library.py` and desktop
`test_notes_library_desktop.py` cover action placement, Documents ownership,
remote call bounds, containment, cancellation and credential retirement. Native
`obsidian_checks.py` covers real Local/LocalCrypt reads and action screenshots.

The shared `FolderLocationHeader` groups passive storage/lock images and labels
beneath the folder name, separate from parent navigation. That secondary line
shows `BrowserStatusLabel` messages while nonempty and restores storage identity
when cleared, preserving result/error visibility.
Main local/remote browsers and the local/library drawer browser mount the search
button in this header beside the current folder. Native single-line label
measurements retain a zero minimum width after rehinting so long folder names
and status messages truncate instead of pushing the 48-point search control
outside the viewport, including on Android. Android uses one inline row
with Back/Up, a compact folder title and storage subtitle, Search and overflow.
Subtitle and operation-status rows use native text height rather than a fixed
18-point box, so Android font padding and larger text do not clip glyphs.
Opening search temporarily replaces its caption with the input and close control
while retaining Up and overflow. iOS retains its title, subtitle and both actions
in the native bar and adds a search row only while active. Closing search removes
that row completely. Standalone pickers retain their search row.

Remote browsing mounts `cloud_up` beside `cloud_status` in the main browser,
using the same 48-point up-arrow control as local browsing. It calls the existing
`parent_cloud` handler and remains disabled during cloud operations. The advanced
actions route does not retain this control. Parent navigation walks logical paths
within the selected remote; native route Back retains its separate screen behavior.

The mobile `FileBrowser` bounds List and Tiles at 500 entries per page using the
shared browser's `page_size` property, including bounded remote browsers. Paging controls precede the rows inside
the scroll content so the bottom destination bar cannot cover Next at the end
of a listing. Row command binding uses one button-to-entry map per render,
avoiding repeated filtering and sorting for every row. Generic folder glyphs
require no image reads; the shared renderer omits empty image widgets when
thumbnails are disabled. Thumbnail loading retains its revision-aware RAM bounds.

`keyboard.py` observes outside touches without consuming control events. On iOS,
a window-local recognizer delegate ends editing outside editable text controls;
Android browser views dismiss a focused search field on outside touch-down.
Text-field touches keep normal cursor and selection behavior.

`workspace_navigation.py` owns feature-level layout inside the existing
commonUtils native tab and navigation stacks. The host retains native Back,
keyboard safe areas, immersive-reader chrome and independent window ownership.
It no longer installs the earlier Documents-only UISplitViewController. Settings
and Chat remain full-screen destinations; chat configuration is a full-screen
route in Chat.

`WorkspaceFrame` keeps each original editor/browser Box as its route view. Its
existing children move into a retained content Box, with a top-left hamburger
and a horizontal content area. Transfer banners retain their original registered
parent. Compact drawers retain the main content at its original width and insert a
browser up to 320 points/dp wide, leaving at least 64 points/dp of the page visible.
The row clips overflow. UIKit animates a snapshot of the previous row to reveal
the new layout, respecting Reduce Motion; the actual editor retains its owner.
Android uses the same retained layout without the UIKit transition. Root scroll
overviews receive a Box frame too, so their hamburger toggles in place.
On Apple, the frame moves its menu and Split control into the existing native
navigation bar, preserving Back and eliminating the extra in-content header.
The 52-point menu uses UIButtonConfiguration glass when available, with a gray
capsule fallback. Destination selection renders against its explicit destination
because native selection callbacks precede the host state commit; UIKit Back
also schedules a workspace render. At 640 points/dp, the file browser and document each receive half the
actual content width. The same measured-window rule drives Chat's conversation
list and message area; it does not infer device type from a name.

The file drawer has independent browser state over the shared bounded browser
and ResourceSelection APIs. Its roots are local files and available LocalCrypt
copies. Remote connection/mapping operations stay in the existing workspaces.
Enumeration runs in a worker, rejects superseded folder/storage results, and
serializes scheduled refreshes. Opening files uses the existing provider-session
or library import path and preserves the destination where the user opened it.
It does not modify the Workspaces tab's selected resource or reuse transfer cancellation
handles. Failed enumeration disables stale file opening.

In Documents, Split chooses another open editable text/Markdown session. The
current session becomes the left-hand pinned editor; the selected session is the
right-hand editor. Each widget has one native parent. Reparenting borrows the
existing owner rather than cloning its text, draft or callbacks. The hamburger
temporarily substitutes the file browser for the pinned editor. Narrowing keeps
the selected document and retains the other session. Closing a pinned session
clears its presentation; editor commands rebind to their actual owner and can
swap the active/pinned sides. Books and comics retain their existing reader
lifecycles and are not paired by this text-editor command.

Conversation selection uses stable conversation IDs, preserves unsent drafts,
and disables conversation switching during a request. Generation settings and
export commands remain available from Chat. No model request starts from
navigation. The conversation list represents the existing flat conversation
store; no new folder or branching persistence format is introduced.

Host coverage is in `Mobile/tests/test_workspace_navigation.py`, including
compact drawers, nested-file opening, independent drafts, two-document/browser
switches, collapse and close, and chat history/draft restoration. The native UI
review calls `workspace_checks.py` to exercise real phone/tablet content and
capture the file drawer, paired documents, conversation list, Chat and Settings.
Wide native checks assert that actual pane widths differ by at most two points.
Evidence must identify the staged source; a simulated width in a host test does
not establish native Duo fold-gesture support.

## Workspaces and file browser naming

**Workspaces** is the desktop/mobile product name for the configured-folder
destination formerly called Folder Hub. Its per-folder tools are labelled
**Workspace actions**. Keep the mobile `files` destination, `folder-options`
route, desktop `folders`/`hub` navigation keys, `FolderHubUI` class and existing
`folder_hub` modules/documentation paths stable. This is a presentation rename,
with no saved-state or storage migration. The separate document workspace APIs
continue to manage open sessions and panes.

Reader and preview menus use `mount_native_menu` to occupy the same UIKit
navigation-item slot as Documents, with native Back preserved. Android retains
the in-content control with the Documents inset. Normal reading frames participate
in measured floating-tab clearance; fullscreen comics retain zero margins. The
base inset comes from `ReadingFrame`, so repeated renders do not accumulate
bottom padding. Comic canvases flex to the current pane instead of pinning a
width measured before entering fullscreen.

The physical iPad check on 2026-10-15 used a cache-only synthetic comic and a
transient workspace session. All ten samples passed: the first fullscreen open
and repeated reopens occupied the complete 834-point safe width at x=0; normal
controls used the native Documents menu slot and left reading status 16 points
above the destination-bar boundary. The diagnostic restored ordinary startup
after cleanup. Detailed local measurements are retained in ignored
`Mobile/logs/ipad-reader-layout.json`. This does not establish the cause of the
user's original intermittent Workspaces failure.

Workspaces constructs discovery results and its replacement page before clearing
the existing root. Discovery failures show a recovery page with Refresh, local
browsing and Connections instead of an empty tab. Refresh can retry after credentials
change. Credential selectors guard transient native row indices and compute the
visible selection before clearing folder rows. Regression tests inject LocalCrypt
discovery failure during tab entry and transient credential-selection indices.

The `files` destination key remains stable for routing and session origins; its
visible name is **Workspaces**, with the desktop three-row hub glyph in navigation
and on Home. Its root lists logical folders. Selecting a row opens the preferred
available copy directly. The adjacent actions button opens `folder-options`,
where Browse Local/LocalCrypt/Remote selects an explicit copy. Pull/Push remain on the folder action page. Browser return links and the
drawer’s folder-management shortcut are labelled Workspaces. The Documents drawer offers browse roots, recent identities, discovered libraries
and creation shortcuts. Browse roots and libraries mount the independent file browser
in the main route. The Workspaces drawer implementation remains available, but its
hamburger is not mounted.


## Mobile feedback follow-up (historical, superseded by the UX passes below)

Home suppresses only its own Apple navigation bar; its bottom tab stays visible.
`hub_ui` owns padded format-launcher cards, category filters and the open-session
overview. The stored-document listing is removed. The Archives launcher selects
ZIP/CBZ/EPUB files for current readers; no general archive manager is claimed.
Bundled Qt-free glyphs are rendered from the existing desktop `DestinationIcon`
geometry. `install_folder_hub_icon` applies the hub image to Apple tabs and both
Android navigation presentations without changing commonUtils.

`folder_tree` builds every dash-separated parent level while leaves keep original
folder-choice keys. Collapsing is presentation only. The Credential selector starts
at All and uses existing ZIP-to-remote associations; filtering retains every
available copy of each matching folder. Credential changes refresh in place.
Folder options remain a destination-local route. At 640 points/dp they pair a
retained folder picker and scrollable actions, with the row split equally and no
second outer inset on the picker. Narrowing restores actions alone. Mapping-removal
commands are absent from this page; transfer and deletion contracts are unchanged.

Documents keeps the menu and main browser as separate widgets to avoid borrowing
a widget twice. Library shortcuts retain the discovery provider (including pulled
crypt namespaces) and reject changed credentials. Clearing private catalog state
invalidates drawer enumeration, clears private browser rows and rebuilds the menu.
`RecentDocuments` exposes at most ten entries in each window's private workspace.
Ordinary identities and saved-credential file references carry an optional opened
timestamp; older histories remain readable. `document_sources` excludes session-only
connections from the ordinary on-disk history, even when their credential ZIP is
retained. Session-only recent entries join the list only in RAM after authentication.

`features.rclone.mobile.document_lists.CredentialDocumentLists` saves session-only
open/recent references under `CredentialDocumentLists/<credential digest>/<window
digest>.zip`. The archive's sole member is the generic `entries.json`; user filenames
and paths occur only in its encrypted contents. Native `document_lists_seal/open`
uses the already authenticated credential ZIP's password and AES-256 ZIP encryption.
The password stays only in native session memory and is cleared when credentials
lock, clear or are replaced; neither it nor decrypted cache payloads enter a vault.
Only password-protected credential ZIPs enable caching. Connection identities are
validated when decrypting and when reopening files. Corrupt caches are preserved.

Unlocking restores metadata-only transient `credential-reference` entries in Open
documents and RAM-only Recent entries, without network reads. Selecting an entry
constructs its reader on demand. Closing removes it from the encrypted open list
and retains its recent entry. Locking/replacing credentials retires live readers
without erasing their saved open list. The cache contains no document bytes or
unsaved edits; explicit privacy-gated exports remain excluded. Files inherited
from older retained-credential plaintext history are migrated only after ciphertext
publication succeeds. Cache writes serialize with deletion; forgetting credentials
removes encrypted lists and decoded entries across windows. Credential replacement
also deletes the replaced retained package's list cache.

`SavedFilesUI` exposes retained library imports in Settings independently of the
ten recent identities and active workspace sessions. `LibraryStore.stored_files`
counts UUID archive/JSON pairs once and includes incomplete or corrupt imports;
linked or invalid identities are reported as unmeasurable. Sizes cover archive
and reading-record bytes, excluding the derived metadata index, Local/LocalCrypt
folders and remote RAM snapshots. Confirmed deletion refuses concurrent app
windows and busy library operations, closes the matching reader, forgets its
Recent identity and deletes only that UUID's archives, record and edit journal
under the publication mutation lock. Source files remain outside this operation.
Deletion also forgets matching `ResourceImports` identities so reopening a
retained source can import it again instead of targeting a removed library UUID.
Import records contain no source provenance; the inventory explicitly labels
the original source as unrecorded. Direct remote/provider sessions remain absent
from this inventory and persisted workspace/history, including after restart.

Comic reader menus and tools have no standalone ZIP relock command. Archive
password lookup/unlock is unchanged; ordinary reader closure releases its source,
password and decoded pages. This does not change rclone crypt credential lifecycle.

Imported `ReaderChrome` selects menu/tools content from the session's format;
provider readers use the opened reader's EPUB/comic capabilities and read-only
flag. Comics expose no text appearance, speech, chapter search or bookmark UI.
`ReaderAppearance(kind=...)` constructs either EPUB typography or comic layout;
its `settings()` returns only that format's preference changes. Provider comic
tools omit disabled text-save/discard actions. Page sliders, direct page selection,
fit, reading mode and supported metadata/neighbor actions remain available.
`reader_controls.COMIC_COMMANDS` is the single ordered comic-menu definition.
Imported and provider controllers supply callbacks to `comic_actions`; unsupported
capabilities are omitted. Both use `comic_pages` for their page-selection screen
and the same comic `ReaderAppearance`. Provider storage adapters do not define
separate comic menus. EPUB and text/image commands remain format-owned.

`ComicHeader` is shared by imported and provider comics: existing browser navigation,
48-point previous/next-file icons and overflow. Native SF Symbols/Android vectors
distinguish file skip from the footer's single page arrows. `COMIC_COMMANDS` keeps
only page selection, appearance, reading mode, fit, supported metadata and close;
navigation and first/last-page duplicates are omitted. Imported boundaries disable
file buttons; unavailable provider file navigation disables them. The header guards
overlapping taps, and adjacent-file handlers preserve fullscreen/control visibility.
Provider comic status/page numbers sit beneath the footer and hide with controls.
Folder-backed providers enumerate neighboring comics on a worker to set file-button
boundaries. Imported reader titles identify the opened comic instead of the generic
Books & Comics page. iPhone simulator review used a separate app identity and
synthetic comic; ten fullscreen/controls/reopen captures passed the native layout
diagnostic. That diagnostic now centers against the actual viewport and separately
requires fullscreen viewport origin/height to match the window; hidden chrome
does not leave safe-area padding. Android icon/layout behavior remains host-tested.
The shared comic menu includes `Info…`. Imported readers resolve their current
library UUID archive; provider readers format remote name/key, a logical LocalCrypt
location or the opened local file. This is an on-demand dialog without config
reads, source-provenance guesses or new persistence. Unavailable private sessions
cannot show their path.

Chat reserves the actual overlap between the native tab bar and the content
viewport. This handles floating bars extending above UIKit's reported bottom safe
inset, both before and after keyboard layout. It does not add a second keyboard
inset. The native workspace checks cover Workspaces pane widths and composer
clearance in addition to retained editor ownership.

Validation: 183 mobile host tests and 52 portable mobile tests (three expected
platform skips), plus lint and whitespace checks. Targeted native probes used the
existing simulator executable with the current Python UI sources: iPhone category
cards, folder nesting/collapse/credential filtering, matching library shortcuts,
and composer bounds/hit testing with keyboard and six-line drafts; wide iPad
Workspaces panes measured 405/405 points and met at x=417 in an 834-point window.
These are targeted local checks, not full native-suite, Android-rendering,
physical-device or Duo fold-transition evidence. Probe sources, screenshots,
results and source hashes are retained under `Mobile/logs/feedback-review/`.


## iPhone tab labels at cold start

After installing the app-owned Workspaces glyph, `navigation.refresh_apple_tab_items`
creates a fresh `UITabBarItem` for each wrapped navigation controller, using the
final destination title and image, then refreshes the native tab array. This avoids
reusing the original OptionContainer items' compressed label geometry on iOS 26.
The change does not select destinations, initialize Chat or change the route stacks.
No private UIKit label classes or frame writes are used by the application.

An iOS 26.5 cold-start probe reproduced Workspaces at 24.3 points wide despite a
55.3-point intrinsic width; selecting it repaired the label. With fresh items, all
five labels fit before any selection, and their heights increase from the clipped
7–8 points to 12 points. Cold-start label checks passed on iOS 26.5 and 27.0.
Native suite startup now inspects rendered iPhone label bounds before it exercises
navigation, and host coverage verifies titles, glyphs and selection preservation.
The iPad's hidden legacy tab labels are excluded from the phone-only pixel check;
its visible native tab/sidebar presentation is checked separately. Local captures
and measurements live in `Mobile/logs/tab-label-review/`.


Validation for this fix: 185 mobile host tests passed, including startup from the
staged payload and title/image/selection preservation. Targeted native probes
passed phone cold-start bounds on iOS 26.5 and 27.0 and iPad tab/sidebar selection.
The signed update was installed in place on the paired iPhone; a physical-device
capture showed all five complete labels. That capture was on Documents, so the
before-selection assertion specifically comes from the cold-launch simulator
probes, not the physical screenshot. Lint and whitespace checks passed.


## Credential retention and compact interaction follow-up

Credential group labels come from the persisted ZIP-to-remote associations and
are seeded from the protected vault label when restoring older saved credentials.
Known but locked remotes stay available in Workspaces. Action entry points check
that a remote is loaded and, for mapped folders, matches its connection identity.
Session imports retain the original ZIP via CredentialPackages: AES-256-GCM in
the native bridge, a separate device-protected key, identity-bound authenticated
data and bounded ciphertext/index files. ZIP passwords and decoded configuration
are not stored in this cache. Unlocking imports the retained ZIP as session-only,
checks the connection identity, then resumes the requested action. Existing
session imports without a retained archive need one fresh selection. Forgetting
credentials destroys the cache key before removing the retained files.

Documents groups open sessions by format, ahead of recent closed documents. New/Open commands use a compact toolbar rather than tool cards. Private provider
sessions remain transient; recent history separately admits eligible reopen references.
Workspace saving also checks that provider allowlist independently of the transient
flag. PrivateSessions records the opening client/generation; Home, document cards
and activation reject locked or superseded private sessions without consulting the
bridge during rendering. Private previews remain memory-only. Explicit ordinary
local downloads/imports retain their existing local-file semantics.

Drawer taps render cached menu contents immediately, defer credential/provider
queries to a worker, and do not checkpoint an editor just to reveal its menu.
Workspaces takes unlocked remote names and credential groups from the shared
`CloudClient.package_records` snapshot rather than a scene's native selector.
An empty selector cannot hide another iPad scene's loaded package; an empty shared
snapshot cannot revive stale unlocked names. Rendering this list does not call
the native bridge or probe online services.
Credential-change notifications refresh a visible hub after stale private readers
are retired. Source/filter changes also reread the local discovery snapshot.
ZIP filter labels omit the archive suffix and use numbered collision labels.
Preparing a retained view invalidates the layout cache; every render rebinds its
native header. Connection-query failures are reported without stranding the next
refresh. The initial Chat selection mounts its lazy root without calling
Routes.show/host.activate from inside the native selection callback.

The app-owned UIButton subclass limits plain text buttons horizontally to their
public title/image rectangles and preserves vertical touch clearance. Visible
list rows, bounded glass buttons and compact icon controls keep their native
bounds. Actions fire on release inside, allowing ordinary scroll cancellation.

Validation: 191 mobile host tests; 53 portable mobile tests with three expected
platform skips; native bridge Go tests; lint and whitespace checks. Targeted iOS
26.5 simulator probes verified first Chat selection, 20 drawer toggles, a 402-point
plain button rejecting blank-edge hits and accepting its text center, Credential
label spacing and an opened Markdown document nested beneath its launcher actions.
Sources/screenshots/results are in the ignored Mobile/logs/credential-followup/
folder. These targeted checks do not constitute a full Android or native-suite run.

## Native first-selection ordering

`install_apple_selection` replaces the iOS OptionContainer selection handler with
an app-owned queued handler. Toga 0.5.7's `tabBar:didSelectItem:` may run before
UIKit updates `selectedViewController`; reading current_tab inside that signal
can therefore rebuild the previous destination. The queued handler reads the
settled selection, lets the host commit state, lays out the native controller,
and reflows the workspace/header. Programmatic selections remain synchronous;
their guarded signals cancel stale queued user events. This keeps the shared
commonUtils adapter unchanged.

The targeted iOS probe signals the native item before changing selectedIndex,
then verifies the first Documents frame, toolbar target and drawer action.
This covers event ordering that programmatic `current_tab` tests missed.


## Folder viewport restoration

Local workspace shortcuts initialize the file browser at the requested storage
and path, without first listing the device root. Folder navigation captures and
restores scroll position through the browser's viewport adapter: List mode uses
the native table's content offset and Tiles uses its ScrollContainer. The outer
browser Box is only a layout container; treating it as a ScrollContainer raises
an exception when navigating away from an already displayed folder on iOS.

## LocalCrypt picker identity on iOS

The pinned Toga backend did not reload UIPickerView's row count before selecting
an item in a replaced source. Its text field could display LocalCrypt while
`Selection.value` still returned the first row, Local files. The app-owned
appearance adapter now reloads the picker immediately before native select_item,
keeping the displayed label and provider identity aligned. Private-open failures
are also copied to the visible browser status. Native LocalCrypt coverage opens a
synthetic encrypted CBZ through a fresh scoped browser and verifies its first page;
it does not import plaintext into the ordinary library or document store.


INI support is separately enabled in the private memory reader, stream-to-text
path, text chooser and native encrypted-write extension check. The 1 MiB text
limit and lossless TextSession encoding/line-ending behavior are unchanged.
The portable smoke fixture allowlist includes the new INI regression.

Validation: 213 mobile host tests; 54 portable tests with three expected platform
skips; native bridge Go tests including encrypted INI round-trip; lint/whitespace
checks. The targeted iOS 26.5 probe opened a real encrypted fixture CBZ through
CryptFiles/ManagedCopies, verified its decoded first image and correct storage
selection, then opened an INI in the private text view. Native INI saving is
covered by the Go round-trip and host UI save tests; the targeted simulator used
its existing executable for the open/display checks. Source/results/screenshots
are retained in ignored `Mobile/logs/localcrypt-open-review/`. Android rendering
and a full native suite were not exercised in this follow-up.


ManagedCopies retries a native archive unlock that requires configuration by
calling CryptFiles.archive_password. That provider walks logical ancestors only
within its root, reads each virtual remoteConfig.ini with a 64 KiB bound and
uses services.documents.zip_passwords.password_from_ini for the desktop inheritance policy.
Plain archives do not require configuration reads. Explicit input is not silently
overridden. Parsing errors are sanitized and resolved values are never copied to
preferences, workspace history or diagnostics. A native fixture verifies this
path on a protected archive without an interactive entry step.

The iOS-only `show_legacy` preference defaults to false. FolderHubUI owns a
session override; the Settings switch refreshes retained browsers, the hub and
library shortcuts immediately without writing preferences. Explicit save
persists it; reload discards the override. FileBrowser filters logical directory
components before pagination, including search results and provider remote roots,
so LocalCrypt uses decoded names. The filter changes presentation only.

Credential group and retained-ZIP chooser labels share the iOS session visibility
policy, matching the `Legacy` prefix without requiring a dash. Filter presentation
without modifying package associations or retained credential data. When a selected
credential becomes hidden, both the selection and its retained name reset to All.


## Task-focused presentation (local UX passes, 2026-10-15)

`HubUI` renders visible open sessions before eligible recent identities. Recent
reopening uses the existing checkpoint and reader/editor activation contracts;
session-only references stay out of plaintext history and private content previews remain excluded. Card grids reflow to one,
two or three columns, including spacers for an incomplete row. Home reflows
Recent and Your spaces independently of the document grids.

Folder row activation enters the existing guarded browser directly. Its adjacent
action button retains the explicit copy/transfer route. Preparing this route
without presenting it provides a status and credential-resume owner; failed
browsing with a status can present the action route. No transient action screen
is added to the successful browse Back stack.

`appearance.reserve_navigation` applies measured floating UIKit tab-bar overlap
to the active ordinary view, preserving its original bottom margin. It runs from
workspace rendering and skips Chat and reading frames because those own their
clearance/chrome. It subtracts the container's existing safe-area inset before
measuring overlap. Split bar items are mounted only when a wide editable
workspace can use them. FileDrawer has one parent-folder control and a breadcrumb;
the inherited browser-history Back button remains available to code but is not
mounted in Local/LocalCrypt or Remote browsing. Native route Back stays intact.

Editor status comes from the document owner: durable recovery, source save,
session-only draft and conflict are distinct. A conflict exposes the existing
Save a copy command through `ActionMenu`, preserving owner rebinding and close
guards. No save, transfer, credential or persistence contract was changed.

Android retained destination roots are explicitly sized from the outer native
allocation, subtracting rail width when present. Measuring the child content
view instead is self-referential and can shrink the workspace on repeated
layouts. A host regression covers repeated renders and rail allocation; the
native phone probe checks 411 logical points of body width against the 411-point
window. Android's action bar follows the same light/dark surface palette.

## Partially open Duo seam layout

`logisticsmobile.fold_layout` observes `UIHingeInteraction` on each host window
when available (iOS 27.1+), retaining its update block and interaction. Status 2
activates the seam policy; fully open, unknown/unavailable and horizontal-fold
orientations use ordinary layout. Coordinates come from the window midpoint
converted into the actual widget allocation, so asymmetric safe areas and the
native rail do not shift the seam. The SDK headers are the API contract source;
older iOS versions skip interaction installation.

Home applies that coordinate to both action and content rows. Imported and
provider comic loaders select paired portraits in this mode, while preserving
landscape and explicit double-page isolation. RAM-only composition fits each
portrait within its own side and places the inner edges at a zero-width join;
a lone page remains on its reading side. Normal composition keeps its existing
gutter. Layout watchers compare posture/seam as well as viewport dimensions and
wait for fit zoom before rebuilding. Provider worker loads use a main-thread
snapshot of the layout mode and never read UIKit hinge geometry on a worker.

`Mobile/tests/test_fold_layout.py` covers rail offsets, status/orientation fallback,
unequal aspect ratios, unpaired manga and landscape isolation. The cache-only
`fold_seam_probe` records native Home joins and a real composed comic; its partial
status is injected explicitly when the simulator is flat, so it does not claim
to verify a physical fold gesture.

Local iOS 27.1 Duo verification observed native partial status 2 in the inner
display's landscape orientation (UIInterfaceOrientation 4). Both Home joins
measured 475 points against the 475.5-point window center (native layout rounding);
the composed comic join measured exactly 475.5. The separate probe used cache-only
fixtures and an existing SDK 27.1 executable with refreshed Python sources.
The 315-test mobile suite passed 312 checks inside the sandbox; the three blocked
localhost fixture checks passed on a network-enabled rerun. A focused 76-test
navigation/reader run passed, as did the final bitmap refinement tests. Evidence:
[fold seam geometry](mobile-evidence/2026-10-15-duo-fold-seam.json).

## Fullscreen reader system chrome

`ReadingFrame` marks all immersive readers with `_reader_fullscreen` and only comic
images with `_comic_fullscreen`. The shared navigation chrome hides bars on both
platforms; only comic images extend beyond UIKit safe areas. EPUB text keeps its
normal margins and a 48-point Show reading controls action. Transfer banners stay
hidden during either immersive mode without pausing transfers.

`ios_reader_chrome` installs a pinned-backend outer navigation-controller subclass
before window construction. A weak window-to-host map scopes status-bar preferences
to the owning workspace. The Apple content-layout adapter restores measured safe
areas normally and clears image insets during immersive comics. It does not change
the spread scale algorithm, reading direction, private storage or credential policy.

The isolated Duo simulator check passed comic fullscreen → controls → fullscreen
transitions at the full 951-point window width, with status-bar restoration.
Imported EPUB fullscreen retained 16-point outer margins and its restore action.
The check uses only synthetic cache fixtures and an injected partial posture;
see [local reader evidence](mobile-evidence/2026-10-15-reader-fullscreen-duo.json).

The same isolated check passed on a regular iPhone 17 Pro at 402 points,
including EPUB margins, restore controls and status-bar restoration;
see [regular iPhone evidence](mobile-evidence/2026-10-15-reader-fullscreen-iphone.json).
Android uses the existing shared immersive-bar implementation; these iOS reports
do not claim native Android gesture verification.

## Chat presentation

Chat uses dedicated neutral palette roles for its drawer, selected conversation,
reading pane and composer on iOS and Android. The shared `surface` helper accepts
background/foreground roles and optional outlines; registered surfaces are repainted
on theme changes and retain Android e-ink overrides. UIKit colours remain dynamic.
The drawer places New chat and settings beneath its scrollable history; selected
rows use a rounded fill rather than a title prefix. Export remains in the header
actions menu. Hamburger mounting and compact/wide pane ownership are unchanged.

Validation: 36 focused chat, appearance and workspace checks plus six transcript
presentation checks passed. An isolated UIKit preview verified compact iPhone
and wide Duo layouts, native menu ownership and rounded composer rendering.
Android uses the shared layout and its native surface painter; this change has
not yet been visually verified on an Android device.

The main transcript uses `chat_background` and a separate `chat_bubble` role.
Completed message role labels remain available to accessibility without visible
headings; partial/recovered message status stays visible. The native composer
shares one rounded surface with its growing input and circular Send/Stop icon.
Icon controls retain accessible action names and Android disabled/tint states.
The header groups New conversation and More without moving the native hamburger.

A compact UIKit preview verified the main transcript, unified composer and
generation Stop icon against synthetic offline messages, with the native
hamburger still mounted in its original navigation slot.

Chat's native WebView backing and HTML root use the same dynamic
`chat_background` role as its body, covering load and overscroll areas. A live
UIKit light → dark switch verified computed transcript backgrounds of white
and black respectively without replacing the conversation; paired screenshots
were captured from the same running preview. Thirteen focused appearance and
transcript checks passed.

## Chat top fade and large-screen geometry

The transcript's fixed, noninteractive top gradient fades scrolling messages
into the active canvas colour. The header remains fully opaque. Chat alone
uses a matching UIKit navigation appearance and root background, refreshed
with system appearance; other destination bars retain their existing styling.
The native hamburger stays in its existing navigation slot.

Header labels use a single line with native ellipsis and measured bounds so
long conversation/model names cannot push the action capsule out of its safe
area. Composer and status margins center a roughly 780-point maximum reading
width when a pane is wide, while split panes retain their existing allocation.

Local validation passed 37 chat/appearance/workspace checks and six transcript
checks. An isolated preview with valid synthetic domain messages passed 16
configurations across iPad and Duo: portrait/landscape, light/dark, and drawer
open/closed. Native assertions verified action bounds, centered composer width,
bottom containment, noninteractive fade, and unchanged hamburger ownership.
See [native measurements](mobile-evidence/2026-10-16-chat-wide-layout.json).
These are simulator results, not physical fold/keyboard interaction evidence.


## Workspaces source tabs

Workspaces and `FileBrowser` list mode share `folder_hub_style.folder_row` and
`folder_name`: 48-point rows, regular 15-point titles, four-point spacing,
24-point accent icons in a 36-point slot, and borderless rounded row surfaces.
The landing page's outer branch containers are transparent; indentation and
branch guides retain its always-expanded naming hierarchy. Group labels remain
noninteractive. This presentation does not add tree expansion to browser
entries or change discovery, filtering, activation, menus, paging or tile mode.
Guide strokes and anchors use whole-point geometry so native rounding does not
accumulate across siblings. Strokes are centered on row midpoints, nested group
labels leave an eight-point gap after incoming branches, and native text metrics
keep group labels centered on both platforms. The native folder-hub design probe
compares actual connector endpoints, row centers and group bounds on iOS/Android.

`WorkspaceFrame` retains the Workspaces root's actual `main` container as the
leading pane on wide folder-options, local/LocalCrypt, remote and workspace-browser
routes. The root shows a choose-workspace placeholder before opening a folder.
Frames return borrowed widgets to their owners before reflow, preserving source
control references, scroll position and browser state across Back and rotation.
No duplicate folder picker is constructed for a detail route. Both existing
ScrollContainers retain independent scrolling and native route history remains
authoritative.

Workspaces uses 640 points of allocated content width after rails and safe areas
to choose two panes. The split normally divides that allocation equally.
`fold_layout.seam_fraction(include_open=True)` also accepts fully open hinge
status 3, alongside partial status 2, in landscape; other callers keep their
existing partial-only policy. The row's converted window coordinate aligns the
boundary to the physical midpoint, including asymmetric rails/insets. Hinge
changes participate in the layout key even without a size change. Regression
coverage in `test_workspace_navigation` checks retained controls, compact/wide
rotation, Back, content-width thresholds and posture-only reflow;
`test_fold_layout` checks the full-open coordinate policy.

The mobile Workspaces places rclone, Local and Network shares source controls
above its credential row. `folder_hub.source_choices` partitions logical folders
by their remote ownership, retaining all associated Local/LocalCrypt/Remote copies
within that source. Direct SMB connections use the existing `Network shares` and
`Session network shares` package associations, including retained metadata after
locking. Imported ZIPs, including ZIPs containing SMB remotes, remain under rclone.
Rendering uses cached associations without querying the native bridge. Only
rclone displays the credential selector; changing source clears collapsed groups
and resets the credential to All. The source survives rebuilding the hub during
the current app session. Setup actions appear only for unconfigured sources:
Home Server offers **Add share…**, and Cloud offers **Add Remote…**. A cached
`folder_configured_sources` snapshot includes loaded, saved, session and retained
connection metadata before folder visibility or credential filtering. Transfer
feedback takes precedence over Cloud's setup action.

On iOS, `storage_location.shared_documents_path` exposes the registered public
Documents root separately from the managed Local directory. The app-owned
`local_sources.SharedFiles` provider lists `Local` under its actual name and
protects its root from mutations. Entering it switches to `CollectionFiles`.
Local lists imported folders and downloaded/synced copies individually, alongside
shared subfolders. The root choice is marked `browser_root` and rendered as a
**Browse All Files** action below the folder tree, without a workspace menu.
The local and LocalCrypt browser omit the source strip and places its actions
button at the trailing edge of `FolderLocationHeader`, alongside Search. The
`overflow` icon uses `ellipsis.circle` on iOS and vertical dots on Android.
Workspaces owns source selection; opening an encrypted source keeps the same
single folder header. Locked Workspaces opens initialize the shared cloud
controls before entering credential checks, so cold-start unlocking uses the same
password prompt and resume callback as Home unlock.
Private app data is never used as the shared root. Managed copies continue using
`CollectionFiles` and their transfer mappings.
Regression coverage is in `Mobile/tests/test_folder_source_tabs.py` and the hub
and document-layout tests. Native device appearance still requires a device run.

## Offline documentation wiki

`logisticsmobile.documentation_ui.show_documentation` opens the shared
`commonUtils.ui.native.markdown.MarkdownWikiView` with Logistics appearance.
The catalog, native wiki UI and inert Markdown renderer belong to commonUtils. Settings opens the bundled `logisticsmobile/user_docs` tree in a detail
route. The shared `AdaptiveSidebar` uses a 260-point sidebar, 448-point article minimum
and 12-point gap after the wiki's margins; narrower allocations use a hamburger.
`resize_workspace` supplies the Settings content width after native rails/safe
areas (before the wiki's own margins). Actual parent allocation caps the width,
so split-screen and foldable windows follow available space rather than model
names or raw resolution. Search and
expanded-folder state survive page changes. Links are restricted to cataloged
local Markdown pages. This is a read-only help route, separate from editable
workspace documents, so opening help does not replace a document session.

`Mobile/tools.py` stages the documentation UI, portable catalog and all bundled
Markdown guides explicitly. New guide files must remain under the owner directory
and pass the existing linked-source rejection. Shared desktop API details remain
in commonUtils' Markdown guide.

### Mobile Markdown presentation

Settings documentation, editor previews and assistant messages use the shared
`commonUtils.ui.native.markdown_preview` parser. The mobile Briefcase manifest
includes `markdown-it-py==4.2.0`; no native parser wheel is needed. CommonMark,
tables and strikethrough render offline with escaped HTML and inert external
links/images. Documentation opts into local links and heading navigation through
the shared wiki. Its rows reserve disclosure space for leaves and indent every
level, so expanding a folder cannot move child labels left of their parent.
Focused regressions live in `commonUtils.tests.test_native_markdown` and
`Mobile/tests/test_documentation_ui.py`; host/dummy checks do not certify native
iOS or Android visual layout. See the shared native embedding guide for API details.


### Browser row selection and Markdown pane controls

The Logistics `FileBrowser` adapter and Notes Library use bundled folder/file
icons and a filled selected row rather than a checkmark in the filename. Selection
is repainted after list/tile rendering and page changes. `DocumentationReader`
applies the same host presentation to the shared wiki's visible catalog rows.
The Notes Library and documentation navigation toolbars belong to their article
pane in a wide layout; compact browsing keeps the toolbar above the active pane
so its browse toggle remains reachable. Reflow reparents the retained toolbar
without replacing the WebView or speech owner. Focused host coverage lives in
`test_native_browser`, `test_obsidian` and `test_documentation_ui`.


Validation for this presentation change: 67 focused mobile host checks passed.
An isolated iPad simulator preview verified selected rows and measured both
Markdown toolbars at the article's left edge (documentation x=284, Notes Library
x=272 logical points), beyond each 260-point browser pane. Local screenshots
and measurements are in ignored `Mobile/logs/browser-pane-review/`. Android
rendering was not visually verified in this pass.

## Settings categories and responsive panes

`SettingsNavigation` in `settings_ui.py` owns each window's category selection
and retained option ScrollContainers. `show_settings` builds the existing controls
into category-owned Boxes rather than one long scroll page. Compact category
selection uses the existing `settings-category` native route. At 640 points/dp
of allocated Settings width, the root keeps a category sidebar and selected
options pane; category selection replaces only that pane. Both panes scroll
independently. The width comes from `adaptive.content_width`, accounting for
native rails and safe areas on Android and iOS. `fold_layout.seam_fraction`
aligns the sidebar with a vertical Duo hinge; unfolded landscape uses the normal
wide layout.

`resize_workspace` and native `route_changed` synchronize the layout. Widening
a compact category returns its retained controls to the root and removes only
that category route. Narrowing a visible wide root opens the selected category
as a detail route. Nested pages are retained during resizing; returning through
Back completes the category transition without dropping those pages early.
Control instances and current values survive layout changes. The shared
preferences status follows the selected category.

`test_settings_navigation` covers compact Back, wide selection, rotation,
nested-page return, Duo seam sizing and Android/iOS category availability;
`test_settings_ui` retains preference persistence and explanatory help checks.

## Reader gestures and document origins

Document routes suppress destination tabs/rails independently of immersive
reading. `reader_chrome.sync_document_tabs` runs after fullscreen restoration and
updates native keyboard restoration state, so keyboard dismissal and rotation
cannot reveal destinations while a document or its secondary routes are visible.
The main document's leading Back arrow uses `request_reader_close`, including
unsaved-change prompts; secondary routes retain their normal Back step.
Selection callbacks pass the incoming destination explicitly because native
selection is reported before the host commits it. Reopening a retained session
captures a new return screen when its former presentation has been removed,
including when the new screen belongs to the same destination. Android's reader
bar also updates the keyboard restoration snapshot when entering or leaving a
document, preventing an empty retired bar from reappearing after dismissal.
Cancelling a managed-document close resumes its saved Preview/Edit mode. UIKit's
native Back from a close prompt clears the pending exit intent through the same
keep-editing path as the app's Back handler.

Local imports, provider readers, direct remote readers, recent entries and open
sessions present in the selected destination. Reader and private controllers
capture that destination before opening work; text editors and file pickers use
the current destination. Documents remains the shared session list. Only an
explicit command such as All documents selects that list.

Back pops document detail routes to the retained originating panel, preserving
folder, search, selection and scroll widgets. Android first dismisses applicable
reader controls or fullscreen mode. Reopening a session from another tab moves
its view and trims its previous presentation, preserving the old tab's underlying
screen and avoiding an empty route. Workspace frames are rebuilt for the new tab
without copying document buffers. Regression coverage includes
`test_document_navigation`, `test_reader_navigation`, `test_native_reader_return`
and `test_android_back`; dummy-host and mocked UIKit checks do not certify device
gesture rendering.

The host reapplies reader chrome and horizontal swipe ownership after adaptive
layout and after UIKit navigation completion, including pushes. EPUB WebViews
advertise page swipes alongside comic canvases, independently of fullscreen.
`page_animation.py` supplies E Ink policy to commonUtils' native transitions
for short comic page slides in logical reading
direction (reversed for manga), skipping initial/same-page renders and respecting
platform animation settings and E Ink mode. Library and provider content swaps
share this animation policy; private pixels remain in their native view layers.

## Native navigation validation

The October 20 physical BOOX Note Air5 C check (Android 15) verified system Back,
unsaved-change cancellation, keyboard dismissal before document exit, toolbar
Back with the keyboard open, and returning to Home, Workspaces and Documents.
Both its default rail and a test-forced native bottom bar passed. A real swipe
established the folder viewport; closing the document preserved its filter,
selection and exact scroll offset in both layouts. See the
[Android navigation evidence](mobile-evidence/2026-10-20-android-document-navigation.json)
for source hashes and coverage limits. The separate synthetic QA installation
does not update the production app.

The separate Android 16 phone-emulator check used a 360 × 640 dp display and
required the actual under-400-dp keyboard suppression branch. Portrait and
landscape suppressed the bars; first Back dismissed the IME without reaching the
document-close handler, and second Back closed the document. Rotation, native bar
snapshot transfer, retiring a document while suppression was active, and folder
search keyboard dismissal passed. Closing restored the same filter, selection
and exact native scroll offset. See the [phone keyboard evidence](mobile-evidence/2026-10-20-android-phone-keyboard.json)
for measurements, source hashes and the cutout-adjusted landscape breakpoint.

The Android 16 predictive-Back follow-up used real left/right edge swipes and
explicitly cancelled touch streams. Cancelled gestures retained clean/dirty
readers, the close prompt and IME state. With an unsaved draft and keyboard open,
the committed gesture dismissed the IME; the next gesture opened the close prompt.
Back from that prompt retained the draft. Native cold Workspaces unlock, wrong
password retry, automatic LocalCrypt folder resume and the single browser header
also passed. See [predictive Back and LocalCrypt evidence](mobile-evidence/2026-10-20-android-predictive-back-localcrypt.json)
for input details, callback evidence and physical-device/animation limits.

The physical BOOX Note Air5 C follow-up verified the cold Workspaces LocalCrypt
path using real native folder and Unlock button taps. Wrong-password retry,
automatic encrypted-folder resume, a detached source strip and one visible folder
header in the tablet workspace frame passed. See [BOOX LocalCrypt evidence](mobile-evidence/2026-10-20-boox-localcrypt-workspaces.json)
for source hashes, input details and scope. The synthetic QA installation did not
replace the normal app or use user credentials.

The October 2026 simulator check exercised synthetic local managed and provider
Markdown on iPhone and iPad with iOS 27.0. Native Back, completed and cancelled
slow edge swipes, Home → document → Show in folder, parent-folder traversal,
Home picker Cancel, Preview/Edit switching and single folder titles passed.
Video review confirmed populated parent content during interactive transitions.
The iPad check also covers native tab selection updating the Python route state.

The focused host run passed 152 mobile checks, seven packaging checks and 50
desktop/document-store checks. Local evidence is retained under the ignored
`Mobile/logs/navigation-flow-fixes/` directory, including XCTest source,
attachments, logs, a swipe recording and `report.json`. This validates the tested
simulator flows; physical devices and live remote providers need separate checks.

Native iOS folder pages place the folder title and centered storage icon/subtitle
inside the navigation bar's title view. Disk/cloud icons describe the storage;
encrypted folders also show their locked/unlocked icon. The subtitle uses native
bar containment instead of negative content margins. Search and contextual actions
are individual native bar items; the expanded search field remains in content.
The recycled table and its ordinary cells use the window palette, so the list
blends into the surrounding page in both light and dark appearance. Selected
files retain a rounded highlight in the hover palette.

## Rotation and display cutouts

Rotation is a layout event, not navigation. Workspaces retains its current source,
folder and route stack; open file drawers keep their explicit open state. Settings
retains either its category list or the category the user chose, including across
compact/wide transitions. Merely displaying the default wide category does not
authorize opening that category when returning to portrait.

The iOS host coalesces changes to each native content container's allocation and
safe-area insets into a responsive-layout wakeup. This includes inset-only changes
and portrait shrink events that Toga's normal window resize notification can
suppress. UIKit supplies the safe areas for the owning window and navigation/split
controller; no model-specific notch or Dynamic Island offsets are used. Root panels
therefore reflow against the current allocation after every orientation change.
Chat header/composer widths use the current safe host allocation rather than the
previous child layout. Android ignores unchanged global-layout callbacks, while
viewport size, padding/keyboard, navigation chrome and active-panel changes still
wake responsive layouts; explicit reflow calls are never suppressed. EPUB chapter sidebars keep their internal padding inside
the sidebar's measured width, for both imported and provider books. Chapters,
bookmarks and the provider session notice share one scrolling sidebar viewport,
so their minimum heights cannot push the reader below a short landscape safe area.

The native release suite requires `native_rotation_safe_areas`. Its
`rotation_checks.py` fixture performs two rounds of portrait → landscape-left →
portrait → landscape-right → portrait, checking route/panel identity, actual
native content bounds and visible fixed controls against the window safe area. It covers the five destinations, workspace sources, nested
folders, Home file picker, Settings categories, connection/Chat configuration,
Markdown editor/preview, imported/provider EPUB and its Find panel, comics, provider text, Notes
Library and Help. A settings category may move between a compact route and a wide
pane while retaining its logical identity. Fullscreen image content intentionally
extends beneath system chrome and is tested separately by the comic suite.

These checks run through `Mobile/ui_tools.py` in `.github/workflows/mobile-build.yml`,
which is a required dependency of `.github/workflows/release.yml`. They belong to
the real native app gate, not the pure-Python document-runtime smoke test. Native
geometry samples and failures are included in the uploaded mobile diagnostics.
Each native app run is bounded at 30 minutes; build-job limits include both iOS
device runs and their compilation time.
Physical devices, accessibility text sizes, keyboard presentation and live remote
provider behavior still require their own targeted verification.

## Selection policy owner

`logisticsmobile/workspace_policy.py` resolves retained editable session views and
owns pinned-document selection, focus swapping, unavailable-session retirement
and pair-picker eligibility without importing a native toolkit. The navigation
adapter composes `WorkspaceSelection`; its `pinned` property remains compatible.
Widget mounting, fold measurements and native toolbars remain in
`workspace_navigation.py`. Pure policy tests complement the existing workspace
navigation and reader-lifetime regressions.


## Adaptive iOS toolbar actions

`logisticsmobile.ios_toolbar` maps retained Logistics buttons to ordinary
`UIBarButtonItem` instances and semantic `UIBarButtonItemGroup` groups in the
owning navigation controller. It forwards actions to the retained button target,
copies current native menus, and keeps bar-item enabled state synchronized with
Toga. It does not mount fixed horizontal custom views or add manual glass gaps.
Folder actions and reader tools therefore participate in UIKit's horizontal and
vertical layouts; related comic navigation and document tools use distinct groups.
Close occupies the leading navigation group with native Back suppressed. Save
uses a prominent pinned trailing group. Reader titles use UIKit's normal title
allocation instead of reserving horizontal space for actions that may be vertical.
Transfer status keeps its meaningful text and its own group and higher priority.

Duo-specific overflow selection reads the owning controller's
`traitCollection.verticalBarEdge`, guarded for older systems. A preferred vertical
edge moves the existing More menu's live children into `additionalOverflowItems`.
The uncached provider retains the original menu dispatch, privacy and busy guards.
Horizontal contexts retain the native More button. Native viewport wakeups refresh
folder and reader bars after allocation/inset changes. No model-name, screen-size
or hinge-status check decides toolbar placement. UIKit chooses the physical edge,
container eligibility, item axis and overflow geometry.

Screen owners may declare `_ios_toolbar_buttons`, optional leading actions,
a title and obsolete header widgets to remove. These declarations are consumed
only by the iOS host. `prepare_form` accepts explicit primary/cancel/back labels
for selected forms; it does not promote arbitrary body or destructive actions.
Source-specific workspace actions, row menus, search fields, reading progress,
playback controls and keyboard accessories stay associated with their content.

The SDK selector requires iOS 27.1+ for Duo bar support. iOS 15 uses native
bar-item arrays when grouped navigation placements are unavailable. Host regressions in
`test_ios_toolbar`, `test_ios_bar_controls`, folder, navigation and reader tests
cover state and ownership; actual native axis, overflow and safe-area geometry
also require simulator/device validation.


The October 21 isolated QA run passed 27 screen states on each of Duo, iPhone
and iPad (81 total), with actual native Search/Save target dispatch. Separate
XCTest taps verified the normal toolbar menu on iPhone/iPad and the system
Duo overflow menu. The probe is `Mobile/native_tests/tests/logisticsmobile/ios_toolbar_probe.py`;
the UI test source is `Mobile/native_tests/ios/ToolbarMenuUITests.swift`.
See the [native toolbar evidence](mobile-evidence/2026-10-21-ios-adaptive-toolbars.json)
for source hashes, layouts and limits. Inner-display fold poses, older native
runtimes, accessibility settings and live remote providers were not exercised.
Primary-menu items clear their native target/action so a single tap opens the
menu; context-menu items retain their original primary action.

## Native safe areas during rotation

The window's bottom safe area and the destination bar's axis are independent.
`appearance.reserve_navigation` reserves any Home-indicator overlap remaining
after the native content container's insets, including when the destination bar
is vertical. Fullscreen readers retain their full-bleed canvas; Chat owns its
composer clearance and applies the same window-bound check. Declared iOS forms
refit their retained labels to current safe content width through
`ios_toolbar.fit_form`, so wide explanatory text cannot keep a landscape minimum
after returning to portrait.

## Artwork beneath vertical iOS bars

`ios_content_background` creates an image-only `UIBackgroundExtensionView`
sibling behind the active reading frame when UIKit supplies a vertical bar.
It reuses the current canvas's native image and keeps the real page, footer,
labels and actions in their original safe layout. Only the reading canvas next
to the outer bar edge can supply the extension; companion panes cannot bleed
across another pane or a fold. Its vertical bounds match the canvas, excluding
the reader's header and footer. Continuous text and form widgets are never
captured into the decorative surface.

The extension has no interactions or accessibility elements. Fullscreen,
horizontal bars, Reduce Transparency, route changes and private-reader
conceal/suspension release the native image and detach the extension. Older
systems without the native extension class keep the ordinary safe layout.
`test_ios_content_background.py` covers edge geometry and pixel-release order;
the native pose audit records the actual foreground/background rectangles.
