# Mobile host code

This package is the Toga application source. `Mobile/` owns builds, deployment
and native acceptance packaging. Start with the [code map](code-map.md)
and [mobile preparation guide](mobile-preparation.md).
User behavior belongs in [the mobile user guide](../user_mobile/user_mobile.md).

## Owners

| Change | Owner |
| --- | --- |
| Startup, navigation composition and managed text-document lifetime | `app.py` |
| Workspace identities, generations and sessions | `workspace.py`, `window_owners.py`, `window_scenes.py` |
| Adaptive panes and destination drawers | `workspace_navigation.py`, `adaptive_workspace.py` |
| Workspaces sources and presentation | `folder_hub.py`, `local_sources.py`, `folder_hub_ui.py`, `folder_hub_style.py` |
| Local file management and comic batch entry points | `files_ui.py` |
| Text Open/Save As, picker widgets and pending bytes | `editor_picker.py` |
| Saved-import inventory and confirmed deletion | `saved_files_ui.py`: composed `SavedFilesController` |
| Explicit host dependencies and legacy state access | `host_services.py` |
| Managed text bytes, checkpoints and editing widgets | `documents.py` (host recovery), `features/text_editor/mobile/ui.py` (widgets) |
| Ordinary and provider reader ownership | `reader_sessions.py`, `private_sessions.py` |
| Reader-facing host services and shared controls | `reader_host.py`, `reader_controls.py`, `reader_chrome.py` |
| Device screen locking and sensitive-content protection | `screen_privacy.py` |

Format behavior and presentation remain with `features/books/mobile` and
`features/comics/mobile`. Cloud, managed collections and encrypted-copy adapters
remain with `features/rclone/mobile`. The host owns navigation, session policy and
workflow composition. Shared toolkit mechanisms remain in commonUtils.

