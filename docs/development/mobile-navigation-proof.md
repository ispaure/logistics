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

### Shared native-owner lifecycle checks (2026-10-23)

`mobile_build/native_tests/tests/logisticsmobile/native_lifecycle_probe.py` is an
isolated Toga entry point using synthetic image/text content. Stage it as the
test app's `logisticsmobile.app` with current commonUtils and its Android Java
sources. Its `main()` returns the Toga app. Keep the existing launcher calling
`main().main_loop()`, use bundle/application ID
`io.github.ispaure.logisticsnativelifecycle`, and retain the Android speech-service
queries. Never install this fixture over the main app. The probe uses the same
shared cooperative-loop binding as the Logistics host.

The Android fixture additionally handles `density|smallestScreenSize` configuration
changes in its Activity manifest. These flags belong to the isolated fixture:
the driver changes emulator density/size while testing an installed native owner.
It must not restart the Activity and silently test an obsolete Python task. Each
checkpoint checks the current Activity, and the driver requires one probe UUID
and PID throughout the run. This does not validate Activity recreation/recovery.

After installing the isolated app on a dedicated target, run:

```sh
python3 mobile_build/validation/native_lifecycle_tools.py ios \
  --device SIMULATOR_UUID --output test-results/native-lifecycle
python3 mobile_build/validation/native_lifecycle_tools.py android \
  --device emulator-PORT --output test-results/native-lifecycle
```

The driver rejects physical Android serials, switches the live app through
background/foreground at navigation, canvas and speech checkpoints, and restores
Android display overrides in `finally`. Reports retain native backend identity,
loaded source/bytecode fingerprints, run UUID, callbacks and external checkpoints.
Save evidence before uninstalling the isolated app; preserve the main package.

Local runs on an iPhone 18 Pro / iOS 27.0 simulator and an Android 15 / API 35
emulator pass three cycles per component: navigation installation, chrome
restoration, uninstallation/reinstallation and retired callbacks; image zoom/fit,
native gesture handlers, pixel/listener cleanup and repeated disposal; and native
offline speech callbacks, stop/restart, close and suppression of late deliveries.
The iOS canvas also creates a native magnifier and checks its pixel cleanup.
Android additionally crosses phone, tablet rail and landscape allocations while
keeping the Activity and selected destination. Both platforms observe actual
background/foreground callbacks while each owner is live.

The baseline reproduced failed navigation admission retaining host/native state
and speech closure retaining presentation callbacks. Further native checks caught
Android resize wrapper identity/argument errors and programmatic tab selection
leaking through install/uninstall. Shared fixes preserve paired retirement and
selection without moving native factories. The image canvas required no runtime
change. Host native contracts, mobile navigation/speech checks and lint pass.

This focused pass does not certify physical-device touch/pinch/pan, audible output,
system audio interruption, IME restoration, iPad independent windows, Activity
recreation or minimum-version OS behavior. Keep those acceptance gates separate;
the fixture's UIKit selector/Java listener calls are not finger-driven gestures.

### Full-host IME, scenes and Activity recreation

The follow-up `native_host_lifecycle_probe.py` uses the actual Logistics startup,
document editors, scene manager and replacement workflow. It runs under the
separate bundle `io.github.ispaure.logisticslifecyclecontinuation` with synthetic
drafts in that package's cache. Stage current sources and native Java using the
normal mobile source manifests, copy the tracked native fixtures into the app's
`tests` package, and set its launcher to:

```python
from tests.logisticsmobile.native_host_lifecycle_probe import main
main().main_loop()
```

Keep the normal Android Activity configuration flags; this probe calls actual
`Activity.recreate()` rather than simulating replacement. Keep the normal iOS
scene configuration and native `LogisticsSceneAppDelegate` launcher. Use an iPad
simulator for the independent-window cases. After installing the separate QA app:

```sh
python3 mobile_build/validation/native_host_lifecycle_tools.py ios \
  --device IPAD_SIMULATOR_UUID --output test-results/native-host-ios
python3 mobile_build/validation/native_host_lifecycle_tools.py android \
  --device emulator-PORT --output test-results/native-host-android
```

The driver preserves success/failure reports, progress, recreation history and
fault diagnostics before uninstalling only that QA package. It rejects physical
Android serials and restores the temporary software-keyboard preference in
`finally`. The main app and its data remain separate. Reports fingerprint the
loaded shared navigation and application-lifecycle code.
Acceptance also requires the probe's direct Python-stderr capture marker and no
swallowed handler/task errors; Android's process log is checked as well. The
separate `host-validation.json` records driver acceptance without rewriting the
native report, so a malformed or error-bearing native success cannot pass.

