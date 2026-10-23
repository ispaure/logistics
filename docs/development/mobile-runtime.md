# Mobile host code

This package is the Toga application source. `mobile_build/` owns builds, deployment
and native acceptance packaging. Start with the [code map](code-map.md)
and [mobile preparation guide](mobile-preparation.md).
User behavior belongs in [the mobile user guide](../user_mobile/user_mobile.md).

## Owners

`mobile.snow.SeasonalSnow` uses `services.seasonal` for the shared
December 15–January 2 season, including both endpoints. The default-on `seasonal_snow` preference is edited
in Appearance on both platforms. A touch-transparent UIView with animated
CALayers on iOS and `SnowView.java` on Android provide the decoration. A one-second
watcher removes it for system high contrast, Android E Ink, inactive privacy
state, or a disabled preference. Window disposal cancels the watcher. Owner source
manifests include the policy and Android view. `test_seasonal_snow.py` covers
preferences/settings; `native_tests/tests/logisticsmobile/snow_probe.py` is the
isolated native overlay smoke test.

Workspace navigation sizes are defined in `mobile.ui_metrics`: 17 native
pt/sp body text, 16 control text, 13 caption text and 48 pt/dp touch targets.
`toga_font_size()` converts native design sizes by 72/96 because both pinned Toga
mobile font backends multiply explicit fonts by 96/72. Pack requires integer
font sizes, so the helper rounds (17 native becomes 13 Toga, about 17.3 native).
Do not apply this conversion
to geometry or direct UIKit/Android font APIs. Android retains system sp scaling
and reported density; there is no BOOX model multiplier or physical-DPI detection.
`folder_hub_style` and `folder_hub_ui` consume these metrics; native file lists
use 48-unit rows on both platforms (the Java adapter mirrors the constants).
Android scroll-position calculations must use the same row height as binding.
The Android adapter adds a 1dp native list divider using the palette border color,
inset 8dp at both ends of the row bounds, including beneath the icons. iOS uses
12pt insets for its app-owned lines without changing UIKit's content insets.
iOS row images retain their renderer scale after PNG decoding, keeping their
28pt image slot aligned with Android's 28dp icons on Retina displays.
Its high-contrast group outline encloses the populated portion of short lists
or the viewport for long lists, painted after children so selected fills cannot
cover it. Folder icons and accessibility descriptions identify folders without
Android disclosure chevrons; iOS keeps its native disclosure and selection.
The Android scrollbar reserves its own width outside the rows, with a 4dp gap;
the group outline follows the inset row bounds so it stays clear of the thumb.
Scroll offsets include spacing between rows, with no extra trailing divider height.
Workspace folder surfaces opt into the existing E Ink outline role, which paints
a square black border on Android; noninteractive group headings stay borderless.
This policy covers workspace and file navigation, not all feature UI or readers;
system accessibility extremes still require native layout validation.

| Change | Owner |
| --- | --- |
| Startup and application wiring | `app.py`, `composition/assembly.py`, `composition/presentation.py` |
| Workspace identities, generations and sessions | `workspace.py`, `window_owners.py`, `window_scenes.py` |
| Adaptive panes and destination drawers | `workspace_navigation.py`, `adaptive_workspace.py` |
| Workspaces discovery task, cache and invalidation | `folder_discovery.py`, composed by `folder_controller.py`; snapshot/result building in `folder_hub.py` |
| Workspaces sources and presentation | `folder_hub.py`, `local_sources.py`, `folder_hub_ui.py`, `folder_hub_style.py` |
| File create/rename/move/delete coordination | `file_operations.py`, composed by `composition.presentation.file_operations`; `files_ui.py` retains forms, confirmation and forwarding methods |
| Main and workspace browser listing requests | `folder_listing.py`; presentation in `files_ui.py` and `workspace_navigation.py` |
| Local file management and comic batch entry points | `files_ui.py` |
| Text Open/Save As, picker widgets and pending bytes | `editor_picker.py` |
| Saved-import inventory and confirmed deletion | `saved_files_ui.py`: composed `SavedFilesController` |
| Explicit read-only services and writable compatibility state | `services/workflow_host.py`; lazy owner access in `composition/assembly.py` |
| Managed text bytes, checkpoints and editing widgets | `documents.py` (host recovery), `features/text_editor/mobile/ui.py` (widgets) |
| Provider Markdown modes, controls and preview lifecycle | `features/text_editor/mobile/provider_markdown.py`, composed by `composition.presentation.provider_markdown`; session source input remains authoritative |
| Ordinary and provider reader ownership | `reader_sessions.py`, `private_sessions.py` |
| Session Close/Back decisions and source return | `session_workflows/transitions.py`, source-specific `session_workflows/adapters.py`; facade in `reader_lifecycle.py` |
| Reader surface publication and footer/chrome synchronization | `reading/publication.py`, validity captures in `reading/sources.py` |
| Settings composition, category controls and connection forms | `settings/navigation.py`, `settings/categories.py`, `settings/forms.py`, `settings/speech.py`, `settings/information.py` |
| Temporary file-opening presentation and measured read progress | `document_sources.py`, `loading_progress.py` |
| Reader-facing host services and shared controls | `reader_host.py`, `reader_controls.py`, `reader_chrome.py` |
| Device screen locking and sensitive-content protection | `screen_privacy.py` |

Format behavior and presentation remain with `features/books/mobile` and
`features/comics/mobile`. Cloud, managed collections and encrypted-copy adapters
remain with `features/rclone/mobile`. The host owns navigation, session policy and
workflow composition. Shared toolkit mechanisms remain in commonUtils.

Feature adapters receive application policy through presentation contracts.
`MobileHostUI` supplies folder-route recording and temporary loading-panel scopes
to rclone; `MobilePresentation` supplies font sizing/binding and folder actions to
the text editor. Feature code must not import the `mobile` host to reach
those services. Secondary scene hosts share the application's command registry
alongside its other application infrastructure, while retaining independent
document and navigation state.

`navigation.py` installs the desktop destination artwork on Android bottom bars
and rails and iOS tabs: Home, Workspaces, stacked Documents, the Chat bubble and
Settings sliders. `mobile_build/generate_navigation_icons.py` renders the canonical
`desktop.sidebar.DestinationIcon` drawings into bundled transparent 3x PNGs in
`hub_icons.py`; run it with the desktop interpreter, or use `--check` to verify
the generated assets. Mobile has no Qt runtime dependency. Material and UIKit
own selection/theme tinting; iOS retains the artwork in each Toga OptionItem so
native tab reconstruction preserves it.

