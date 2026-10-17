# Native navigation foundation evidence

Milestone 0 introduces a reusable native host and isolated proof fixtures. The
normal application shell is migrated in milestone 1; passing this proof alone
does not change the normal launch screen.

The shared Python `NavigationState` owns destination IDs and independent routes.
`commonUtils.ui.native.navigation` now isolates backend access, following the
local architecture cleanup. Toga 0.5.7 and Briefcase 0.4.5
remain pinned. Android explicitly depends on Material 1.12.0. Apple builds select
an installed iOS 27.1 SDK or newer to opt into Duo bar adaptation, retaining the
declared iOS 15 minimum and guarding newer controller APIs.

## Local evidence

The native suite retains all existing feature cases and adds
`native_navigation_foundation`, for 16 required cases. Local reports and
screenshots are retained under ignored `Mobile/logs/navigation/` directories.
Reports record the staged source fingerprint; lifecycle reports refer to the
proof revision they exercised rather than claiming to cover later edits.

| Target | Evidence |
| --- | --- |
| iPhone 17 Pro, iOS 26.5 | 16 native cases; native tabs, folder push/pop, fallback bars, draft preservation and widget registry cleanup |
| iPhone Duo, iOS 27.1 | 16 native cases; system-managed bar adaptation; five lifecycle cases covering rotation, background/resume and process recovery |
| iPad Pro 11, iOS 27.0 | 16 native cases; regular-width native split composition with an uncollapsed detail pane |
| Android 15 emulator | 16 native cases; Material bottom navigation and rail, direct native selection callbacks, focus and cleanup |
| Android 15 resized emulator | Nine lifecycle cases spanning phone, keyboard, portrait/landscape tablet, Activity recreation and process restart |

The Android tablet profile approximates BOOX Air 5C dimensions/density. Physical
BOOX hardware, E Ink refresh, stylus behavior, real fold gestures and independent
OS windows remain unverified. The legacy bar path was forced on available Apple
runtimes; an iOS 15 runtime was unavailable.

## Integration decisions

Apple uses managed UIKit containment with a navigation controller per destination.
Window bounds and all safe-area edges replace Toga's main-screen/status-bar
assumptions. Modern tab/sidebar mode is availability guarded. The split proof
uses a presented full-screen controller; milestone 2 must integrate the enduring
workspace composition, rather than treating this fixture as the final workspace.

Android assigns unique destination menu IDs and handles selection before the
Material control commits its checked item. A themed native rail replaces bottom
navigation at 600 dp of measured window width. Resize and keyboard padding use
actual content bounds. Activity recreation re-enters the Python application;
durable draft state is therefore essential, rather than relying on widget survival.

Adapters restore replaced callbacks and containment on disposal. Native tests
assert main-thread execution and exact Toga widget registry cleanup. Lifecycle
reports include process memory snapshots (roughly 90–110 MiB Android PSS and
322–360 MB Apple peak RSS in these instrumented fixtures). These measurements
are a baseline, not proof of bounded reader caches or absence of native leaks.
Reader integration will permit one decoded current page and one prefetched page
per visible reader, releasing them when its view detaches; concurrent decoded
pages must be capped by byte size as well as count.

The proof uses synthetic drafts and a dedicated cache directory. It does not
claim native document picker coverage or persist private plaintext sessions.
Reproduction commands and restoration of the ordinary launcher are documented
in `docs/development/mobile-launchers.md`.


## Phase 0 completion checkpoint (October 14, 2026)

The actual app now implements the first navigation/document deliverable. The
numbered resume commits add explicit dirty-close choices, safe discard against
current saved bytes, per-document Edit/Preview continuity, callback ownership,
and unavailable-resource Retry/Remove routes. Both native suites passed all 18
cases at `55a9310` (Phase 0 Part 5), including the expanded text-workspace and
preview cases, plus contrast assertions for inactive Android icons and labels.
The normal iOS and Android launchers also build and launch independently of
test mode. The 45 mobile dummy/tooling tests and 32 portable
document/workspace/reader/privacy tests pass. Release tooling tests also pass
(17 cases, one platform-specific skip).

Exact reports are retained as `mobile-evidence/2026-10-14-phase0-*-native-ui-local.json`.
They share staged fingerprint
`3d1130bfbba3a1e051c93fd36690c22a071300d127dc08b7721b91f773833ca7`.
These are local development reports: their dirty marker includes preserved,
unrelated deployment/TestFlight work. They are not substituted for clean
automated release evidence. Phase 0 Part 6 changes only documentation and
release-note validation, so the recorded application revision remains explicit.
Earlier lifecycle reports remain evidence for the revisions they exercised.
The physical-device and minimum-runtime limitations above still apply.