`navigation.py` installs application-owned Android destination artwork on both
the bottom bar and side rail: Home, the existing Workspaces glyph, stacked
Documents, Chat bubbles and a Settings gear. These avoid manufacturer-dependent
stock menu artwork (in particular, Android's Send arrow is not the Chat icon).
Material navigation owns selection/theme tinting; iOS keeps its native symbols.

Markdown readers expose `_workspace_toolbar` so the workspace drawer shares
their existing control row instead of adding a second header. UIKit still mounts
the drawer in its native navigation bar. Reading views also expose native
button/toolbar handles so UIKit hosts the existing buttons as title-bar custom
views, preserving callbacks, menus, accessibility labels and enabled states.
Updates cache the controller/button set and never reparent borrowed buttons
during progress or dirty-state refresh. Error prompts remain visible. Text editors use top pencil/page mode
icons, and rebuild their native action menu only when clean/dirty state changes;
clean documents omit Save. Provider Markdown likewise inserts its Save icon only
for a changed editable buffer and collapses its unused mode-selector footer.
EPUB uses compact `PageFooter` controls inside its top toolbar; comic scrubbing
keeps its existing footer. Safe-area and floating-tab clearance remain in force.
The isolated `compact_reading_probe.py` measures Markdown and EPUB reading areas
through portrait, landscape and portrait return, including provider sessions.

The pinned Toga iOS backend queues scroll-view refreshes during layout. The
host's `appearance.py` adapter ignores refresh/scroll callbacks after their weak
Python interface has been released. Editor preview shutdown remains with the
Text Editor feature, which retires WebKit delegates before releasing its view.

## Open/Save As lifecycle

`app.editor_picker()` lazily creates one `EditorPicker` per host. It owns picker
widgets, rows, provider associations, source document, pending bytes, privacy gate
and cancellation. The app's existing picker methods/attributes delegate to that
owner for native probes and existing callbacks; they do not duplicate its state.
The controller explicitly enumerates host services with `HostService`; it has no
catch-all attribute forwarding. `files_ui.py` retains file-management behavior
and small compatibility delegates for picker entry points.

Provider selection and widget values are captured on the UI loop. Listing,
resolution, publication and verification run in worker threads using captured
models/values and a workflow-local cancellation event. The picker participates
in the host busy policy, but never takes over another workflow's `_crypt_cancel`.
Host Cancel dispatches to each relevant owner. Busy remains set until the picker
worker returns; a cancelled blocking call must still settle before reuse.

Worker results are checked against the owning host, picker epoch, credential
client/generation, navigation generation and source privacy gate. Late listings,
errors and resolved opens cannot replace newer state. Private catalog clearing,
host replacement and successful exit invalidate/clear picker state. Concealing
private content also cancels picker work. Cancellation can arrive after a file
was published; it does not imply that completed publication was rolled back.

Save As still publishes without overwriting, verifies the reopened bytes, and
retains its draft if reopening fails. `app.finish_save_as_source()` owns the
managed-document handoff after successful reopening; the picker cannot mutate
an editor widget through an implicit host attribute. Privacy gates follow the
exported provider session. Storage/cancellation correctness remains owned by the
existing resource operations, not a second implementation here.

## Saved imports and host composition

`app.saved_files()` composes `SavedFilesController`, replacing its former app
mixin. The controller owns inventory presentation/message state and explicitly
uses host reader/workspace services. Deletion still checks other windows and busy
readers before and after confirmation, retires affected sessions, and forgets
Recent/import mappings. Original sources and managed Local/LocalCrypt folders
are outside this workflow. Chat, Cloud, Transfers, Workspaces, Home/Documents, Locations and Storage are now composed controllers. Their `METHODS` and `FIELDS` enumerate compatibility accessors; explicit host descriptors supply other dependencies. No catch-all attribute forwarding is used. The app retains document/provider lifecycle and reader manager integration.

## Packaging and verification

Add host modules to `Python/logisticsmobile/mobile_sources.json` and feature/service modules to their owning manifests in the same change as imports. `Mobile/tools.py` aggregates and validates these declarations.
`editor_picker.py` and `host_services.py` are explicitly staged. Do not edit
generated `Mobile/payload/` or Briefcase projects as application source.

| Contract | Tests |
| --- | --- |
| Picker ownership, cancellation, stale results, locked-source saving | `Mobile/tests/test_editor_picker.py` |
| Provider identity, Save As verification and reopen failures | `Mobile/tests/test_files_ui.py` |
| Private drafts, privacy handoff and delayed opens | `Mobile/tests/test_private_sessions.py` |
| Saved-import safety, other windows and reader retirement | `Mobile/tests/test_saved_files.py` |
| Window ownership, layout/navigation and paired panes | `Mobile/tests/test_window_owners.py`, `test_workspace_ui.py` |
| Payload completeness and portable imports | `Python/tests/test_mobile_packaging.py`, `test_mobile_portability.py` |

Use the [host validation commands](mobile-launchers.md#host-validation).
These are host contracts. Apple/Android picker layout, native Back and real
LocalCrypt transfer behavior still need the existing native acceptance scenarios
in `Mobile/native_tests/tests/logisticsmobile/localcrypt_checks.py`.

## Workflow controllers

`features/lm/mobile/controller.py` owns chat state; rclone owns cloud and transfer controllers. Host navigation workflows have dedicated `*_controller.py` modules. `services/workflow_host.py` supplies explicit read/write host attributes. `host_services.composed_workflow` installs only declared compatibility names. Transfer/review cancellation is independent from file/cloud cancellation; global Cancel dispatches to both. Ownership and cancellation are exercised by `Mobile/tests/test_workflow_ownership.py`.

## Native source editor and live Markdown

The Text Editor mobile owner uses `commonUtils.ui.native.code_input.CodeInput`
for source editing and the existing offline renderer for live Markdown. Preview
is enabled by default for Markdown, stacked in compact editor allocations and
beside the source at 720 logical units of usable width. The session's existing
`markdown_split` field stores the visible/hidden choice. The separate full-page
preview remains available. Local/private editable Markdown retains its source
while previewing; remote text stays read-only.

On Android 12 and newer, `logisticsmobile.android_markdown_font` obtains the
font selected for a native Toga label through `TextRunShaper`, then supplies its
exact glyph tables to marked Markdown preview and formatted-editor WebViews.
CSS `sans-serif` alone does not reliably follow OEM font customization. The
bridge supports TrueType collections and compresses the selected face as WOFF
using the standard library. The pinned Toga client's request interceptor serves
each view's unique font URL from RAM with CORS and `no-store` headers; it never
fetches that URL from the network. Font bytes stay outside document HTML so
private pages retain their existing 2 MiB memory-only bound. Retired URLs return
410, and unmarked book/transcript pages retain their own typography. Code stays
monospace. Older Android versions, inaccessible fonts and native font buffers
above 32 MiB retain the CSS fallback; other script fallback remains WebView-owned.
`Mobile/tests/test_markdown_font.py` covers routing, retirement, content policy,
font collection extraction and lossless WOFF tables. The isolated
`Mobile/native_tests/tests/logisticsmobile/markdown_font_probe.py` checks actual
font loading and native glyph measurements across preview, formatted editing
and large private pages, using the device font plus serif and monospace faces.
The [2026-10-18 Note Air 5C report](mobile-evidence/2026-10-18-markdown-font.json)
records all nine successful Android 15 checks and the tested source hashes.

Desktop and mobile share language detection and Pygments grammars through
`formats.code_syntax`, `formats.code_blade` and `formats.code_spans`. The mobile
manifest pins Pygments 2.19.2. Native attributes/spans preserve source, selection
and keyboard ownership. CodeInput skips expensive colouring above 128 Ki
characters while retaining editing and logical line numbers. Android's
CodeEditorSupport Java bridge draws the gutter against native wrapped lines;
iOS uses a UITextView overlay with native line-fragment geometry.

The isolated [iOS editor evidence](mobile-evidence/2026-10-17-source-editor/editor.json)
covers native typing into Markdown, a rendered table, live updates, syntax
colouring and preserved selection. The [source screenshot](mobile-evidence/2026-10-17-source-editor/source-python.png)
and [live preview screenshot](mobile-evidence/2026-10-17-source-editor/markdown-live.png)
use synthetic files and a separate simulator app identity. Android bridge compilation
and host editor regressions passed; this evidence does not certify physical-device
keyboards, IME/undo gestures or Android runtime editor appearance.

## Settings persistence and folder search

Mobile Settings saves font size, restore behavior and restart clearing on change,
alongside the existing immediate overview and Android appearance handlers.
`show_legacy_session` belongs to the running host; preference loading ignores
older persisted `show_legacy` values and saving writes its compatibility value
as false. Reloading preferences preserves the session visibility choice.

Online folder search filters the complete native bridge listing in memory;
ordinary and crypt remote listings have no entry count cap. Local providers use
the cancellable recursive search with no scan or result count cap. Native rows
remain paginated at 40 per page. Local reads use the cancellable listing path
without toggling global cloud controls or refreshing the download inventory.
Folder pages are built offscreen before attachment; thumbnails remain asynchronous. Regression coverage lives in
`Mobile/tests/test_native_browser.py`, `Mobile/tests/test_settings_ui.py`,
`Python/tests/test_mobile_hub.py` and `Mobile/rclone_bridge/list_test.go`.

Session-only imports retain password-protected source ZIPs using the separate
device-encrypted `CredentialPackages` store for future password-only unlocking.
Decoded credentials and ZIP passwords stay in memory. Preference writes filter
session-only associations; retained-package metadata belongs to its own index.
Settings autosave cannot persist decoded session credentials.

Resume-password gates carry a memory-only credential name supplied when importing
a session package or adding a connection. The lock form lists only remaining
locked gates, updating after each accepted password. Unnamed private-document
gates use a generic private-session label. The scrollable form preserves the
existing root replacement, safe-area handling and lifecycle race checks.

## Startup and document responsiveness

The host builds Settings on first use rather than during startup. Native Settings
tab selection mounts its root without recursively activating a destination;
direct settings-detail actions initialize the root before pushing their detail.
Navigation and resize callbacks reflow Settings only while that destination is
visible. Selecting it again measures the retained controls at the current width.
Settings itself retains its category menu and constructs/presents each category
only when first selected (or when the initial wide layout displays App).
`SettingsPages` preserves menu order and membership without constructing pages.
Reflow fits only the sidebar and displayed category; hidden pages adopt the
current width when revisited. Category highlights update only when their state
changes, and Apple text fitting reuses a measurement label after checking the
text/width/font cache. About's build-information lookup runs only on opening About.
Reload preferences explicitly rebuilds category factories; ordinary visits reuse
their controls. Saving preferences reads only the controls already constructed,
preserving preference values belonging to unopened categories.
Restore/clear-on-restart switches do not rebuild the unrelated Documents list;
font changes retain their existing editor/overview refresh.

A browser file tap publishes selection and opens the document directly. It does
not first await the browser's detailed metadata callback; explicit information
selection still supports that callback. Folder navigation, bounded row counts,
selection validation and cancellation remain in place.
Async selection callbacks must still reference the same listing and visible
entry before opening; replacing the listing cancels that tap. Selection styling
updates only rows whose selected state changed, rather than reapplying native
surface styles and fetching every button's text on each tap.

Provider-backed Markdown, including ordinary local files, prepares its initial
preview and sibling images on a worker before constructing the native preview.
The rendered HTML is handed to the UI once, with the existing cancellation check
before publication. Source editing and subsequent preview toggles retain their
existing behavior. Rendering errors retain the source view and existing feedback.

`CollectionFiles.list` formats timestamps using the date's local UTC offset from
`time.localtime`, avoiding repeated system-timezone probes by `astimezone` for
every file. Tests compare the resulting strings across DST transitions and
half-hour offsets, including fractional seconds that round across DST changes.
In a macOS host microbenchmark, 1,000 timestamp conversions
dropped from about 604 ms to 62 ms; this is not Android device timing.

`Mobile/tests/test_mobile_responsiveness.py` covers deferred Settings, native tab
selection without reentry, file taps bypassing metadata, and worker-only initial
Markdown rendering. Existing browser, folder-navigation, private-session and
Android Back tests cover lifecycle behavior. Physical Android launch, filesystem
and WebView timings still require a device run. Shared syntax detection changes
are documented and tested in commonUtils, not duplicated in the host contract.

Workspace saves skip repeated durable publication only when the serialized
ordinary-session state and on-disk revision are unchanged. The revision includes
device/inode, size, nanosecond modification/change times, mode and link count.
Deletion or replacement forces a write; linked paths are still rejected before
checking the cache. Draft recovery writes keep their existing durability policy.
`Python/tests/test_mobile_workspace.py` covers view changes and external edits.

## Workspaces refresh

Workspaces has no routine Refresh button; returning to the hub and credential/
transfer state changes update its list automatically. The error page offers
**Try again** through `refresh_folder_hub`. Refresh uses loaded remote names, the credential-load crypt location
snapshot and local transfer mappings. Credential loading also retains crypt
account identities, so refresh checks their local directories for newly present
or removed copies without resolving identities through rclone again. It rereads
local directory names without
calling native crypt discovery or waiting for cloud/transfer work. Unchanged
choices retain their existing widgets; changed choices update the list in place
without replacing the page or navigation. Credential loading owns
`refresh_hub_crypt_locations`, including its client/generation guard.

Source switches cache one native row hierarchy per source on the current hub
page. A return to an unchanged tab reattaches that hierarchy; credential filters
replace only that source's cached view. Discovery, loaded/crypt credential state,
network-share ownership or legacy visibility changes invalidate all three views.
Snapshots own copies of discovery data so in-place mapping changes invalidate
them too. New hierarchies are assembled detached and mounted as one subtree,
avoiding incremental layout of the visible scroll container. Rendering reads
loaded remote names and retained crypt metadata once per update, independently
of row count. Source changes suppress the credential selector's reset callback
to avoid a duplicate discovery/render pass. Folder discovery still checks local
changes when switching sources; cached widgets do not authorize remote access.

`Mobile/tests/test_folder_navigation_performance.py` covers row reuse, bounded
credential reads, a single source-change render and local/lock-state invalidation.
These host checks establish work reduction; device timing remains unmeasured.

The default source is Local. `source_choices` includes managed Local/LocalCrypt
copies there as well as under their remote owner, retaining the full logical
entry for overflow actions. `folder_browse_copy` selects the device copy for
Local taps and the Remote copy (including job-remote mappings) for rclone taps;
action pages keep their existing transfer and deletion identity. Row icons and
legends describe the active tab’s storage. Remote encryption uses the cached
crypt-remote snapshot or an existing LocalCrypt copy, without bridge discovery.

Workspaces displays Local, Cloud and Home Server, while retaining the internal
source keys `Local`, `rclone` and `Network shares` for routing and copy selection.
It uses a source-owned action row: Cloud shows Transfers when needed, Home
Server shows Add share, and Local has no toolbar or reserved toolbar spacing.
Switching sources moves the existing native controls; the credential selector
appears only for rclone. Empty Network shares keeps one Add share control in
the toolbar rather than duplicating it in the folder listing.

Workspaces styling lives in `folder_hub_style.py`: dynamic semantic surfaces,
selected tab styling and compact native symbols. Each top-level branch has one
rounded surface with transparent rows, separators and permanent vertical guides.
Each level advances 40 points. Group labels reserve the same 32-point icon slot
and 4-point label gap as folder rows, so a child group cannot back-align with
its parent's label. Child folder icons also start beyond their parent's label.
Informational group labels have no handlers or disclosure controls. Encrypted
folders use shared vector folder/lock geometry on both native platforms, with
individual blue `folder_unlocked` and orange `folder_locked` roles. These roles
have light/dark palettes and turn black in Android monochrome mode; distinct
open/closed shackles and accessible names preserve the state without color.
The shared native destination bar remains platform-owned. Idle loading controls
are detached from `folder_loading_box`; folder opening temporarily attaches the
status and progress controls, and removes them on completion.

Android high-contrast surfaces repaint after generic native button styling, so
refreshes preserve selected-tab inversion and borderless row controls.
The app explicitly enables Material's active destination indicator on both the
bottom bar and rail, using a 40 dp square with a black fill and white checked
icon. Leaving high contrast restores the indicator's original enabled state,
dimensions, shape and colors as well as ripple and elevation.
Surface buttons suppress elevation and state animation in that mode; leaving it restores
the saved native button styling. Workspaces transfer banners use a live visibility
predicate: only the rclone source shows running or unsuccessful transfer notices.
Changing source reevaluates it immediately, without changing transfer state.

`browser_ui.FolderLocationHeader` shows only the currently browsed storage (drive
or cloud), adding a lock for encrypted providers/remotes. Local and remote
browsing update it after a successful listing. Its navigation glyph becomes Back
at the provider root and returns to Workspaces; nested folders retain Up.

## Android Workspaces profiling — 2026-10-19

The disposable [performance probe](../../Mobile/native_tests/tests/logisticsmobile/performance_probe.py)
measures native Android navigation callbacks, the next native draw, nested workflow
spans and cProfile call trees. It uses an isolated storage root and four synthetic
locked LocalCrypt folders with matching retained remote metadata. Credentials are
not loaded, and the association lookup returns fixture metadata. Discovery and UI
construction otherwise use the normal application paths. This does not measure
an external SD card or the user's credential vault.

The measured source was Logistics `433c6038` and commonUtils `710bc341`, with a
probe-only launcher. The API 35 ARM64 emulator ran on the development Mac; these
times are not Samsung A15 hardware timings. Three unprofiled visits per source
gave these medians:

| Operation | Local | Cloud |
| --- | ---: | ---: |
| Navigation callback, including native activation | 173 ms | 156 ms |
| Entry to next native draw | 191 ms | 168 ms |
| Folder discovery | 4.8 ms | 4.3 ms |
| Whole picker construction, including discovery and rows | 164 ms | 146 ms |
| Row construction and styling, within picker construction | 118 ms | 102 ms |
| Workspace save | 0.4 ms | 0.2 ms |

Nested spans overlap and must not be added. cProfile adds overhead, so its elapsed
times are used to locate work rather than as user-facing latency measurements.
One Local visit constructed 74 widgets and 25 buttons, called `paint_surface`
112 times and button `rehint` 221 times. Surface painting occupied 129 ms of a
233 ms profiled visit, including native drawable/tint work and Java import
resolution. It overlaps widget-construction time.

`HubUI.refresh_hub('files')` rebuilds the picker on every root tab visit.
`build_folder_picker` resets `folder_tab_views`, so that cache does not survive
leaving and returning to Workspaces. A probe-only counterfactual that bypassed
this rebuild reduced the callback median to 8 ms and next-draw median to 25 ms.
It is not a production fix: retaining a page must still refresh discovery and
invalidate rows when credentials, lock state, storage, mappings or visibility
change.

Other measured callbacks were Documents 41–43 ms; Settings 305 ms on first entry
and 52 ms on return; Chat 239 ms on first entry and 14 ms on return. The four-second
Samsung delay was not reproduced in this emulator. Device CPU speed, actual
storage and application state remain unmeasured; do not attribute the entire
reported delay to these emulator results.

### Retained Workspaces implementation

Workspaces now retains its root page and controls between visits. Tab entry still
runs local discovery and `update_folder_list`; the existing snapshot covers
folder choices, network-share ownership, loaded/crypt remote names and visibility.
Changed snapshots invalidate every source's rows, including detached tabs. An
unchanged source retains its native rows and does not repaint the source buttons.
Source and credential selection survive returning to the page. Transfer actions
are reevaluated even when folder rows are reused. Explicit Refresh also checks
lock state when names are unchanged. Discovery errors replace the page with the
existing recovery actions and discard the failed page for a fresh retry.

The attached root is not removed and reattached on an unchanged tab return.
Detail routes retain their previous browser/Back behavior. The same emulator
fixture measured warm Local callbacks at 12–13 ms and Cloud at 9–12 ms, with the
next native draw at 20–31 ms. The first build of a source remains more expensive
(126–143 ms callback in this run). These are emulator results, not an estimate of
Samsung A15 latency. Native checks verify page/source reuse, lock/unlock changes,
hidden-source invalidation and folder creation/removal. The mobile regression
suite also covers credential filters, transfer actions, discovery recovery and
reader/browser return routes. Native iOS simulator checks also pass for retained
view parenting, source/credential selection, lock indicators, folder discovery,
workspace actions and Back navigation.

The probe must run only in a disposable QA application on a simulator/emulator.
Copy it into that application's isolated Python payload and replace only the QA
launcher with `main().main_loop()`. It writes `performance-evidence/result.json`,
human-readable profiles and `.prof` call trees under that app's cache directory.
Keep it out of normal launchers and signed tester releases. The draw listener is
Android-specific. Results in this run are retained locally under
`Mobile/build/performance-profile/android/`.

## App reset boundary

`logisticsmobile.app_reset` owns reset operations. Android calls its own
`ActivityManager.clearApplicationUserData()`; no package argument can target
another app. iOS records a schema-only durable request in private storage. The
primary app processes it before `prepare_for_app` migration or service creation.
The reset never reads collection-volume pointers for erasure. It clears public
Documents, Application Support (including config/private state), caches, WebKit,
cookies, saved application state and app temporary files. A contained symlink is
unlinked without visiting its target; linked root paths are refused. The retry
marker survives partial deletion and is removed last.

iOS deletes only Logistics's two credential Keychain service namespaces,
including keys orphaned by corrupt metadata, then clears the app's native user
defaults. Other Keychain services remain. Key deletion must succeed before file
erasure. Reset confirmation requires ERASE and no active transfer/generation or
other window. The iOS reset notice replaces navigation and suppresses exit
checkpoints until a full process restart; new-window requests are refused.

The collection UI separately previews explicit paths and selected/active state.
`start_empty_location` refuses any nonempty tree and never copies or deletes the
old collection. `recover_location` is presented as using existing files without
copying. `wipe_destination` remains forbidden for the active location.

The app-only UserDefaults reset is declared with CA92.1 in
`Mobile/privacy/App.xcprivacy`, copied as a target resource before signing and
verified in exported apps. Platform API references:
[Android clearApplicationUserData](https://developer.android.com/reference/android/app/ActivityManager#clearApplicationUserData())
and [Apple Keychain deletion](https://developer.apple.com/documentation/security/secitemdelete(_:)).