Android folder headers use symmetric action gutters around a 17sp title and
12.75sp storage description. Inline image spans keep the 12dp storage/lock
indicators centered with the description and preserve middle ellipsis at narrow
widths. Buttons retain 48dp targets and their existing Android backgrounds.
`action_menu.NativeMenu` wraps the shared menu with an Android theme resolved
when it opens; document menus retain their native groups. Workspace row menus
resolve their commands at opening time and reuse the guarded folder actions
without navigating to the fallback page. On iOS, file-row accessory buttons use
uncached deferred `UIMenu` elements; row selection resolves commands asynchronously
and retired cells return no actions. Menu callbacks retain the browser epoch and
selection guards. Chat receives the same
menu factory through `MobilePresentation.NativeMenu`. `android_res` supplies
8dp popup corners and a white, black-outlined E Ink variant. The resources are
copied from the host's resource tree into generated Android projects by
`cloud_build.configure_android_sources`, alongside the Books native resources.

Markdown readers expose `_workspace_toolbar` so the workspace drawer shares
their existing control row instead of adding a second header. UIKit still mounts
the drawer in its native navigation bar. Reading views also expose native
button/toolbar handles so UIKit hosts the existing buttons as title-bar custom
views, preserving callbacks, menus, accessibility labels and enabled states.
Updates cache the controller/button set and only rebuild the action groups when
its buttons change. Error prompts remain visible. Text editors use top pencil/page mode
icons, and rebuild their native action menu only when clean/dirty state changes;
clean documents omit Save. Provider Markdown likewise inserts its Save icon only
for a changed editable buffer and collapses its unused mode-selector footer.
EPUB and PDF keep page commands/progress in a footer; comic scrubbing keeps its
existing footer. All iOS readers and text editors publish `_native_reader_title`
and their supported action buttons through the same title-bar contract. The
host's `ios_reader_chrome.reader_title` centers the label relative to the native
window during UIKit layout, allowing asymmetric action groups without shifting
the visible title. Fullscreen continues to hide the entire native bar.
UIKit owns navigation-button backgrounds: `ios_reader_chrome.bar_control` marks
mounted controls so surface/trait refreshes keep their backgrounds clear, remove
app outlines and avoid a second button configuration inside the system glass.
Independent reader actions (including speech and More) have separate bar items
and fixed-space separators. Adjacent previous/next comic controls share one
constrained stack; Close and the workspace drawer are separate. Folder title
actions retain their shared stack with transparent contents. Standalone drawer
buttons use one native glass configuration (gray on older systems), restored on
trait refresh. `test_ios_bar_controls.py` covers grouping/repaint policy and the
disposable `ios_bubble_probe.py` checks native layout, menus, fullscreen return,
light/dark rendering and existing save/cancel/discard/conflict guards.
The October 20 glass-button evidence (local artifact `test-results/mobile-evidence/2026-10-20-ios-bubbles.json`)
records iOS 27 iPhone/iPad simulator results, portrait/landscape return, source
hashes and screenshots. The disposable apps were removed after evidence capture.
Native-only filename/status controls are detached to avoid duplicate titles;
managed editor renaming remains available through its action menu. PDF tools
stay above the canvas when open, and single-image readers omit page navigation.
Notes Library/documentation keep their trees while putting history/parent
commands in their native More menus. Safe-area and floating-tab clearance remain in force.
The isolated `compact_reading_probe.py` measures Markdown and EPUB reading areas
through portrait, landscape and portrait return, including provider sessions.

The pinned Toga iOS backend queues scroll-view refreshes during layout. The
host's `appearance.py` adapter ignores refresh/scroll callbacks after their weak
Python interface has been released. Editor preview shutdown remains with the
Text Editor feature, which retires WebKit delegates before releasing its view.

## Folder listing ownership

Each main file browser and workspace drawer owns a separate `FolderListing`.
It starts and invalidates reads, supplies a cooperative cancellation event, and
rejects late results and errors after a newer request, location change, host or
browser replacement, or private credential replacement/generation change. Locking
private storage explicitly invalidates these reads. The worker receives a captured
provider (or drawer `ResourceSelection`) and folder, and never reads widgets.

`files_ui.py` retains provider resolution, row labels, search/sort, successful
location recording and failed-navigation recovery. `workspace_navigation.py`
retains root discovery, refresh coalescing, extension filters, breadcrumbs and its
existing error presentation. Drawer generations also invalidate active requests.
Main listing continues to call the provider directly; drawers continue through
`ResourceSelection`. Listing has no mutation busy guard, so local browsing during
transfers keeps its existing policy. Open/Save As pickers and remote connection
setup remain separate workflows.

Run `python3 dev.py test mobile test_folder_listing.py`, `test_files_ui.py`,
`test_workspace_navigation.py`, `test_folder_navigation_performance.py` and
`test_private_sessions.py`. `test_packaged_startup.py` exercises both listing
adapters from the staged payload; desktop `test_mobile_packaging.py` checks manifest
closure.

## File operation ownership

`FilesUI.file_operations()` owns one `FileOperations` coordinator. The UI captures
an immutable `FileOperationRequest` on the UI thread: operation, source provider,
path, entered name/target and destination specification. The worker receives no
widgets. `FileDestination` preserves existing provider objects and captures the
root, client, generation and remote for locations requiring resolution. Native
encrypted destination resolution stays in the worker and rejects a changed
credential generation before construction.

The host adapter in `composition.presentation.file_operations` retains transfer/busy and
unsaved-reader policy, snapshots controls/status and connects the coordinator's
cancellation event to the existing `_crypt_cancel`/Cancel path. The coordinator
owns its request and task until the worker retires. Cancelling an awaiting task
signals cancellation and waits for its thread before releasing the busy guard;
there is no new parallel mutation path. Existing `file_work` callbacks remain
supported, including the selected-provider/path compatibility snapshot.

The UI still confirms Delete before submitting its captured target. Selection
changes during the dialog do not retarget that request. Success refreshes the
current browser; navigation, provider/credential replacement or host retirement
prevents old completion/error messages from replacing newer status. Cleanup
restores captured controls and releases only its own cancellation/busy ownership.

Actual writes, no-clobber publication, verification and deletion remain in
commonUtils resource operations. Cancellation is cooperative and does not promise
rollback: incomplete mutations retain their existing refresh-before-retry warning.
No preference, storage schema or confirmation wording changes are introduced.

Run `python3 dev.py test mobile test_file_operations.py` and `test_files_ui.py`
(`py` on Windows). Checks cover captured requests, worker destination resolution,
confirmed delete identity, overwrite refusal, partial failures, busy/dirty guards,
late status and cancellation cleanup. Staged startup creates and renames a folder
from the payload, and packaging checks reject an omitted coordinator module.
See [validation](testing.md) for environment setup.