Native iOS 27.0 / iPad Pro 11-inch checks cover three IME cycles per editor,
restored insets and Home/document tab visibility, and three independent secondary
window close/reopen cycles. Each cycle verifies separate editors/routes, duplicate
writer exclusion, saved text/destination restoration, keyboard ownership transfer
from primary to child and back, and suppression of retired key/scene callbacks.
The baseline retained a 320-point inset on the inactive primary scene. Shared
navigation now reconciles scene activation in addition to per-scene key windows.

Native Android 15 / API 35 checks cover portrait and short-landscape IME/chrome
restoration, then three real Activity recreations in one process. Four distinct
Activity/probe identities preserve draft identity and text. Deliberately retained
old hosts must have inactive navigation adapters and removed selection/Back
callbacks; late resize delivery is replayed after retirement. The baseline left
old navigation installed. `HostLifecycle` now retires native presentation owners
after preserving durable state, and retired hosts ignore late window-resize
callbacks even when Toga already queued them. Host regression/driver tests cover preservation
vetoes, ordered/idempotent retirement, failed evidence capture and QA cleanup.

The simulator retained an inactive secondary scene in UIKit's `openSessions`
without reporting an error after a destruction request. Successful close/reopen
coverage uses the app's active-window closure path; inactive-session destruction
and original-launch-scene destruction remain unverified. This pass also does not
certify process-death restoration, floating/hardware keyboards, physical devices
or minimum-version OS behavior. Raw evidence stays in ignored test results.

### Normal startup and saved-workspace audit

The iOS startup audit uses the normal app storage paths rather than overriding
`storage_root`. It checks legacy migration with an unsaved draft, grouped shared
folders, connection pages, file browsing, chat setup, documentation, and EPUB,
comic and PDF opening. Existing dash-separated shared folders reproduced a cold
startup failure in `tree_anchor`: Rubicon returned a callable UIKit
`intrinsicContentSize` getter. The application now accepts both callable and
property forms without changing folder contents or saved documents.

The full native suite saves its complete exception traceback in the disposable
test app's cache. Its LocalCrypt navigation check awaits the production browser
entry point rather than racing a picker-triggered listing against another manual
listing. Neither diagnostic path is included in the normal app launcher.

### iOS destination icon retention

The application retains destination artwork in each Toga `OptionItem.icon`.
Assigning only the native tab item's image leaves Toga's icon empty; rebuilding
that item after a title update restores its default star. Logistics renders its
UIKit symbols and Workspaces artwork into small, regenerated cache PNGs and
assigns real Toga icons before refreshing the native items. The cached artwork
contains no user content and keeps template tinting for selected and dark states.

`mobile_build/native_tests/tests/logisticsmobile/tab_icons_probe.py` reproduces the
original stars by reapplying tab titles, then checks native images against their
retained icons through title/icon reconstruction, destination switches, and light
and dark appearance. Local iPhone and iPad simulator runs on 2026-10-18 passed all
nine snapshots; the original implementation reproduced five stars. These checks
do not claim physical-device access.

The native suite retains all existing feature cases and adds
`native_navigation_foundation`, for 16 required cases. Local reports and
screenshots are retained under ignored `mobile_build/logs/navigation/` directories.
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

Exact reports are retained as `test-results/mobile-evidence/2026-10-14-phase0-*-native-ui-local.json`.
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
files. `mobile_build/tests/test_copy_ui.py` covers destination browsing, collisions,
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


## Local mobile Workspaces and embedded sync changes (2026-10-14)

The mobile payload includes `configFile.ini` and portable `services.folders.policy`;
desktop and mobile share the exclusion parser and dash naming helper. No desktop
configuration singleton or Qt dependency is admitted to the payload. INI bytes are
included in the source digest. Workspaces aggregates actual private folders,
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

Readers opened from Files use the Documents navigation stack and retain their
Files origin on both platforms. Popping reader tools keeps the reader visible;
popping the reader returns to the retained file browser, including its viewport.
UIKit delegate pops and explicit Back follow the same origin policy. Readers
opened inside Documents return to that tab's root.

The iOS reader uses constrained native stacks with equal-width controls so
widget refreshes cannot collapse their frames onto one another. Independent
actions have separate glass backgrounds; adjacent comic previous/next controls
share a stack. App-painted button fills are removed inside UIKit bar backgrounds,
including on appearance refresh. Screenshot checks assert visible controls'
spacing and minimum width after layout.

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
