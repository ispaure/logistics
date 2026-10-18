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
| Folder Hub sources and presentation | `folder_hub.py`, `local_sources.py`, `folder_hub_ui.py`, `folder_hub_style.py` |
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
the bottom bar and side rail: Home, the existing Folder Hub glyph, stacked
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
are outside this workflow. Chat, Cloud, Transfers, Folder Hub, Home/Documents, Locations and Storage are now composed controllers. Their `METHODS` and `FIELDS` enumerate compatibility accessors; explicit host descriptors supply other dependencies. No catch-all attribute forwarding is used. The app retains document/provider lifecycle and reader manager integration.

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

## Folder Hub refresh

Folder Hub has no routine Refresh button; returning to the hub and credential/
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

Folder Hub displays Local, Cloud and Home Server, while retaining the internal
source keys `Local`, `rclone` and `Network shares` for routing and copy selection.
It uses a source-owned action row: Cloud shows Transfers when needed, Home
Server shows Add share, and Local has no toolbar or reserved toolbar spacing.
Switching sources moves the existing native controls; the credential selector
appears only for rclone. Empty Network shares keeps one Add share control in
the toolbar rather than duplicating it in the folder listing.

Folder Hub styling lives in `folder_hub_style.py`: dynamic semantic surfaces,
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
the saved native button styling. Folder Hub transfer banners use a live visibility
predicate: only the rclone source shows running or unsuccessful transfer notices.
Changing source reevaluates it immediately, without changing transfer state.

`browser_ui.FolderLocationHeader` shows only the currently browsed storage (drive
or cloud), adding a lock for encrypted providers/remotes. Local and remote
browsing update it after a successful listing. Its navigation glyph becomes Back
at the provider root and returns to Folder Hub; nested folders retain Up.