The release publisher optionally uses a tag-specific Markdown file in
`.github/release-notes/` for the release title and description; otherwise it keeps
generated notes. Existing releases/assets retain their no-overwrite protection,
and the validation/build/runtime gates still precede publication.

## Guided remote copies

`features.rclone.mobile.copy_ui.CopyUI` owns the remote-to-device destination route.
It snapshots the client, credential generation and selected row before presenting
an app-managed LocalFiles folder picker. Connection changes refuse the transfer.
The browser exposes separate selected-item and current-folder copy actions because
folder taps navigate immediately. Local storage selection and parent navigation
are primary controls; storage changes open the root. No remote write API is added.

`folder_download.pull_item` stages files, flushes them and publishes with an
exclusive hard link; staging removal leaves one independent destination file.
Collisions produce a new copy name. Folder transfers reuse the existing staged
folder pull. Cancellation, authentication failure and credential changes before
publication remove staging. The native descriptor is sampled every 200 ms on a
worker to report bytes without changing the bridge ABI. UI progress is dispatched
on the event loop; the bar measures the current file, stays animated for unknown
sizes, and completes only after publication. Folder status also counts completed
files. `Mobile/tests/test_copy_ui.py` covers destination browsing, collisions,
source generation changes, retry, cancellation and progress using the dummy host;
these checks are not physical iOS/Android interaction evidence.

## Native launch panels and per-editor search

`hub_ui.py` builds Home and Documents icon panels over the existing session and
file-picker commands. `hub_icons.py` embeds small PNG line icons, decoded by Toga
without a runtime imaging dependency. Home reflows at 700/1100 points; Documents
keeps one column for the existing native list/detail sidebar. Root refreshes on
destination selection do not replace retained detail routes or activate another
session. New from a hub explicitly displays the newly created editor.

`editor_search.py` owns literal Find/Replace widgets per `TextEditorView`. Native
selection converts Python offsets into UTF-16 offsets on Apple and Android.
Replacement updates the existing text widget and draft checkpoint path; it does
not write through a separate persistence path. Queries and replacement strings
are memory-only and are not added to the workspace manifest. Host tests cover
Continue ownership/preview, new-document draft retention, wrapped Unicode search,
literal replacement and independent editor queries. These checks do not certify
physical keyboard or layout behavior.


## Local mobile Folder Hub and embedded sync changes (2026-10-14)

The mobile payload includes `configFile.ini` and portable `services.folder_policy`;
desktop and mobile share the exclusion parser and dash naming helper. No desktop
configuration singleton or Qt dependency is admitted to the payload. INI bytes are
included in the source digest. Folder Hub aggregates actual private folders,
transfer mappings, loaded remotes and nonsecret ZIP/remote associations from the
existing mobile preferences INI. Loaded crypt connections alone are not local
copies; browsing/discovery does not instantiate empty crypt namespaces.

Managed transfers call native `mirror_sync`, which wraps rclone `fs/sync.Sync`
with an admitted connection, validated private local directory, connection identity,
selected remote prefix and explicit direction. Crypt-to-Local uses rclone's crypt
filesystem; LocalCrypt uses its backing ciphertext scope. No backup directory or
suffix is configured. Push review inventories both sides and shows removals;
changed local or remote inventory invalidates the review. Cancellation leaves
completed destination changes and retains the mapping for retry. Normal transfers
create no snapshots/staging copies; old publication journals and snapshots retain
compatibility recovery/read support. Rclone filesystem caches are cleared when
credentials change. A transfer-specific accounting group supplies byte progress.

Local folder deletion reuses shared provider inventory/delete operations and
removes the mapping after successful deletion. Existing unrelated changes remain
in the checkout. These changes have host/native-library regression coverage;
installed iOS/Android visual and network behavior needs a freshly rebuilt app.


## Complete simulator test results

The disposable native test app atomically writes `logistics-native-ui-result.json`
in its cache before printing the chunked stdout report. `ui_tools.py` can read that
file through `simctl get_app_container` when Apple's log stream drops the final
chunks/exit marker. It accepts only a file written after that invocation started
and applies the same full-case, backend, clean-source and exact-commit checks as
stdout. Independent-window verification remains mandatory for the iPad gate.
Briefcase's missing-result code 200 can use that verified file; other process
failures, stale/missing files, incomplete cases and failed tests still block the
release. Android continues to use its stdout report. The host preserves the
chosen report transport and Briefcase exit code beside the native evidence.