## Workspaces folder discovery

`FolderController.discovery` owns the refresh task, cache, credential stamp and
invalidation epoch. `folder_discovery.py` receives explicit snapshot, publication,
error and host-liveness callbacks; it does not depend on folder widgets. Requests
during a scan share its task and coalesce into one rescan. Invalidating clears
cached private names immediately. A subsequent request is retained even if the
retired worker has not finished yet.

The controller captures a detached `FolderDiscoverySnapshot` on the UI thread:
resolved mappings, known remote names, retained package metadata and cached crypt
locations/identities. `folder_hub.discover_folder_choices` reads local directories
and returns a `FolderDiscoveryResult`; it neither mutates the snapshot nor
receives a client or application-shaped callback object. It preserves existing
folder grouping, copy precedence and the shared Local root. Discovery does not
fetch remote contents or authorize access to a listed location. Native crypt
identity discovery still happens separately when credentials load.

Results and errors are published on the UI thread only while their epoch,
credential-client identity/generation and refresh request remain current. Old
errors cannot replace status for a locked or newer session. Native hosts read a
copy of the credential-matching cache while refreshing; dummy/desktop hosts keep
the existing synchronous discovery path. `folder_hub_ui.py` retains presentation,
navigation and forwarding methods; opening folders still uses existing credential
guards.

Run `python3 dev.py test mobile 'test_folder_*.py'` for discovery, grouping, tabs,
selection and navigation checks (`py` on Windows). The discovery tests include
snapshot isolation, worker/UI ownership, refresh coalescing, stale results/errors,
lock/shutdown and retry recovery. Packaging checks reject an omitted discovery
module, and staged startup exercises an actual Workspaces refresh using only the
payload. See [validation](testing.md) for environments and packaging commands.

## Destination entry cost

Android's global-layout callback also runs when child text is measured without
a viewport change. The host compares native bounds, insets, navigation mode,
destination and body identity before reflowing responsive panels. Unchanged
native callbacks return without measuring those children again; keyboard,
rotation, navigation and explicit application reflows remain active. This keeps
Chat layout from starving completion callbacks for finished background work.

Entering Workspaces with Local selected reuses the folder view and discovers
local changes without constructing the cloud browser or credential settings.
Selecting Cloud or Home Server still initializes remote controls and restores
saved credentials. Local folder opening uses its own loading status even when
remote progress widgets have never been created.

Settings fits its category menu before mounting it in the destination. The static
menu retains its measured width across repeated tab and layout callbacks and
refits when the pane width changes. Category status messages continue to refit
as their text changes; compact/wide routes keep the same preference controls.
These contracts are covered by `test_folder_hub.py`, `test_settings_ui.py`,
`test_settings_navigation.py` and `test_settings_checkpoints.py` in `mobile_build/tests`.
Host profiles measure Python work only; Android draw latency requires the native
`performance_probe.py` with an attached device.

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

Main reader/editor surfaces expose `_reader_session_id` and
`_reader_close_button`. The native bars mount this Close control in place of
Back; secondary tools, metadata and appearance routes keep Back. Inline tools
switch that same leading control to Back through `reader_tool_back` and restore
Close when dismissed. `document_dialogs.py` supplies window-modal UIKit alerts
and Android AlertDialogs: Save/discard/cancel for dirty sessions and metadata,
and destructive Delete/cancel for stored-document deletion. No close-decision
route is pushed. The iOS destructive role and Android red command text also
mark Delete in document menus. Shared document menus filter redundant
New/Open/Import/Close commands. Android's
system Back dismisses overlays/search/chapters first, then requests the same
close, including in fullscreen. UIKit's interactive pop is disabled on main
document surfaces so it cannot bypass unsaved-edit handling. Closing uses each
session owner's existing cleanup/save guards, flushes pending EPUB progress,
and retires document/close-prompt routes before restoring the retained origin
folder and viewport. Section changes continue to retain sessions.

`PrivateSessions.positions` is a bounded, memory-only cache keyed by the existing
opaque source identity. It retains page indices, EPUB offsets and supported
native text/Markdown scroll offsets after Close, without content or filenames.
Restoration occurs on the newly opened owner, with WebView scroll restoration
waiting for its load callback, pending font reflow and native drawing. Explicit private-reader clearing also clears
this cache. Imported books retain their existing durable progress policy.
Managed text sessions retain their view state in a bounded host-memory cache
for close/reopen. Tests live in `test_reader_lifecycle.py`, `test_android_back.py`,
`test_android_reader_chrome.py` and `test_reader_navigation.py`; the disposable
`reader_exit_probe.py` validates native control activation and draft guards.
`PageFooter` uses one 48-point control row for comics, EPUBs and PDFs: small
chevrons retain 48-point targets, the native track is 4 points with a 16-point
thumb, and a centered capsule badge sizes to its progress text. Comic/PDF release
commits a page; EPUB release commits a chapter, while its badge retains the
current chapter percentage. Status/error labels remain available to native
header diagnostics. `reader_progress.py` supplies the palette, reading direction and refresh registry;
commonUtils owns native slider painting.
The progress-footer native check (local artifact `test-results/mobile-evidence/2026-10-20-reader-progress.json`)
verifies all three formats on iPhone, iPad and BOOX, including scrubbing.
Imported and provider comic canvases, PDFs and images use zero
outer frame margin. UIKit reader titles use the pane width between controls
without a fixed 320-point cap. The reader-space native check (local artifact `test-results/mobile-evidence/2026-10-20-reader-space.json`)
verifies the single-row footer on iPhone, iPad and BOOX, plus full-title fit on iPad.
`reader_close_icon_probe.py` additionally checks native X artwork/labels, closing
comics, and cancel/save/discard/conflict behavior for edited documents. The
October 20 focused results (local artifact `test-results/mobile-evidence/2026-10-20-close-icon.json`) cover
iPhone/iPad simulators and a physical Android BOOX using isolated synthetic files.

Add host modules to `Python/mobile/mobile_sources.json` and feature/service modules to their owning manifests in the same change as imports. `mobile_build/tools.py` aggregates and validates these declarations.
`editor_picker.py` and `composition/assembly.py` are explicitly staged. Do not edit
generated `mobile_build/payload/` or Briefcase projects as application source.

| Contract | Tests |
| --- | --- |
| Picker ownership, cancellation, stale results, locked-source saving | `mobile_build/tests/test_editor_picker.py` |
| Provider identity, Save As verification and reopen failures | `mobile_build/tests/test_files_ui.py` |
| Private drafts, privacy handoff and delayed opens | `mobile_build/tests/test_private_sessions.py` |
| Saved-import safety, other windows and reader retirement | `mobile_build/tests/test_saved_files.py` |
| Window ownership, layout/navigation and paired panes | `mobile_build/tests/test_window_owners.py`, `test_workspace_ui.py` |
| Payload completeness and portable imports | `Python/tests/test_mobile_packaging.py`, `test_mobile_portability.py` |

Use the [host validation commands](mobile-launchers.md#host-validation).
These are host contracts. Apple/Android picker layout, native Back and real
LocalCrypt transfer behavior still need the existing native acceptance scenarios
in `mobile_build/native_tests/tests/logisticsmobile/localcrypt_checks.py`.

## Workflow controllers

The application declares its retained controller factories directly in `app.py`,
so editor navigation can resolve workflow owners without evaluating decorators.
New composition code calls these owners explicitly. The assembly decorator retains
the enumerated app accessors for existing callbacks and tests, and respects an
explicit factory rather than replacing it. Presentation contracts describe named
arguments and asynchronous return values without importing either UI toolkit.

`features/lm/mobile/controller.py` owns chat state; rclone owns cloud and transfer controllers. Host navigation workflows have dedicated `*_controller.py` modules. `services/workflow_host.py` supplies explicit read/write host attributes. `composition.assembly.composed_workflow` installs only declared compatibility names. Transfer/review cancellation is independent from file/cloud cancellation; global Cancel dispatches to both. Ownership and cancellation are exercised by `mobile_build/tests/test_workflow_ownership.py`.

## Native source editor and live Markdown

Android document chrome consumes the same `_native_reader_*` contract as
UIKit. `android_reader_chrome.py` mounts the existing buttons in a custom
ActionBar view, with symmetric title clearance, native Back and the relevant
drawer. It detaches redundant inline toolbars/workspace headers. Button-set
changes release retired native parents before reuse (including dirty/clean
Save transitions); ordinary routes clear the title and hide the document bar.
Error prompts remain visible in the native header. Locking clears its text,
accessibility descriptions and native button parents before it can be shown
again. Fullscreen restoration runs before the incoming route sets the final
bar visibility. Native List rows
on both platforms expose a visible contextual ellipsis, while retaining
tap-to-open and the platform's existing selection gesture. Recycled controls
validate their row/source identity before invoking contextual commands.
Open-only document drawers omit contextual selection controls. See the
native parity checks (local artifact `test-results/mobile-evidence/2026-10-20-chrome-parity.json`) for the
tested scope and screenshots.

The Text Editor mobile owner uses `commonUtils.ui.native.code_input.CodeInput`
for source editing and the existing offline renderer for live Markdown. Preview
is enabled by default for Markdown, stacked in compact editor allocations and
beside the source at 720 logical units of usable width. The session's existing
`markdown_split` field stores the visible/hidden choice. The separate full-page
preview remains available. Local/private editable Markdown retains its source
while previewing; remote text stays read-only.

On Android 12 and newer, `mobile.android_markdown_font` obtains the
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
`mobile_build/tests/test_markdown_font.py` covers routing, retirement, content policy,
font collection extraction and lossless WOFF tables. The isolated
`mobile_build/native_tests/tests/logisticsmobile/markdown_font_probe.py` checks actual
font loading and native glyph measurements across preview, formatted editing
and large private pages, using the device font plus serif and monospace faces.
The 2026-10-18 Note Air 5C report (local artifact `test-results/mobile-evidence/2026-10-18-markdown-font.json`)
records all nine successful Android 15 checks and the tested source hashes.

Desktop and mobile share language detection and Pygments grammars through
`formats.code_syntax`, `formats.code_blade` and `formats.code_spans`. The mobile
manifest pins Pygments 2.19.2. Native attributes/spans preserve source, selection
and keyboard ownership. CodeInput skips expensive colouring above 128 Ki
characters while retaining editing and logical line numbers. Android's
CodeEditorSupport Java bridge draws the gutter against native wrapped lines;
iOS uses a UITextView overlay with native line-fragment geometry.

The isolated iOS editor evidence (local artifact `test-results/mobile-evidence/2026-10-17-source-editor/editor.json`)
covers native typing into Markdown, a rendered table, live updates, syntax
colouring and preserved selection. The source screenshot (local artifact `test-results/mobile-evidence/2026-10-17-source-editor/source-python.png`)
and live preview screenshot (local artifact `test-results/mobile-evidence/2026-10-17-source-editor/markdown-live.png`)
use synthetic files and a separate simulator app identity. Android bridge compilation
and host editor regressions passed; this evidence does not certify physical-device
keyboards, IME/undo gestures or Android runtime editor appearance.

## Settings persistence and folder search

### Native startup progress

Primary iOS and Android startup first shows a lightweight `StartupScreen` in the
main window. `LogisticsMobile._startup_steps` yields eight real phases: private
storage, preferences, document state, editor, navigation, restored documents,
workspace and opening the workspace. The driver yields a draw turn before each
phase. Its bar counts completed phases; it does not estimate time, bytes or remote
requests. Status labels contain no document paths, filenames or credential names.
Native title bars are hidden while loading and restored before installing the
normal navigation host. The same window is reused for the ready workspace.
When last-document restoration is enabled, restart cleanup preserves the active
ordinary session while closing other clean sessions. Startup opens the active
text view or awaits its EPUB/comic reader before revealing the workspace;
session-only resources remain excluded. With restoration disabled, startup shows Home.
Home readiness does not depend on cloud storage. After the workspace is revealed,
`restore_cloud_in_background` starts the shared `start_cloud_restore` task,
preparing connection state and restoring device-saved credentials without
constructing the remote-browser or connection-settings controls. `show_cloud`
constructs those controls when needed and adopts the current loaded/busy state;
opening them during restoration shares the same task. Credential publication
refreshes Home and already constructed Documents hubs; it does not construct an
unopened Documents page. When Home's visible file summaries, sources, notices and
unlock action are unchanged, it retains its root/actions/recent-file controls and
updates credential glyphs and accessibility descriptions in place. Content changes
still rebuild Home, and retained detail routes remain untouched. Initial restore does not clear local
browser or reader state. Ordinary local browsing and local text reads can proceed
while restoration is pending. Cloud-backed reopens await restoration and validate
the saved connection identity before exposing content. Retained session-only ZIPs
still require their password. Background connection failure leaves Home usable.
On Android, a native snapshot of the final loading frame covers the attached
workspace while navigation and content receive their real viewport measurements.
A pre-draw listener waits for positive, unchanged content bounds and no pending
layout, with a workspace reflow between measured passes, before removing the
cover. It blocks taps and hides unfinished descendants from accessibility;
readiness callbacks wait for the reveal. Cancellation and failures remove the
snapshot and its listener. This handoff uses layout readiness rather than a
fixed startup delay.

Toga's `on_running` callback waits for successful initialization. Native probes
and other startup consumers must begin UI interaction there, rather than directly
after `super().startup()`. Synchronously constructed secondary iPad scene hosts
and non-native hosts retain their existing construction contract. Resize callbacks
wait until startup finishes. Closing during startup cancels initialization without
checkpointing partially built services; replacement hosts cancel an earlier
unfinished startup and tolerate missing workspace state.

Startup errors keep a generic recovery message in the loading screen and do not
report completion. Cancellation does not display a startup error. Existing iOS
reset and migration still run before preferences and document services. The system
launch screen covers the native/Python runtime boot preceding this application UI.
`test_startup_progress.py` verifies draw/work ordering, lifecycle callbacks,
failure and cancellation. The disposable `startup_progress_probe.py` captures
actual iOS/Android stages and verifies readiness and navigation after loading.

Mobile Settings saves font size, restore behavior and restart clearing on change,
alongside the existing immediate overview and Android appearance handlers.
`show_legacy_session` belongs to the running host; preference loading ignores
older persisted `show_legacy` values and saving writes its compatibility value
as false. Reloading preferences preserves the session visibility choice.

Online folder search filters the complete native bridge listing in memory;
ordinary and crypt remote listings have no entry count cap. Local providers use
the cancellable recursive search with no scan or result count cap. Mobile List
and Tiles display every matching entry in one scrolling view, without paging.
The mobile browser queues search work on its owning Toga app loop: synchronous
native text callbacks may run between cooperative asyncio dispatches and lack a
running-loop context. Search still debounces, cancels superseded queries and
restores the immediate folder listing when cleared.
`document_sources.reopen_file` wraps credential resolution and the complete open
in a compact status/activity strip below the current view, including Home/Recent
and restored credential entries. Its `finally` cleanup stops the indicator and
removes only its own strip; completion never restores an earlier view.
Local reads use the cancellable listing path
without toggling global cloud controls or refreshing the download inventory.
Folder pages are built offscreen before attachment. Local and LocalCrypt List/Tiles
views use names and generic icons, without queuing content or thumbnail reads.
Mobile file List views use `RecycledFileList`, a single bounded native scrolling
widget with lightweight source records for every sorted/filtered entry. Android
uses the app-owned `FileListView` Java `ListView`/`BaseAdapter`: `getView` binds
recycled rows, with text and icons held in Java rather than per-entry Toga
containers. Toga 0.5.7's Android `DetailedList` instead creates every row inside a
`ScrollView`, so that backend is deliberately replaced. iOS keeps Toga's
`UITableView` backend and reusable cells, with browser disclosure indicators,
middle filename truncation and full accessibility names. Native selection owns
highlighting. Android palette updates include monochrome selected-row contrast.
Both adapters draw dividers only between dataset items. iOS disables UIKit's
default separators and toggles an inset line when binding each reusable cell,
keeping filename insets unchanged for last and single-row lists. Android draws
lines by dataset position, including when the final item enters the viewport.

Local, remote, workspace drawer and Open/Save picker lists keep a bounded viewport;
none wraps the native list in an outer scroll container. The picker form has its
own scrollable area. There are no Python row-population timers or per-file Toga
buttons. Search still covers the entire source, including recursive matches;
source publication never truncates the list to the visible rows. File taps keep
the existing direct-open path. Android long press and iOS's Select swipe action
select an item for contextual commands without opening it. Each callback captures
the row's entry and render epoch; replaced snapshots and late asynchronous
selection callbacks cannot open stale files. Folder and Back behavior retains the
existing provider/navigation owners.

Only cells requested by a native viewport queue optional thumbnail work, with
bounded concurrency/pending requests and the existing bounded byte cache. Local
and LocalCrypt browsing still does not enable thumbnail content reads. Recycled
cells clear old text, accessibility descriptions and images when retired; stopping
clears the native source, selection and provider snapshot. On iOS, retirement
only clears a cell no longer associated with a table row. Every `willDisplayCell`
rebinds its text, image, disclosure, accessibility and palette from the current
source, including when the resume-password screen restores a retained window
root without another `cellForRowAtIndexPath` request. This preserves the browser
snapshot, sorting and selection instead of refetching the directory on unlock.
The commonUtils `test_native_recycled_list_ios.py` covers detached-cell redisplay and late retirement;
`test_screen_privacy.py` checks repeated password restoration of the same listing.
Tiles retain their existing shared renderer and separate scroll container.

The disposable `recycled_list_probe.py` under `mobile_build/native_tests/tests/logisticsmobile/`
uses 10,005 synthetic file records to validate native viewport bounds, scrolling
to the last result, activation, search, sorting, stale callback rejection and
clearing. It is a QA launcher only and must not replace production launchers.
Native verification evidence (local artifact `test-results/mobile-evidence/2026-10-19-recycled-file-lists.json`)
records 20 visible Android rows (40 created views while jumping to the last
entry) on a BOOX Note Air 5C and 10 visible iOS simulator cells, with complete
search, last-item activation, source replacement, visible-row thumbnails and
clearing checks. The focused 174-test host set and seven packaging tests pass;
separate pre-existing broad-suite failures were reproduced with the original
browser. These synthetic checks establish bounded UI work, not real storage
latency or full-app frame timing.
Regression coverage lives in
`mobile_build/tests/test_browser_progressive.py`, `mobile_build/tests/test_keyboard.py`,
`mobile_build/tests/test_native_browser.py`, `mobile_build/tests/test_settings_ui.py`,
`Python/tests/test_mobile_hub.py` and `mobile_build/rclone_bridge/list_test.go`.

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
selection still supports that callback. Folder navigation, selection validation
and cancellation remain in place.
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

`mobile_build/tests/test_mobile_responsiveness.py` covers deferred Settings, native tab
selection without reentry, file taps bypassing metadata, and worker-only initial
Markdown rendering. Existing browser, folder-navigation, private-session and
Android Back tests cover lifecycle behavior. Physical Android launch, filesystem
and WebView timings still require a device run. Shared syntax detection changes
are documented and tested in commonUtils, not duplicated in the host contract.

Workspace saves skip repeated durable publication only when the serialized
ordinary-session state and on-disk revision are unchanged. The revision includes
device/inode, size, nanosecond modification/change times, mode and link count.
Deletion or replacement forces a write; linked paths are still rejected before
checking the cache. Managed text recovery likewise skips publication only when
name, text, encoding, original bytes and the recovery file revision match the
last successful durable checkpoint. Missing or changed files force publication;
failed writes are retried and linked paths remain rejected. Changed drafts keep
file and directory flushes before navigation is allowed. Settings categories
checkpoint once before changing selection, including in wide layouts; compact
presentation reuses that guard. Destination selection checkpoints text first and
saves workspace state once afterward. These paths are shared by Android and iOS.
`Python/tests/test_mobile_workspace.py` covers view changes and external edits.

### BOOX file-list before/after profiling — 2026-10-19

The paired BOOX report (local artifact `test-results/mobile-evidence/2026-10-19-boox-file-list-profile.json`)
compares the original progressive browser against the recycled List renderer in
one isolated QA process on a physical Note Air 5C (Android API 35, reported
refresh rate 38 Hz). It uses production appearance hooks with normal system
appearance and synthetic in-memory records. Provider I/O, app startup and physical
E Ink pixel presentation are excluded. Each size has five alternating paired
trials after excluded warmups; cProfile runs are separate.

| Files | Original next native draw, median | Recycled next native draw, median | Ratio |
| --- | ---: | ---: | ---: |
| 40 | 2,547 ms | 74 ms | 34.2× |
| 200 | 2,523 ms | 96 ms | 26.3× |
| 1,000 | 2,536 ms | 179 ms | 14.1× |

The original renderer initially constructs 40 rows at every size. Its 200-file
cProfile points to widget construction and surface styling: 320 `paint_surface`
calls within the initial batch. Profiled times include profiler overhead and are
not used in the latency ratios. Browser-control construction remains about
250 ms for either implementation, measured separately from listing publication.

Steady-state scrolling was measured only after all 200 records were available
and the old browser had finished constructing all 200 widgets. That old
progressive construction took about 101 seconds in this run. Three trials per
implementation used identical native touch sequences. Median trial frame p50 was
137 ms original versus 145 ms recycled; median trial p95 was 172 versus 171 ms.
This does **not** demonstrate a scrolling improvement. Native fling behavior
produces different travel distances, and Android frame metrics include rendering
pipeline delays, so these results do not establish the remaining cause or a
physical E Ink refresh rate. Layout/render tracing remains necessary to diagnose
the residual scrolling lag. Do not present the listing speedup as an overall app
or scrolling speedup.

`mobile_build/native_tests/tests/logisticsmobile/boox_file_list_profile.py` is a
QA-only launcher. Stage the original browser at the report's pinned commit as
`mobile.legacy_browser_ui`, the current browser normally, and the
QA-only `android/io/github/ispaure/logisticsmobile/FileListBenchmark.java` into
the disposable app's Java source tree. The helper is not in the production
source allowlist. Results and cProfile trees are written beneath that QA app's
cache in `boox-file-list-profile/`. Local raw results, call trees and a mixed
render-tail `gfxinfo framestats` dump are retained under
`mobile_build/build/list-recycling-qa/boox-profile/`. The published JSON omits
noncomparable backing-view counts and records this instrumentation limitation.

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

`mobile_build/tests/test_folder_navigation_performance.py` covers row reuse, bounded
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
See [shared folder artwork](ui-architecture.md#shared-lockedunlocked-folder-artwork)
for the canonical desktop/mobile source and browser PNG regeneration command.
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

The disposable [performance probe](../../mobile_build/native_tests/tests/logisticsmobile/performance_probe.py)
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

Workspaces retains its root page and separate row hierarchies for Local, Cloud
and Home Server. Background discovery still snapshots native credential state on
the UI loop, coalesces worker scans and rejects retired credential generations.
Each publication reconciles the selected source: unchanged controls stay attached,
added/removed folders change only the affected hierarchy, and lock/status changes
update the existing icon and accessibility description. Callbacks resolve the
latest choices when pressed. Detached source views reconcile before mounting;
credential and visibility filters still remove unavailable entries. A remote-only
metadata change does not discard unchanged Local rows. Source and credential
selection survive returning to the page, and transfer actions are reevaluated.
Discovery errors keep the existing recovery actions and rebuild a failed page on
retry.

Offscreen Workspaces construction batches native surface painting until each
control has its final roles and metrics. Android caches resolved drawing classes,
immutable colour lists and up to 128 drawable constant-state templates. Each view
gets an independent mutated drawable; bounds, tint, pressed state and animations
are not shared. Template keys include resolved colours and pixel geometry, so
Light/Dark, E Ink and density changes cannot reuse the wrong appearance. Existing
compact icon updates preserve dimensions, padding and symbol configuration rather
than resetting the control and forcing repeated Toga layout. No persistent cache,
new credential index or row virtualization is introduced.

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
`mobile_build/build/performance-profile/android/`.


### Incremental Workspaces verification — 2026-10-20

A paired run on the same API 35 ARM64 AOSP ATD emulator uses synthetic cache-only
folders, retained metadata and no loaded credentials or network. The before build
preserves the pre-change presentation files; the after build changes only row
reconciliation and surface/icon handling. These are emulator timings, not a
physical-phone latency claim.

| Operation with 100 local folders | Before | After |
| --- | ---: | ---: |
| UI row work after a remote-only metadata change, both publications | 3,700 ms | 9.3 ms |
| Full row construction, unprofiled callback | 1,888 ms | 810 ms |
| Unchanged repeat visit callback | 16.6 ms | 10.7 ms |

The original cache discarded Local rows once against old discovery results and
again when new Remote choices arrived, even though the Local folders were
unchanged. Reconciliation retains all those native controls across both updates.
Updating all 100 lock icons in place takes 128–139 ms in this fixture. Native
checks verify retained button/icon identities and independent pressed states.
Light, Dark and E Ink before/after screenshots are pixel-identical at 1080×1920.
The 100-row profile reduces actual native background paints from 1,614 to 706;
wrapper calls that only enqueue a final paint are not counted as native paints.
The full list still constructs all its native controls on first use; recycling
large offscreen lists remains separate work. This incremental run did not include
native iOS timing or screenshots. Raw profiles, source hashes and
screenshots are retained locally in
`mobile_build/logs/workspaces-optimization-20261020/`.

## App reset boundary

`mobile.app_reset` owns reset operations. Android calls its own
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

Android collection drive discovery in `storage_ui` uses mounted `StorageVolume`
roots and the All files access grant on API 30+. On API 24–29 it uses
`Context.getExternalFilesDirs(None)` and `StorageManager.getStorageVolume(File)`
to expose mounted app-owned directories, including removable cards. These paths
support ordinary Python/native bridge file access without storage permissions;
legacy storage permission cannot authorize arbitrary removable-card writes.
No hidden APIs or guessed mount paths are used. Existing copy/verify, location
markers and missing-card checks apply to the selected app directory. Android
removes these directories on uninstall or clearing app data, so legacy storage
UI and guides call out the backup requirement. `test_android_storage.py` checks
strict API 24/28/29 and API 30/35 surfaces; storage UI tests cover a permission-free
copy and preservation of the original files. These are host checks, not physical
Android 9 SD-card validation.

The app-only UserDefaults reset is declared with CA92.1 in
`mobile_build/privacy/App.xcprivacy`, copied as a target resource before signing and
verified in exported apps. Platform API references:
[Android clearApplicationUserData](https://developer.android.com/reference/android/app/ActivityManager#clearApplicationUserData())
and [Apple Keychain deletion](https://developer.apple.com/documentation/security/secitemdelete(_:)).

## Transfer details and reader actions

Document transfer shortcuts share the native reader action groups on iPhone and
Android. `reader_chrome.reader_buttons` adds a compact percentage/details button;
the transfer controller omits inline banners from views declaring native reader
controls. Its `MobileHostUI.refresh_transfer_chrome` hook updates visible labels
without rebuilding native groups for each progress snapshot. Visibility changes
reflow the action groups, and fullscreen follows the reader chrome. Successful
completion dismisses after five seconds with an epoch guard so a later transfer
cannot be dismissed by an earlier completion callback. Stopped transfers persist.

Transfer details and their settings use the current destination's route stack,
so redraws do not create a cross-tab return edge. Their Back action pops the route
without cancelling transfer work. Remote opening entry points (browser, retained
sessions and Recent references) surface connection-busy decisions with a native
dialog. Feature menus resolve the native activity through the reader controller's
host and dispatch presentation commands during transfers; operation-specific
guards still own mutations and credential requests. Regression coverage is in
`mobile_build/tests/test_transfer_feedback.py`; the physical Android acceptance probe is
`mobile_build/native_tests/tests/logisticsmobile/transfer_feedback_probe.py`.

## Unified iOS local browsing

Credential restore, replacement and lock cleanup retain ordinary local provider
roots, rows and in-flight listings. They remove private roots and retire private
browser state. This also protects a cold Local files entry while initial
credential restoration finishes on Android or iOS.
UIKit scene activation can also arrive while the startup window is still being
built. Scene callbacks record activity immediately and dispatch privacy/focus
handlers only after the privacy owner exists.

The local browser presents one On this device source. `SharedFiles` lists the
iOS Documents root and exposes its `Local` child with the display name Collection.
`FilesUI.browser_file_location` routes that child and its descendants into the
existing CollectionFiles provider; Parent at the collection root returns to
Documents. The outer provider rejects direct entry access to Local so root mutations
cannot rename or remove the managed collection; recursive search can list its
contents. Internal Local files and Shared
files location identities remain distinct for existing pins, managed workflows,
provider documents and history, but share one source control. No storage migration
is involved; Android's collection root is unchanged.

## Per-format mobile text sizing

`mobile.font_scaling` binds native iOS and Android pinch gestures to
`markdown_font_size`, `text_font_size` and `epub_font_size` (12–32). Preferences
seed missing category sizes from the legacy `font_size` and preserve them on the
next save. Settings and gestures refresh registered surfaces in place, including
provider readers; WebViews reflow their DOM without replacing editor contents.
EPUB reflow uses the existing resize bridge to retain its text anchor.

`markdown_justify` and `epub_justify` are independent validated Boolean strings,
defaulting to `false`. The same registered WebView bindings apply them through
the `--logistics-text-align` CSS variable and dispatch resize without reloading
the document. Markdown preview and formatted editor CSS target paragraphs and
list items; native source inputs keep their platform alignment. EPUB's portable
typography options include `justify` for initial chapter rendering and the
in-reader appearance form saves the same preference as Settings. Settings reload
discards stale switch references and rebuilds the categories lazily.

## October 20 ownership cleanup

Books and Comics now own imported/provider format controllers, and Books owns
mixed library presentation and its portable metadata index. Text Editor owns the
mobile Notes Library browser. The host composes explicit presentation services
in `composition/presentation.py` and keeps storage/provider discovery, workspace identities,
credentials and private publication. Reader and private-session compatibility
accessors delegate format state to its owning controller; prepared view handoff
uses setters so state cannot bypass these owners.

Comic folder batch plans/views are owned by a composed feature controller.
Generic speech, private WebView and image-header mechanisms live in commonUtils;
voice preferences, media privacy gates and document routing remain here. Native
payload allowlists include all moved modules and explicitly stage new shared
modules in dirty local development payloads. See the
[ownership audit and implementation status](ownership-audit.md).

## Application shutdown and disposable resources

`application_lifecycle.HostLifecycle` owns application exit vetoes, host replacement
and memory-pressure resource release. Replacement preparation flushes documents,
credential lists and chat before retiring callbacks; async model loading and final
retirement share that preparation once. Failed chat preservation leaves the old
host active for retry. Replacement disposal and successful exit are idempotent;
memory trimming remains repeatable and preserves the current speech owner. `LogisticsMobile` delegates its
existing callbacks to this module, so startup cancellation, active transfers,
private documents and native callback signatures keep their existing behavior.
`reader_lifecycle.py` still owns individual document exit/Back behavior. Host tests
include `test_application_lifecycle.py`, startup progress, reset, private sessions,
LocalCrypt and speech media.

## Provider presentation assembly

`provider_presentation.py` builds the provider reader chrome only after the session
owner opens a document. `provider_document.ProviderDocumentSession` owns the current reader and metadata
draft state and disposes its format resources after the busy/dirty guards accept
closure. Compatibility attributes on the controller forward to this session;
repeated disposal is harmless, and adopting a reader starts a new lifetime.
`provider_opening.ProviderDocumentOpening` owns document preparation, credential
identity checks, cancellation and publication, with
`provider_view.ProviderDocumentView` constructing the unpublished controls. Each
`ProviderDocumentSession` retains its opening owner. `provider_ui.py` retains
close/save and other session commands; Books, Comics and Markdown controllers retain
format navigation. The `compact_private_view` host callback remains compatible.
Private-session, provider-Markdown and reader-chrome tests cover the assembly.
Native visual behavior still requires the relevant native acceptance scenarios.

## Sleep, memory trimming and visible library readers

`ScreenPrivacy.resume_reader` checks both provider sessions and imported-library
readers after wake or successful unlock. A `ReaderController` remembers the
reading/control mode before releasing its decoder, then schedules one recovery
task to reopen the saved page/passage in the retained route. Workspace tokens,
visible-owner identity and privacy checks prevent a queued task from reopening a
closed/hidden document or bypassing a lock. No archive password is retained for
this recovery; existing password prompts remain authoritative.

Android can queue a memory-pressure callback until after its Activity resume
notification. `application_lifecycle.release_disposable_resources` therefore
requests the same guarded recovery after trimming. While inactive or locked it
stays deferred; once visible and unlocked a late trim cannot strand an empty page.
This also uses the existing provider-reader recovery for PDF/comic surfaces.

`test_reader_sessions.py` covers ordinary comic/EPUB restoration, duplicate wake
signals, a close or navigation racing recovery, and trim arriving after reveal.
`reader_resume_probe.py` supplies an isolated synthetic native app. With that APK
installed under `io.github.ispaure.logisticsreaderresumeqa`, run:

```sh
python3 mobile_build/reader_resume_tools.py --adb /path/to/sdk/platform-tools/adb --device emulator-5580 --output mobile_build/logs/reader-resume
```

The driver requires an explicit emulator and never targets a physical Boox or the
main app. It exercises HOME/background, screen off, an injected native memory
callback, screen on and Activity resume. The library cases additionally queue a
trim through the normal memory subscription after wake. Reports distinguish these
orderings; screenshots and logs stay under ignored `mobile_build/logs/`. Keep simulator
or emulator evidence distinct from physical Boox/E Ink acceptance.

## Composition and explicit host capabilities

`composition.assembly.composed_workflow` installs only the controller's enumerated
`METHODS` and `FIELDS` as compatibility accessors and constructs that owner lazily.
`services.workflow_host.HostService` is a read-only application capability;
`HostAttribute` is writable by default, and `StateAttribute` targets an explicit
owned record. A missing attribute raises normally; there is no catch-all app
fallback. Add a service or writable state field deliberately instead of broadening
a feature controller's access to the host.

`composition.presentation` assembles rclone, Notes, library, speech, reader and
file-operation presentation callbacks. Feature adapters receive these ports and
remain independent of the mobile application import. Register new source owners
in the owning mobile manifests; generated payload copies are not implementation
files. `test_composition_contracts`, workflow ownership and feature-boundary checks
exercise composition, and staged startup checks catch omitted modules.

## Session transition decisions

`session_workflows.transitions.SessionTransitions` is the orchestration owner for
Close, reader Back/return and host-preservation checkpoints. `prepare` captures a
session key, provider and workspace token in `CloseDecision`; `commit` rejects a
missing, cancelled or stale decision before invoking the source adapter. Its
`CloseResult.committed` reports whether closure actually completed. A failed save
or veto must stop later removal/navigation.

`session_workflows.adapters` retains distinct managed-text, library, provider,
Notes Library and credential-reference close behavior. Model persistence, private
draft rules and writer ownership stay with their sources. Async dirty-dialog
answers capture the workspace token before opening and revalidate it plus the
active host before Save/Discard. A surviving session ID alone is insufficient.
Busy-reader exits await pending operations without releasing their owner early.
`HostLifecycle` delegates replacement/exit preservation to this coordinator;
reader/session facade methods keep their existing host call signatures.

`EditorPicker` separately captures the originating managed/provider document for
Save As. Cancel or native dismissal restores that origin, including a new draft,
without selecting an unrelated previously opened provider document.
Focused coverage includes `test_session_transitions`, `test_reader_lifecycle`,
`test_private_sessions`, `test_application_lifecycle` and `test_editor_picker`.

## Reader publication boundary

`reading.publication.ReadingPublication` coordinates outgoing animation capture,
prepared-surface mount, retirement and footer/chrome refresh for library and
provider readers. `reading.sources` captures source-specific validity: library
reader/epoch or provider reader/workspace token, plus active-host checks.
Formats retain decoding, page targets, reading progress and private-source policy.

Use the `preparing(direction)` scope around view preparation. It releases outgoing
animation snapshots even if construction fails or is cancelled. `mount` checks
validity again, disposes an obsolete unmounted disposable surface, and retires
replaced surfaces only on the accepted publication path. Failure before mounting
retains the displayed view; later mount exceptions abort animation cleanup but
are not a transactional rollback of arbitrary host callbacks or disposed views.
Footer/chrome updates also reject stale ownership. Library/provider format swaps
and forced view-preparation failure recovery require native checks in addition
to focused host tests such as `test_reading_publication`.

## Settings implementation owners

`settings.navigation.SettingsNavigation` owns compact routes, retained wide panes
and per-window selection. Its `SettingsPages` mapping builds each category only on
first access. `SettingsCategories` constructs application controls;
`settings.forms` owns shared rows and connection forms, `settings.speech` owns
voice controls, and `settings.information` builds installed-version/help content.
The old `settings_ui.py` module is removed; use canonical imports and patch targets.
Connection adapters receive the existing `ConnectionPresentation` callbacks from
composition. Reload discards stale widget references and recreates categories
lazily; preference keys and storage remain unchanged. Settings navigation/UI,
connection and isolated-payload checks cover these boundaries.

### Readable startup and reader assembly

`app._startup_steps()` names the eight startup phases with `startup.StartupPhase`.
It still yields each existing progress label before its work; asynchronous model
loading remains between the preferences yield and the preferences phase. Explicit
phase results carry the storage root, prepared models and restored document.

`provider_presentation` chooses actions, builds PDF tools, and mounts reader/editor
surfaces in separate functions. The private session owner still supplies validity,
credentials and disposal. `folder_hub.folder_row_presentation` computes labels and
lock state without widgets; tab reconciliation retains native row identity.
Appearance installation dispatches to separate iOS/Android installers, retaining
process-wide installation guards and the existing backend hooks.

### Trace a document or cancellation

- **Reopen a file:** `document_sources.reopen_file` owns the temporary loading
  panel. `_reopen_file` resolves the current source/credentials before asking the
  app to open it. Provider documents enter `PrivateSessions.open`, which captures
  workspace/navigation identity. The session owns bytes and format resources;
  presentation assembly runs after admission, and a stale completion cannot take
  over a newer route.
- **Navigate during a listing:** `FolderListing.begin` cancels the previous read
  and captures context/credential identity. `capture` retains provider, folder and
  location. `read` checks `accepts` before and after worker I/O; invalid results are
  discarded. Hosts still own navigation, control state and provider retirement.
- **Cancel a transfer:** the transfer controller owns its cancellation event and
  active review close callback. File/cloud work owns a different event. Global
  Cancel reaches both owners; cancelling only a transfer must not cancel an
  independent file operation. Review approval remains a captured session decision.
- **Replace or close a host:** session transitions preserve/checkpoint state before
  accepting removal. `HostLifecycle.prepare_replacement` preserves durable state
  before background model loading; `retire_for_replacement` retires callbacks,
  invalidates sessions and disposes resources once. A veto leaves the document
  and controls usable. Shared worker cancellation alone does not prove retirement.
