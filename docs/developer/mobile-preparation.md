# Mobile document host and validation

## Launcher artwork

`Mobile/resources/icons` contains pre-sized PNGs derived from the supplied light,
dark and monochrome artwork. iOS uses 20–180 pixel legacy slots and 1024 pixel
light/dark/tinted slots. Android uses 48–192 pixel legacy icons and 108–432 pixel
adaptive layers, with night-qualified artwork and API 33 monochrome resources.
Adaptive foregrounds include padding to retain the complete supplied tile within
the launcher mask. Android launchers control whether night/themed icons refresh.

`Mobile/icon_build.py` installs these resources from `cloud_build.py` after
Briefcase create/update, including device deployments and isolated TestFlight
archives. It also replaces the template launch artwork. Build-time installation
uses only the standard library; Pillow is needed only for asset regeneration:

```sh
Mobile/.venv/bin/python Mobile/icon_build.py /path/to/light.png /path/to/dark.png /path/to/monochrome.png
```

Regeneration downsamples the complete square images with Lanczos filtering,
without cropping or retouching. iOS copies flatten transparency over matching
white/navy backing because app icons must be opaque. Android's separate themed
mask converts inverse grayscale luminance, multiplied by source alpha, to opacity;
this retains the original shading when the launcher supplies its tint. Original
downloads are not changed. Native launchers apply their own final icon masks.

Verify catalog and resource installation with `Mobile/tests/test_icon_build.py`.
Compile the generated iOS catalog with Xcode's asset compiler when changing its
appearance slots. Home-screen appearance and launcher cache refresh still need
device validation; host tests do not establish those behaviors.

## Native destination routes

The mobile host uses Home, Files, Documents and Settings, with independent screen
stacks in shared Python navigation state. `commonUtils.ui.native.routes` retains screen views while
changing destinations. UIKit owns the Apple navigation controllers and reports
completed pops through a lifecycle-owned delegate. Android uses a small tracked
`NavigationBack.java` bridge to AndroidX `OnBackPressedDispatcher`, enabled only
when the current destination has a screen to return from. It is registered to
the Activity lifecycle and removed when a host detaches. No Java key-event
override or generated Activity edit is required.

Android source inclusion lives in Briefcase's tracked Gradle configuration;
recreate the generated Android project when changing that configuration. Back
returns through screens; document close and private save/discard remain separate
operations. The native suite includes actual native pop/dispatcher checks.

This uses [Android's recommended Back dispatcher](https://developer.android.com/guide/navigation/custom-back/predictive-back-gesture).
Custom interactive in-app predictive animations are not yet implemented.

## Shared document workspace

`workspace.py` is a platform-independent identity and lifetime registry. It bounds
the ordinary versioned manifest to 64 KiB and 32 items, stores managed UUIDs and
whitelisted view positions/mode, and omits transient resources and all titles.
Malformed manifests are preserved and cannot be silently overwritten. Existing
DocumentStore UUIDs, recovery records, encodings and conflict checks remain the
owners of text bytes; legacy last-document selection migrates when no workspace
selection exists.

`editors.py` owns a native editor per text session. Change callbacks capture that
owner rather than the app's current selection. The app retains compatibility
aliases for existing feature controllers. Asynchronous import/export captures its
origin and rejects UI completion after that session closes; a background import
does not switch a different active document. Closed ordinary drafts remain stored.
Session generations prevent late results from reviving closed or invalidated
resources. `workspace_navigation.py` supplies the active adaptive presentation
inside the existing native destination/Back stacks on both Apple and Android.
It replaces the earlier Documents-only native split installation from
`adaptive_workspace.py`. At 640 points/dp it can place a browser or retained text
editor beside the current document, in equal halves. Compact windows show a
full-height drawer or the current document. A Material rail starts separately at
600 dp. Resizing never closes a session. `action_menu.py` isolates native editor
command presentation and rebinds commands to their editor owner.

A replacement host for the same app-private root retires its predecessor,
invalidates old session generations and cancels pending private file work. This
is the single-workspace Activity-recreation contract; independent OS windows
require a separate writer/scene ownership model before enabling them.

The --workspace mode of Mobile/navigation_tools.py drives the actual app, rather
than the minimal foundation fixture. Local matrices passed two-draft keyboard,
phone/tablet resize, Activity recreation and restart on Android, and rotation,
background/resume and restart on Duo and iPad. Physical BOOX, real fold gestures,
iOS 15 runtime interaction and accessibility/device touch checks remain unverified.

Logistics has an independent native text/Markdown prototype in
`Python/logisticsmobile`, with Briefcase configuration and tooling under
[`Mobile/`](../../Mobile/README.md). The desktop Qt launcher and its dependency
pins remain separate. The shared Qt facade retains its desktop capability gate:
the mobile host uses Toga and portable commonUtils persistence rather than
importing desktop initialization, menus or dialogs.

The proposed [native navigation and open documents plan](mobile-navigation-plan.md)
defines the next UI architecture for iPhone, iPhone Duo, iPad and Android.
Its milestones describe future work; the contracts and evidence below describe
the existing implementation and its development history.

## Ownership and contracts

| Module | Contract |
| --- | --- |
| `documents.py` | Explicit absolute app-private root; UUID file identities; 1 MiB bounded Unicode text; original encoding/endings; exclusive creation, atomic saves and recovery JSON; stale/deleted-file rejection and safe copies |
| `access.py` | Scoped binary imports; Android content URIs are handled by ContentResolver streams; iOS URLs retain security-scoped access until reading finishes; every handle/scope is closed on failure |
| `pickers.py` | Android ACTION_OPEN_DOCUMENT and iOS UIDocumentPicker open mode; native grants are consumed immediately to import a private copy; no broad storage permission or persisted external write access |
| `app.py` | Native Home/Documents/Settings shell; selection, title editing, multiline text, New/Import/Save/copy/export/preview; checkpoints on edit, focus loss and normal exit |
| `preferences.py` | Immutable defaults and bounded private INI; validation, atomic replace, malformed-file preservation and concurrent-edit rejection |
| `preview.py` | Bounded basic Markdown HTML; escaped raw input, inert links and offline CSP |
| `smoke.py` | Fresh-interpreter desktop-dependency rejection, real runtime identity, exact test inventory and structured evidence |
| `Mobile/tools.py` | Whitelisted Logistics sources, tracked/clean shared Python sources, licenses, source SHAs and dirty-state records; strict emulator/simulator evidence verification |

The host's `paths.data` supplies private storage. Caller-provided names remain
metadata; they never become filesystem paths. UUIDs are validated before deriving
paths, and linked document files are rejected. Saved bytes and the last source
snapshot stay separate from the draft record. New UUID files are reserved exclusively and flushed before their recovery record
is published, avoiding hard links rejected by Android app sandboxes. Incomplete
new data cannot enter the visible document list without that record.
The record contains the original
bytes and edited text so an externally changed or deleted private file cannot
silently overwrite recovered edits. A failed save preserves the draft; a failed
record publication preserves its previous record. Publication after an already
successful file save can leave a recoverable conflict on reopening, requiring a
copy rather than assuming both operations committed together.

Import creates a copy, preserving the selected external source. Android grants
and iOS scoped URLs need not survive app termination because later edits use the
private copy. Editing the original provider document would require a
separate permission, bookmark and provider-write contract; it is not implemented.
The iOS picker delegate is retained until selection/cancellation. Platform choice uses the shared classifier, including older Android Python
runtimes that report Linux with `getandroidapilevel`. Android activity
results use the pinned Toga backend's `start_activity` hook. These backend/native
interfaces must be rechecked before upgrading Toga.

Draft writes currently occur on each edit. This favors simple recovery in the
small prototype; larger documents need performance work before expanding the
1 MiB limit. Focus/exit hooks supplement these checkpoints. Physical-device tests
must still check forced termination, suspension, permission denial/revocation,
providers with slow I/O, keyboard resizing and accessible touch layouts.

## Selected features and dependencies

The native app includes text/Markdown and EPUB/comic readers and uses Toga 0.5.7 backends with Briefcase
0.4.5. It installs no desktop PySide, image or archive dependencies. Staging copies
only whitelisted Logistics Python modules plus tracked shared Python sources and
licenses. It never follows the local external feature link or copies private INIs,
Git metadata or untracked shared files. Local dirty payloads are labelled and
cannot produce accepted mobile runtime evidence.

Native payloads select the portable EPUB/comic modules too. The testbed additionally
selects generated fixtures, including EPUB metadata/resource reading and comic
page bytes/ComicInfo updates. Encrypted archives, other desktop tools, external
sharing and app-store distribution remain future work. No desktop capability is enabled by a prototype build.

## Validation gates

[Native builds](../../.github/workflows/mobile-build.yml) create an Android debug
APK and an unsigned iOS Simulator app archive, with bounded build jobs and retained
source manifests/logs. Build success proves packaging, not native UI interactions.

[Document runtime checks](../../.github/workflows/mobile-runtime.yml) use the
already established CPython 3.14.7 testbeds, pinned at
`823f0323ee6ec1402088b73bce1a38473cac36dc`. Android builds x86_64 on Ubuntu 24.04 and selects Android command-line tools
19.0, matching the native application gate. The runner-bundled SDK manager failed
to unpack the current emulator archive; the versioned installation is selected
through the `latest` path required by the pinned CPython driver.
iOS builds arm64 Simulator on macOS 15. The existing iOS resource-copy workaround
is retained. Twenty-five cases run inside each actual interpreter:

- Nine private document, recovery, encoding, conflict and scoped-import contracts.
- Three existing EPUB/comic/Markdown fixture scenarios.
- Three mobile preference and offline-preview contracts.
- Four mobile library, reading, sanitization, progress and image-bound contracts.
- Four mobile chat, cancellation, privacy and recovery scenarios using loopback fixtures.
- Runtime identity and a desktop-dependency import boundary.

The verifier requires one report, expected native `sys.platform`, actual emulator
or simulator classification, both clean source SHAs, the exact inventory/count,
zero failures/errors and zero skips. Host runs are explicitly `desktop-harness`
and cannot pass the mobile verifier. Scoped-import unit cases use provider objects
to check lifetime/error contracts; they do not prove actual picker permissions.
Reports explicitly record `native_picker_tested: false`.

Source paths on alpha trigger the corresponding mobile jobs; manual target
controls become available once the workflows are on the default branch. New
mobile push runs supersede older mobile push runs. Existing desktop release
validation remains independent. Native artifacts are development outputs, not
store uploads or physical-device signing.

## Evidence status

The shared foundation previously passed Android and iOS in
[run 38277821906](https://github.com/ispaure/commonUtils/actions/runs/38277821906),
with seven cases per runtime. Its
[mobile test guide](../../Python/commonUtils/docs/developer/mobile-testing.md)
records those source/runtime details; this is separate from Logistics validation.

The new Logistics 14-case host harness, packaging/verifier tests and Toga dummy
widget workflow pass locally. Native iOS project generation and dependency
installation succeeded, but the local Xcode storyboard build failed with
`iOS 26.5 Platform Not Installed`; no simulator devices were available. Both [hosted native builds](https://github.com/ispaure/logistics/actions/runs/38353619087)
passed at `a02a4ba`, producing an Android debug APK and iOS Simulator app; see
[build evidence](mobile-evidence/2026-10-13-native-initial.json). The
[first Logistics runtime run](https://github.com/ispaure/logistics/actions/runs/38353619071)
passed all 13 initial cases on iOS, recorded in
[iOS evidence](mobile-evidence/2026-10-13-ios-initial.json). Android ran all 13 but
reported seven errors because its sandbox rejected hard-link publication of new
files; [the failed record](mobile-evidence/2026-10-13-android-initial.json) is retained.
New private files now use exclusive creation followed by publication of a durable
recovery record, and the suite has a fourteenth case enforcing that contract.
The [corrected runtime run](https://github.com/ispaure/logistics/actions/runs/38354610543)
passed all 14 cases with zero failures, errors or skips on both Android and iOS at
`5c4a528`; retained reports are [Android](mobile-evidence/2026-10-13-android-corrected.json)
and [iOS](mobile-evidence/2026-10-13-ios-corrected.json). Both corrected native builds
also passed in [run 38354610510](https://github.com/ispaure/logistics/actions/runs/38354610510);
see [build evidence](mobile-evidence/2026-10-13-native-corrected.json).
No physical-device or actual native picker result is claimed here.

Source releases require both mobile native builds and document runtime checks
alongside the desktop platform checks before packaging and publication. The same
commit supplies every called workflow and source payload; standalone branch runs
do not substitute for this release gate.

## Next work

1. Validate the hosted native artifacts and document runtime results, then run the
   app on simulators/emulators and physical devices with real provider selections.
2. Exercise keyboard/touch/accessibility and suspend/termination recovery before
   adding reader or IDE features.
3. Add explicit export/share and provider writeback, with stale-source checks and
   permission/bookmark handling appropriate to each platform.
4. Select target-native image/archive dependencies before enabling those features;
   then introduce signing, distribution and store metadata.

The [mobile user guide](../../Python/logisticsmobile/user_docs/README.md) describes
the implemented document flow, and [build instructions](../../Mobile/README.md)
list the independent environment and host checks.

## Phase roadmap

The authorized implementation order is phase 1 (hub/preferences/text/Markdown),
phase 2 (EPUB and comic readers), phase 3 (LM chat), and phase 4 (rclone credential
packages and feasible remote access). Each phase is committed with its phase
prefix, pushed, released on alpha only after every platform gate passes, and the
successful release commit is promoted to main for a release request. Physical
device validation and signed distribution remain distinct from source releases.

Phase 1 adds Home/Documents/Settings navigation, private INI preferences,
platform export-copy pickers and an offline basic Markdown preview. Android's
pinned WebView needs the declared Chaquopy static proxy for navigation handlers.
HTML is capped below its 2 MiB default content limit. Active HTML is never passed
through; default-src none and navigation refusal prevent preview network access.
System provider export is explicit; neither original-source writeback nor external
sharing is implied. Picker cancellation and stream cleanup are tested contracts,
not actual native-provider evidence. Static CI runs the official Toga dummy widget
and picker contracts before release, while real mobile testbeds cover the added
portable preference and preview cases.

## Phase 2 reader contracts

`library.py` streams bounded imports into private storage, validates archive member
paths/counts/sizes and uses native access for protected archives before reusing portable EPUBBook and
ComicPages. UUID identities and checksums protect record/path associations.
`features.books.mobile.content` renders an allowlist of XHTML tags with source attributes/styles and
active content removed; small validated PNG/JPEG/WebP images use data URLs under an
offline CSP. Native comic inputs have byte/dimension/pixel limits before decoding.
`reader_ui.py` runs archive operations off the event-loop thread and exposes
reading-order chapter/page selection, bookmarks and optimistic progress updates.
Progress is chapter/page-granular; precise EPUB scroll restoration is future work.

Native build jobs now capture the normal app before a separate Briefcase
`--test` rebuild. Test mode runs seven actual native UI cases against generated
files and private cache data; its exit marker and JSON report must agree with the
expected backend, case inventory and exact root/shared commits. It exercises real
WebView DOM rendering and native image decoding, but supplies fixture providers
rather than opening OS pickers. The test entry point calls `_exit` only after
printing its result; it is excluded from normal app source paths. Retained native
artifacts are the pre-test normal APK/Simulator archive. Native UI evidence is a
required build-job result; packaging cannot bypass it. Physical-device pickers,
keyboard/touch/accessibility and suspension remain independent validation work.

### Phase 2 native UI evidence

At `428d1d7`, [native run 38365625757](https://github.com/ispaure/logistics/actions/runs/38365625757)
passed all seven actual app cases on Android and iOS, including DOM rendering and
native PNG decoding. Retained [Android](mobile-evidence/2026-10-13-android-native-ui-phase2.json)
and [iOS](mobile-evidence/2026-10-13-ios-native-ui-phase2.json) reports identify the
real backend and source commits. The initial failures exposed an Android AVD/tool
mismatch, the pinned backend's required AndroidX WebView asset loader, and an iOS
blank-document navigation race. Briefcase now creates the selected emulator with
its own tools; Android declares WebKit 1.15.0; HTML uses a distinct offline-document
origin while navigation handlers and CSP deny external content. These checks do
not establish physical-device interaction or provider permission behavior.

Phase 1 was published as [v0.1.1-alpha.11](https://github.com/ispaure/logistics/releases/tag/v0.1.1-alpha.11)
at `99f7653`, after the complete five-platform release gate passed. Its exact
commit was promoted to main and release `v0.1.1-main.03` was requested without
waiting for that separate pipeline.

## Phase 3 chat contracts

`chat.py` uses the existing `features.lm.domain` conversation schema, validation and
whole-turn request budgeting, with a mobile-owned bounded private store. Desktop
QLockFile/Qt storage and transport are not imported. Optimistic revision/snapshot
checks reject stale saves; valid recovered streaming messages become interrupted.
The profile schema deliberately excludes API keys. `chat_transport.py` uses
HTTPConnection/HTTPSConnection with default certificate verification, no redirects,
bounded JSON/SSE, explicit socket cancellation and no model tool execution.
An owned background reader isolates file-backed HTTP reads. Cancellation is
checked every 100 ms by the consumer even when Windows does not wake a blocked
read after socket shutdown. The reader closes its own response and retains the
15-second socket timeout; it cannot publish further fragments after cancellation.
`chat_ui.py` owns native controls, explicit connection/model actions, draft and
partial-response checkpoints, and retained failure/cancelled states. HTTP remains
available for existing LAN servers and is labelled as unencrypted in the guide.
No external server is contacted in tests: `chat_fixture.py` binds loopback only
with synthetic text/key values. Native UI test mode adds the same workflow to its
required cases. iOS declares NSLocalNetworkUsageDescription; physical-device
network consent/ATS/provider behavior remains a separate gate. Conversation export
uses the existing bounded system export-copy workflow.

Phase 2 was published as [v0.1.1-alpha.13](https://github.com/ispaure/logistics/releases/tag/v0.1.1-alpha.13)
at `428d1d7` after all desktop, native UI and 21-case mobile runtime gates passed.
Its exact commit was promoted to main and release `v0.1.1-main.04` was requested
without waiting for that separate pipeline.

## Phase 4 embedded rclone contract

The credential import UI exposes **Choose credential ZIP…**, the selected
filename, a password field and adjacent **Load remotes** button. Selection
immediately reads at most 1 MiB into memory while picker access is held, then
releases the provider handle. It does not load credentials or contact a remote.
Loading consumes that in-memory selection, clears the password and shows
**Browse folder** as the next action. A failed load keeps the selected ZIP ready
for another password attempt; a successful load or forgetting credentials
releases it. No additional ZIP or plaintext credential file is persisted.
Focused dummy-backend tests cover selection, cancellation, wrong-password retry,
oversized ZIP rejection and success; the native fixture exercises the new
choose/password/load sequence.
The remote picker retains actual backend remote names and includes an explicit
tap-to-choose label. Its hint lists available crypt remote names, identifies a
selected crypt, and explains when the ZIP has no crypt configuration. It does
not silently choose a backing remote or remap remote identifiers.

`Mobile/rclone_bridge` is a pinned Go module using rclone 1.74.1 and yeka/zip for
WinZip AES/ZipCrypto interoperability. `cloud_build.py` builds Android arm64/x86_64
C shared libraries with NDK 27.2.12479018 and explicit 16 KiB ELF page alignment, and iOS arm64 device plus host-architecture
Simulator C archives. Generated projects link only the narrow C bridge. Go 1.26.9
is pinned in the native workflow; checks run module tests before native builds.
Compiled-module license notices and the Go runtime license are included in the
native Python payload before Briefcase creates the app.

The bridge exposes import, list, bounded read, offline probe, cancel and clear;
it does not expose generic RC, commands or remote mutation. No RC listener starts.
Drive/dropbox/onedrive/s3/webdav/smb/memory backends are linked (plus crypt). Parsed credentials
are checked against explicit per-backend option allowlists before publication.
Config uses the synchronized Storage in `Mobile/rclone_bridge/vault.go`;
configfile.Install is never called. A nonempty logical config path allows rclone to
install that custom Storage without using a plaintext config loader. Session mode
uses only RAM. Saved mode writes AES-256-GCM snapshots with fresh random nonces,
a versioned vault-ID AAD, exclusive 0600 temporary files and atomic replacement.
Bounded no-follow reads reject links, and optimistic byte comparisons reject
concurrent edits. The same encrypted storage path persists rclone token-save callbacks;
failed saves remain visible to subsequent read/list operations. Native backend
config maps bind getters/setters to their storage generation; late callbacks from
retired connections cannot update a replacement package or recreate forgotten files. Plaintext serialization
is disabled. Import validates all members before publishing the replacement. A
session-only import detaches persistence and preserves the saved ciphertext.

The `add_smb` bridge action appends an explicitly named SMB server to the loaded
snapshot, rejects duplicates, and preserves existing connection settings and OAuth
identity pins. `smb.go` validates the host, explicit username and port, obscures the
form password for rclone, and publishes through the same encrypted vault. Session
mode copies the loaded snapshot into detached memory while leaving saved ciphertext
unchanged. Cached backend handles are shut down before storage generations change.
The SMB option allowlist excludes Kerberos config/cache filesystem access. Package
imports also accept this restricted SMB configuration, with an already obscured
password. The Files/Remote connections form accepts multiple servers, defaults to
saving credentials and immediately opens the share browser; existing folder Pull
and copy workflows own transfers. iOS declares SMB in its local-network permission
explanation. SMB share paths start with the share name. Local bridge/configuration
and dummy UI tests do not establish physical Android/iOS SMB server connectivity.

`features/rclone/mobile/credential_vault.py` owns a random 32-byte data key: AndroidKeyStore AES-GCM wraps
it into bounded metadata under noBackupFilesDir; iOS Security.framework uses a
non-synchronizing WhenUnlockedThisDeviceOnly generic-password item. The iOS vault
folder is excluded from backup, and the Keychain item is labeled Logistics plus
the imported ZIP filename. The data key crosses the internal C boundary only for
vault attachment. ZIP passwords never persist. Protected-key failures have no
plaintext fallback or automatic regeneration. Forget unloads native clients and
disables token writers before deleting the known OS key and private vault files.
Corrupt metadata can be forgotten without guessing/deleting unrelated key aliases.
Provider token refresh stays in RAM when session mode is selected, and supported backend Shutdown hooks run
when replacing/clearing cached clients. Normal rclone diagnostic logging is
suppressed; API failures use bounded generic messages without provider responses.

ZIP members are read into bounded buffers, authenticated and validated without
filesystem extraction. The fixture was generated independently with pyzipper
AES-256; tests cover wrong passwords, tampering, path traversal, oversized inputs,
unsupported filesystem/script settings and retention of the prior session on a
failed import. All tests use synthetic credentials and an in-memory remote.

`cloud.py` owns the ctypes C allocation/free boundary and app-private completed
copies. Downloads stream into a duplicated caller-owned private descriptor;
only metadata crosses the C/JSON bridge, avoiding base64 amplification for files.
`features/rclone/mobile/cloud_ui.py` owns explicit picker/import/connect/download controls. Private
copies use exclusive creation in UUID folders and a completion marker, so recovery
excludes incomplete, linked or invalid entries. Export extends the existing system
copy adapter to chunked binary output with an explicit 32 MiB maximum; existing
document/chat exports retain their 1 MiB default.

Crypt downloads have two explicit storage contracts. The ordinary `read` action
continues to reject crypt remotes. `crypt_fetch` saves original ciphertext into
LocalCrypt. The explicit `crypt_read` action resolves an admitted crypt/backing
pair, opens the encrypted object, authenticates/decrypts it as a stream and writes
to a new caller-owned private descriptor. It verifies the decrypted byte count,
completion, cancellation and flush; no whole-file buffer or fixed size cap is
introduced. Python `Downloads.fetch(..., decrypted=True)` publishes the readable
filename in Private downloads only after success, and removes partial plaintext
on failure. The UI labels this action **Download decrypted copy** and explains
that it stores unencrypted data, alongside **Download encrypted copy**. Ordinary
open/export and normal app-data backup behavior apply to the explicit plaintext
copy. Tests cover a transfer larger than the in-memory reader limit, remote
ciphertext preservation, corrupted input, cancellation, existing destinations,
unsafe paths and failed-copy cleanup.

The mobile core inventory now includes 30 cases, including protected-key lifecycle
and failure privacy. Native UI evidence includes ten cases. The ninth covers: real linked rclone, AES credential import,
folder browsing, downloading/opening a private copy and forgetting the session.
Native entry points retain the explicit `native_picker_tested=false` evidence flag.
The tenth exercises native protected-key creation/reload/forget, encrypted package
restoration, missing-key recovery without regeneration and a session-only import
preserving ciphertext. These new native tests
have not yet run on Android/iOS for the local uncommitted implementation.
Physical-provider interaction, real-account OAuth rotation,
background transfers and signed/distributed device builds remain unverified work.

Phase 3 was published as [v0.1.1-alpha.19](https://github.com/ispaure/logistics/releases/tag/v0.1.1-alpha.19)
at `e3f7194`, after all desktop checks, 25-case core checks and eight native UI
cases passed on both mobile runtimes in [run 38379277207](https://github.com/ispaure/logistics/actions/runs/38379277207).
Its exact commit was promoted to main and `v0.1.1-main.05` was requested without
waiting for that separate pipeline. Retained native reports:
[Android](mobile-evidence/2026-10-13-android-native-ui-phase3.json) and
[iOS](mobile-evidence/2026-10-13-ios-native-ui-phase3.json).

`native_loop.py` binds Toga 0.5.7 Android cooperative dispatch to the app's owned
asyncio loop. Java callbacks can enter Python with a different callback-local
running-loop context; the upstream dispatcher establishes it only at startup.
The app installs its wrapper before native wake-up registration, sets the loop
policy, and restores the previous running-loop context after each dispatch. A
host regression enters a callback with another loop and verifies owned futures,
current-task identity and caller-context restoration. Native app checks continue
to exercise actual Java/WebView callbacks; no failed case is retried into success.


## LocalCrypt extension

The bridge now validates a single crypt layer over supported package-local backing
remotes, downloads original ciphertext as a stream and reads offline copies via
authenticated ranges and lazy archive members. Local text/Markdown saves stage and verify ciphertext; inner password ZIPs
are opened lazily through the bundled ZIP library. Comic/EPUB metadata saves replace
only metadata and preserve inner passwords and untouched archive entries. The native private reader keeps text
and PNG/JPEG/WebP images out of persistent
document/library records. EPUB uses a generic archive source. See [LocalCrypt](localcrypt.md)
for API boundaries, limits and host regression coverage. Earlier phase-4 evidence
predates this extension and does not validate its Android/iOS UI or native binaries.

On 2026-10-13, the local uncommitted implementation passed all 14 native UI cases
on an iPhone 17 Pro simulator (iOS 26.5) and an ARM64 Android 35 emulator.
The LocalCrypt cases cover reading, text/Markdown editing, comic/EPUB metadata
editing with inner AES ZIP passwords, save-conflict preservation and locking.
Retained local reports: [iOS](mobile-evidence/2026-10-13-localcrypt-ios-native-ui-local.json)
and [Android](mobile-evidence/2026-10-13-localcrypt-android-native-ui-local.json).
Both bind the staged source fingerprint
`e002b8ca59668c23e7decd8255ea394639092484e20564e7afab73cb7664de36`.
They explicitly record dirty sources and are not release-gate evidence.
Physical devices, real system pickers and manual touch/keyboard interaction remain
unverified. Native testing fixed private-label wrapping on iOS and report log-line
truncation; the failed-save scenario uses an actual stale-file conflict after an
oversized single-line input stalled the Android native text widget.


The subsequent local file-management extension passed 15 native UI cases on both
runtimes, including mkdir, rename, moves within/into/out of crypt storage, editing
after a move, Save As to crypt/Local, continued saves, and collision rejection.
The shared deletion engine is exercised natively; the confirmation/cancel UI is
covered by the dummy-backend regression. Final source fingerprint:
`9b9bfd2610615c299fd2d4ca7c35cdfa7eedddbae040763db1205a8caa71922f`.
Reports: [iOS](mobile-evidence/2026-10-13-localcrypt-files-ios-native-ui-local.json)
and [Android](mobile-evidence/2026-10-13-localcrypt-files-android-native-ui-local.json).
These retain the dirty-source marker and do not replace release-gate evidence.

Two review passes covered mutation safety and UI/provider lifecycle. Fixes included
rejecting different representations of the same physical storage, refreshing iOS
picker row counts, preserving desktop shutdown wiring, and mapping managed staging
names through the crypt provider. Host regressions additionally inject a broken
writer which emits plaintext under an encrypted name, reject corrupted ciphertext,
preserve inner archives during transfers, verify managed metadata editing, and
check source retention on verification/cancellation/conflict failures. Go race
tests cover rewrapping with distinct keys and rejecting the wrong key.

### Shared resource refactor validation (2026-10-13)

The final local payload `154f87ea8cd9ae01c9cf7560aa075a983078059bf63a1aa2f98a31f52b54099b`
passed all 15 native UI cases on the iPhone 17 Pro / iOS 26.5 simulator and
LogisticsLocalCrypt / Android API 35 emulator. This rerun includes the shared save
transaction, explicit capabilities, text-state/editor integration, split provider
modules, partial-failure reporting, explicit encrypted transfer stream and exclusive
staging ownership. Cases cover reading, text/Markdown editing, inner-password comic
and EPUB metadata, file operations, Save As, stale saves and credential locking.

Reports: [iOS](mobile-evidence/2026-10-13-localcrypt-refactor-ios-native-ui-local.json)
and [Android](mobile-evidence/2026-10-13-localcrypt-refactor-android-native-ui-local.json).
Both are marked dirty local-development evidence, not release evidence. System file
picker interaction and physical devices were not tested by these runs.

Targeted shared tests additionally inject verification failures, stale revisions,
late cancellation, partial source deletion, post-save external writes and temporary
name collisions. All passed. Desktop Qt/real-rclone tests and host native-bridge
round trips passed, including inner-password preservation and plaintext-under-encoded-name
rejection. The mobile dummy-backend UI suite passed all 11 cases.

### Provider bypass audit validation (2026-10-13)

Payload `141c29aff3512f96383b018fe513bbf222e54de06a1aa5c0b5bc8c2b4562f646`
passed all 15 native cases on both the iOS simulator and Android API 35 emulator.
Reports: [iOS](mobile-evidence/2026-10-13-provider-audit-ios-native-ui-local.json),
[Android](mobile-evidence/2026-10-13-provider-audit-android-native-ui-local.json).
These are dirty local-development reports, not release or physical-device evidence;
system file pickers remain outside this suite.

Additional validation passed: 75 metadata/core cases, 37 desktop editor/crypt cases,
19 private-backend cases with registered boundaries, 27 shared persistence/provider
cases, and all 11 mobile dummy-backend UI cases. The broader browser, removal,
bulk rename and Markdown run passed 83 tests with one case-sensitive-filesystem
case skipped on this Mac. Targeted tests also verified ordinary Save As rejection
inside actual ciphertext storage and draft retention after a successful mobile
save whose new reader fails to open. Test groups overlap; counts are not additive.


## Shared mobile browser extension

The mobile file manager, remote listing and editor chooser use the commonUtils
portable BrowseTree and native Toga list/tile presentation. Storage/domain work
remains in Logistics adapters; Local/LocalCrypt selection is retained. Generic
file fields appear on selection, with worker-loaded comic/EPUB details and covers.
Only visible thumbnails are queued, at most two concurrently, and caches remain
bounded in RAM. Stale and credential-locked results cannot repopulate a stopped
view. Editor selection omits the info panel. Desktop retains its Qt views and
column mode over the same entry conversion/model contract.

The bridge no longer applies a 32 MiB cap to downloads, crypt transfers or archive
rewrites. Range reads and decoded members have separate buffer limits, while
resource verification hashes authenticated streams. A host native-bridge regression
exercises a 40 MiB archive containing a single 40 MiB unrelated member: Local to
LocalCrypt, cover/info, metadata save, offline-copy move and back to Local, with
contents preserved. Native UI checks include this large-file metadata path and
actual shared list/tile selection, cover decoding, file information and clearing
on lock. Earlier reports above do not validate these additional checks.


On 2026-10-13 the local snapshot
`036c19b5b81f7ccebb705cb7825ce6d21326988781d9f9ba9e4a9d3afadab547`
passed all 15 native UI groups on iPhone 17 Pro / iOS 26.5 Simulator and the Android
API 35 emulator, including the shared browser and 40 MiB archive checks above.
Reports: [iOS](mobile-evidence/2026-10-13-shared-browser-ios-native-ui-local.json),
[Android](mobile-evidence/2026-10-13-shared-browser-android-native-ui-local.json).
These are exact local development snapshots, not committed release evidence or
physical-device/system-picker validation. The desktop browser suites (19 host
window checks and 7 shared provider/view checks), 13 dummy mobile UI checks, and
3 host native-bridge interoperability/large-file/transfer checks also passed.


## Ordinary comic streaming and shared native navigation

LibraryStore imports ordinary comics with shared bounded stream iteration and no
256 MiB archive/expanded-total gate. A shared LocalArchiveSource seeks ZIP headers,
reads a single bounded page through ComicPages and checks file revisions. Unrelated
large resources are not loaded into RAM. Per-page 8 MiB/16-megapixel and 5,000-entry
limits remain; EPUB limits are unchanged. SHA-256 is collected during import,
verified on reopening after restart and cached against the full file revision and
record digest in a bounded 32-entry session cache. Changed files invalidate the
cache; publication and verification reject revision races.

commonUtils owns BrowseHistory, query/sort projection and bounded recursive
provider searches, with Toga
controls in NativeBrowser. Logistics supplies folder/open-location callbacks and
opaque `(storage, relative path)` locations for file manager, remote browser and
editor picker. Tap folders to load them and Back through successful visits.
Search toggles a full-width field matching desktop and scans folder names in
subfolders on a cancellable background worker, with a 10,000-entry bound and
explicit partial results. Closing search restores the original listing. Natural-name/size/modified sorting keeps folders first.
Filtered-out selections are cleared; failed navigation preserves the prior listing
and history. Closing/locking clears navigation and displayed private state.

Host tests cover a real 257 MiB stored archive, page reading, checksum reuse,
restart verification, member read bounds and changed-file rejection. Native UI
checks now include a 257 MiB ordinary comic and actual folder-tap/Back/search/sort
callbacks across Local/LocalCrypt plus the editor picker. Earlier native reports
do not establish coverage for this extension.


The local source snapshot
`c8c2b958584bebe1ed0b63850c980e40660bcbe3de3bd632a2b0c80452b479b3`
passed all 15 native UI groups on both iPhone 17 Pro / iOS 26.5 Simulator and
Android API 35 emulator, including the 257 MiB ordinary comic and shared navigation
checks. Reports: [iOS](mobile-evidence/2026-10-13-streaming-navigation-ios-native-ui-local.json),
[Android](mobile-evidence/2026-10-13-streaming-navigation-android-native-ui-local.json).
The 37 portable host core checks, 14 mobile widget checks, four portable browse
checks and seven desktop shared-view checks also passed. These reports identify a
local development snapshot, not a clean release build or physical-device testing.
Native source updates for hidden compatibility selectors reload their iOS picker
row counts before assigning a new selection; otherwise a successful folder listing
could fail while clearing selection after adding the no-selection placeholder.

The final recursive-search and search-layout snapshot
`494b23ea39d6a48b3adc5a2f1e1207d4358270741a9c7bd36cdd0425fe968aa9`
passed all 15 native UI groups on both simulators, including nested LocalCrypt
search results and restoring the folder listing on closing search. Reports:
[iOS](mobile-evidence/2026-10-13-search-final-ios-native-ui-local.json),
[Android](mobile-evidence/2026-10-13-search-final-android-native-ui-local.json).

## Standalone password-protected comics

Library imports preserve CBZ/ZIP bytes and validate headers, without decrypting
protected members. `LibraryStore.open(..., password=...)` uses a local archive
adapter over the native `file_archive` operation for AES and ZipCrypto. That
operation needs only a caller-owned independent regular-file descriptor, a
password and an optional member name; no remote credentials or network access
are involved. It shares header validation and bounded member decoding with
LocalCrypt. Both Python adapters share `NativeArchiveAccess` for authentication,
RAM caching and revision checks, then use the existing ComicDocument/ComicPages.

The native operation validates every header before reading a selected member,
allows 5,000 entries and bounds each decoded member to 8 MiB. It retains no
whole-file cap or plaintext-file cache. The library keeps password state with the
active source only, clears it on Lock, and writes only existing reading progress
and checksums to records. Missing/wrong passwords retain an inline retry prompt;
Cancel preserves the encrypted library import. Standalone encrypted EPUB import
remains unsupported. Native comic cases cover both desktop-made AES and Info-ZIP
legacy fixtures, retry, page navigation, bookmarks, lock and restart behavior.

Standalone comic validation passed all 15 native UI groups on both simulators for
source snapshot `af8377a815c46db9d48164519ea3c383316af904d20b66b633c164656a9935ac`.
Reports: [iOS](mobile-evidence/2026-10-13-standalone-comics-ios-native-ui-local.json),
[Android](mobile-evidence/2026-10-13-standalone-comics-android-native-ui-local.json).
These are local development snapshots; native file pickers and physical devices
were not exercised. The host native decoder, Go bridge suite and 15 mobile widget
checks also passed, including AES and legacy passwords, retry and locking.


### Remote action checkpoint

Credential controls live in a Settings route; the Files remote route keeps browse
status before the entries and download actions. Invalid selections report the
next action instead of silently returning. `folder_download.pull_folder` streams
ordinary or decrypted files into a private staging directory, validates direct
child paths and duplicate entries, checks cancellation and credential generation,
and publishes a new local folder only after all entries complete. Failures remove
staging; repeated pulls never overwrite local edits. This is a one-time pull, not
synchronization. The 10,000-entry bound matches the mobile traversal budget.

Library sessions use `reader_sessions.Readers` with per-session native views and
one shared LibraryStore adapter. Inactive decoders suspend; asynchronous page/open
results check reader generation and host lifetime. Protected comic sessions remain
transient. LocalCrypt still uses its existing guarded private reader; full private
session integration and independent windows remain later work.

Checkpoint validation: 42 mobile widget/workflow tests, six shared workspace/cloud
checks and the Go bridge suite passed. Both native suites passed all 18 cases,
including a real embedded-rclone folder pull, opening its local copy and checking
its bytes: [iPhone Duo](mobile-evidence/2026-10-14-mobile-checkpoint-ios-native-ui-local.json)
and [Android](mobile-evidence/2026-10-14-mobile-checkpoint-android-native-ui-local.json).
Both reports identify local snapshot
`3862ab9c3f839f7c79b3cb9c92a0dbeef62a9f31225941e9867721e6b005724e`.
These are local development checks, not a published release or physical-device
validation. Work pauses here at the user's request; unfinished milestones remain
listed in the mobile navigation plan.


### Explicit text-session close

User Close actions open a destination-local choice screen when text is dirty.
Cancellation and native Back have no close side effects. `close_session` targets
the captured session owner, with Save, Keep draft, Discard and Cancel choices.
Save conflicts and checkpoint failures retain that owner and report the failure.
`DocumentStore.discard` reads bounded current source bytes, checkpoints a new
baseline before changing the in-memory draft, and never writes or recreates the
source file. A deleted source remains unavailable/conflicted. Ordinary retained
drafts stay accessible through Stored documents; private drafts cannot use Keep.
The direct controller close API defaults to Keep for existing callers.


Markdown presentation mode belongs to each text session. Activating a session
first installs its own editor beneath the preview route, then renders that
session's text if Preview was selected. Returning through native Back records
Edit mode. Preview buttons capture an owner/generation so a closed owner's
callback cannot activate another document. The shared WebView is refreshed on
activation and navigation remains offline and restricted.


Restored ordinary resources whose records cannot be opened display an unavailable
route with Try again and Remove from open documents. Selecting one leaves the
previous editor owner untouched; removing the unavailable entry does not delete
source or recovery files. Library activation failures use the same route.


Android navigation uses a Material DayNight context for both bottom and rail
views. The pinned backend's AppCompat-created bottom view is detached while the
adapter is installed and restored on disposal, including its layout/selection
listeners and menu ownership. Native checks require visible inactive icon and
label contrast against each bar's surface. This prevents normal launch from
showing only the selected destination against an incompatible black background.


### Phase 1: memory-only provider session ownership

`private_sessions.PrivateSessions` owns up to four provider controllers alongside
the ordinary text/library registries. Resource identities hash the stable storage
root and provider key; all provider entries are transient and omit names, paths,
content and view state from ordinary workspace persistence. Each controller owns
its text widgets, metadata form, reader and save callbacks. Switching never
replaces another private draft. Failed Save As presentation rebinds the previous
owner. Credential reload/replace/forget checks every dirty owner before clearing
any owner. Dirty Close offers Save, Discard and Cancel without a durable Keep
choice. Lock/removal invalidates its workspace generation and clears its views.

The private registry admits at most 32 MiB of retained whole-file input across
four owners. Streaming archives retain bounded source caches; inactive owners
release decoded images and native member caches, recreating the selected page
on activation. No dirty text/form is evicted to meet a budget. Ordinary library
readers suspend when a provider owner binds. Existing private text remains
session-only, including provider-backed local text, until explicitly saved to
its verified provider destination. File mutation retains the conservative guard
that all private work must be saved/discarded; ordinary folder browsing does not
close sessions. Native resource and mixed-session checks remain required.


Phase 1 native mixed-session verification passes on both platforms (19 cases
including `native_private_workspace`). It edits two encrypted resources, browses
Files, switches through Settings, reopens the same owner, cancels Close, verifies
that forgetting credentials cannot discard either draft, checks manifest privacy,
and invalidates callbacks when both owners are explicitly discarded. Reports in
`mobile-evidence/2026-10-14-phase1-*-native-ui-local.json` retain the exact local
staged fingerprint. They remain development evidence, not clean release gates.


Phase 1 Part 3 adds scoped memory-pressure subscriptions: iOS memory-warning
notifications and Android application ComponentCallbacks2 trim/low-memory events
schedule cleanup on the owning UI loop. Disposal unregisters each subscription
when a host is replaced or exits. Cleanup releases decoder/image/thumbnail caches
while preserving private text and metadata widgets. Native mixed-session checks
also exercise the cleanup callback without losing either draft.


### Phase 2: repeatable one-way folder pulls

`pull_jobs.PullJobs` stores bounded ordinary job metadata, opaque connection
identities, and SHA-256 file/directory baselines. The native `connection_identity`
action hashes admitted configuration in memory without disclosing credentials or
performing network access. A changed/locked connection rejects a job instead of
retargeting it. Decrypted crypt jobs are transient: their remote names, folder
paths, baselines and journal are omitted from ordinary persistence and cleared
with credentials. Their explicitly downloaded local files remain plaintext.

Refresh downloads a complete separate snapshot before publication. If the local
folder differs from its recorded baseline (including added/deleted files), the
original folder stays untouched and the new remote snapshot remains beside it.
For an unchanged target, a durable intent record precedes renaming the old folder
to a unique previous-version folder and publishing the incoming folder at the
original location. Rename failure rolls back when possible; every surviving
version is retained. Retry reconciles the journal against bounded hashes before
starting another transfer. Metadata-write failure cannot erase either version.
Previous versions are not automatically deleted. Remove job removes metadata,
not files. The model admits at most 16 jobs/10,000 entries per tree and a 4 MiB
manifest; malformed records are preserved and cannot be overwritten.

`resource_imports.ResourceImports` also maps a hashed app-private source identity
to its imported text/library UUID. Reopening a downloaded/local archive copy
activates that imported resource instead of duplicating it. The index stores
no source path, title, draft, password or permission handle; encrypted provider
readers remain outside this index and the ordinary recovery store.

## Unified Files milestone

Toga remains the selected mobile runtime; the Qt experiment is retained separately.
Files caches its native browser route, so destination switching does not rebuild
its history, selected item, search/sort or presentation. Secondary local/remote
commands use the isolated native FeatureCommands menu and separate routes.
Widget ownership remains exclusive when controls move between routes.

`locations.py` persists at most 32 ordinary folder pins in a 16 KiB record, using
private-relative local paths or opaque native connection identities. No encrypted
folder paths or credentials enter that record. Publication checks the previous
bytes, rejects linked files and preserves malformed input. Remote opening resolves
exactly one current ordinary connection; changed/missing identities fail closed.

Both native suites pass 20 cases, including real bridge folder pulls, preserved
local edits and separate conflict snapshots, local/remote pins, persistence and
retained browser state. Reports: [iOS](mobile-evidence/2026-10-14-phase2-ios-native-ui-local.json)
and [Android](mobile-evidence/2026-10-14-phase2-android-native-ui-local.json). These
are labeled local source snapshots; physical provider/device checks remain limits.
The 57 host widget/workflow tests and native Go bridge suite also pass.

## Phase 3 Part 1: native reader presentation

`ComicCanvas` extends the pinned Toga ImageView backend through its widget factory.
iOS owns a UIScrollView/UIImageView zoom container; Android owns a tracked Java
AppCompatImageView with scale and gesture detectors. Neither edits generated
backend packages. Zoom is limited to 1–6, page gestures are gated at fit size, and
edge touches are reserved for platform navigation. ReaderChrome publishes session
commands, compact controls, appearance and a recoverable immersive view. Private
controllers own their separate tools views and decoded images.

Wide Markdown preview is per TextEditorView. Delayed rendering captures a workspace
generation token, checks host lifetime, and is cancelled on close. The optional
flag is whitelisted in the bounded ordinary manifest. Native UI coverage adds
`native_reader_presentation`; WebView ownership assertions wait for a single
rendered text snapshot instead of reading a transient empty document during reload.
Android evidence runs cold-start the emulator rather than restoring renderer state.

## Phase 4 Part 1: independent UIKit scenes

`window_scenes.py` installs a tracked UIApplicationDelegate/UISceneDelegate
extension around the pinned Toga backend. A separate Window frontend uses the
native MainWindow container without the pinned secondary-window rejection. Each
scene owns a Logistics workflow controller, native navigation, adaptive container,
editor/reader callbacks, preferences and a bounded workspace under `Windows/<id>`.
Only app infrastructure and ordinary document storage are shared. Scene IDs are
validated UUIDs or hashes of system session identifiers; restoration activities
contain only that opaque ID. The scene's destination record is bounded and
malformed records are preserved.

WindowOwners grants exclusive process-local resource writers. The original
window retains connection/transfer/chat ownership; protected sessions cannot
coexist with multiple windows. Picker futures/delegates belong to the presenting
window, and disconnect cancels its picker. Secondary disconnect checkpoints,
invalidates callbacks, releases writer leases, native subscriptions and readers,
then activates the original scene. A forced original-scene disconnect retains
its checkpointed owner until process restoration; it does not grant a competing
writer. No independent Android activity capability is enabled.

`Mobile/scene_build.py` applies scene support reproducibly to the generated plist
because the pinned template otherwise forces it off. It does not modify Toga
packages. The iOS release job runs both iPhone and iPad tests, requiring explicit
`independent_windows_tested` evidence on iPad rather than accepting resize as a
substitute. The native case creates actual scenes, rejects duplicate writers,
closes and restores a distinct draft and selected destination. Device-specific
picker and OS eviction checks remain unverified.

## Phase 5 Part 1: managed mobile transfers

MirrorJobs adds bounded, versioned managed-copy mappings and interrupted-publication
recovery. Ordinary copies live beneath LocalFiles; ciphertext copies use the
existing CryptFiles namespace beneath LocalCryptFolders. Pull stages a complete
snapshot, checks the local baseline again at publication, preserves previous
copies and leaves edited destinations intact. Crypto metadata records raw stored
paths and opaque configuration identities, never decrypted document content.
Snapshots are retained outside the live ciphertext tree so temporary names cannot
break crypt browsing. Removing a mapping is metadata-only.

The native bridge exposes scoped mirror info/list/read/stat/write requests for
admitted remote names. Ciphertext pulls authenticate while streaming raw bytes
into the private descriptor. Push stages a stable source copy, checks remote
hashes, retains and verifies a remote backup before replacing a file, and verifies
uploaded bytes. Per-file completed baselines support reviewing a partially
completed push. No remote-delete, shell, arbitrary filesystem or generic RC API
is added. These checks are not a provider-independent atomic compare-and-swap;
external concurrent writers can still race a backend Put, and the review/user guide
must explain folder-level partial completion and avoiding concurrent writers.

Transfer callbacks carry host/generation and operation-epoch guards. Native local
archive/image operations use independent contexts outside the credential-engine
lock so ordinary comics remain usable during remote I/O. This does not make
protected provider operations concurrent: transfer setup preserves dirty work and
releases clean provider views. Active-app background work is distinct from an
OS background-transfer entitlement. The guided CopyUI workflow is integrated and
now uses atomic no-replace rename rather than hard-link publication, which Android
sandboxes reject. Native cases exercise guided copy, ordinary background pull/push,
and ciphertext folder pull/edit/push; all 25 cases pass on Android and iPad/iOS.

## Phase 5 Part 2: scoped ciphertext and complete preflight

Schema 2 keys live ciphertext trees by full connection identity, while the cipher
identity continues to validate encryption settings. CryptFiles accepts a separate
physical namespace for linked copies. Existing cipher-only trees are preserved;
old journals resolve against their original tree, and subsequent pulls populate
the connection scope. Snapshot lookup retains old physical namespaces. Files and
editor selectors expose linked providers without changing legacy destinations.

OAuth connection pins are established before backend connection/token refresh and
stored only inside the authenticated credential vault. They retain the original
full configuration hash while non-token scope settings remain unchanged. Importing
another package replaces pins, and older vaults migrate at first use. Tests cover
refresh, vault restoration, account replacement and separate trees using one cipher.

The mobile Books & Comics catalog discovers configured folders at local copy
roots and immediate collection folders, including mapped subfolder copies. It
shares `features.comics.library_config.library_names` with desktop and reads
LocalCrypt INIs through `CryptFiles`, in a worker, without persisting decoded
names or scanning book archives. Only existing configured library directories
become rows; imports keep their reader/session workflow. Refresh rejects stale
credential generations, and credential clearing removes private catalog rows.

Push preflight authenticates all local ciphertext, verifies source hashes, checks
remote revisions, and handles directories before writeback. Stable source staging
is cancellable. A bounded native progress channel, independent of the credential
engine lock, reports authentication, backup, sending and verification without names
or credentials. Repeated unchanged progress samples do not update native text,
progress widgets or transfer banners, avoiding redundant layout work during local
document use. Transfer metadata uses optimistic byte checks before atomic writes;
external record edits stop writes and are preserved. Stale review callbacks cannot
confirm after credential reload/forget. Every mobile Push entry point confirms
before preparing a review through `start_mirror_review`; the review's write action
requires a separate confirmation. Both prompts validate the connection generation
and mapping again after acceptance. Native selector assignment guards prevent
re-entrant iOS browse requests from racing explicit linked-location routing.

The UIKit delegate is registered before UIApplicationMain through scene_build.py,
not replaced after launch. Closed secondary hosts detach widget registries and leave
the process host map. The original warm owner can move its window to a replacement
scene using UIKit's supported windowScene setter, with open-session reconciliation
and idempotent discard/disconnect handling. Original launch-scene destruction was
vetoed or ended the process on the beta simulator; evidence records that path as unverified rather
than treating a request as successful. See [Apple's windowScene contract](https://developer.apple.com/documentation/uikit/uiwindow/windowscene).

Cold library workspaces retain the selected reader and resume it lazily when the
Documents destination is selected. Explicit text activation clears that pending
reader selection. The iOS CI gate shuts down its completed iPhone simulator before
launching iPad; both inventories still require all native cases, and iPad requires
actual independent-window evidence.

## Phase 5 Part 3: final alpha submission

The final local validation passes all 25 native cases on iPhone iOS 27.1, iPad
simulator iOS 27.0 and Android 15, including actual secondary iPad scenes and managed
Local/LocalCrypt folder transfers. The tracked mobile host suite passes 67 tests;
Go bridge race tests and Python lint pass. The source alpha gates independently
validate the clean tagged source before publication. Local snapshot evidence is
retained under `mobile-evidence/2026-10-14-phase5-part2-*-native-ui-local.json` and
correctly records its pre-commit dirty source identity.

The original submission was `v0.1.1-alpha.33`. Its Windows comic-library fixture
cleanup race blocked publication. Phase 5 Part 4 uses the existing Qt-aware
temporary-directory scope and passes all 31 comic-library tests locally without
suppressing errors. The corrected submission is `v0.1.1-alpha.34`, with title
**Phase 5 Part 5: Toga workspaces and validated mobile transfers**. Consult its GitHub release and CI results
for actual publication status. Physical original-window destruction remains
unverified, as do the manual device checks listed above; no simulator request is
reported as a successful OS closure. This release packages source and does not
imply device signing or App Store/TestFlight publication.

## Phase 5 Part 6: published alpha and clean CI evidence

[v0.1.1-alpha.34](https://github.com/ispaure/logistics/releases/tag/v0.1.1-alpha.34)
is published with its source ZIP. The [release workflow](https://github.com/ispaure/logistics/actions/runs/38542171235)
passed every platform gate (Windows, macOS, Ubuntu, Fedora and static validation),
both embedded mobile runtimes, both native builds, packaging and publication.
Clean tagged native reports verify all 25 cases on Android, iPhone and iPad; iPad
reports actual independent scenes. Both embedded runtime inventories contain all
39 expected tests. The published ZIP's version identifies commit
`8416b248f33b87837783edefde3d2658b4e2b0f2`; its recorded file hashes and tagged
transfer/runtime sources were verified after download.

Clean native reports are retained under
`mobile-evidence/2026-10-14-alpha34-*-native-ui-ci.json`. Physical original-window
closure remains explicitly unverified, and the device limits above still apply.
This final documentation checkpoint changes no released runtime behavior.

## Phase 6 Part 1: brief verification and restoration preference

The user requested three verification passes against the navigation brief and
current alpha. Pass 1 traces navigation, resource identities, recovery/privacy,
adaptive presentation, readers, Files/connection ownership and independent scenes
against their implementation and existing fixtures. The current baseline passes
all 67 tracked host tests. A new cold-reader regression then demonstrates that
startup restored a selected library session despite `restore_last_document=false`.
The fix retains the open reader and saved chapter/page while respecting the
preference; explicit reopening still works. All 68 tracked host tests and all 39
portable core tests pass after the fix.

The feature matrix's physical permissions, cancelled system gestures, physical
fold poses, original iPad window closure, large-text/screen-reader combinations and
minimum-iOS coverage remain unverified. Existing simulator resize and programmatic
checks are not substitutes for those device-specific claims. The Home-first order
in the brief's updated decisions overrides its older three-destination milestone
text; the separately authorized managed Push also supersedes its original remote
read-only boundary. No desktop emulator documentation boundary changed.

The exact prior alpha.34 commit was separately promoted to main and published as
[v0.1.1-main.07](https://github.com/ispaure/logistics/releases/tag/v0.1.1-main.07)
after every [release gate](https://github.com/ispaure/logistics/actions/runs/38570954429)
passed. Its signed normal-launcher build matches the validated source fingerprint
and installed over Wi-Fi without uninstalling or changing identity. All 16 existing
document files remained listed with matching sizes; file contents were not copied
or byte-compared. Physical launch was initially blocked by the locked phone. After the user unlocked
it, launch succeeded and the installed executable was confirmed running.
The alpha verification fixes do not alter that exact-commit main release.

## Phase 6 Parts 2–3: local alpha verification

The [three-pass alpha audit](mobile-alpha-verification.md) records the delayed-open,
superseded-host and hidden password-focus fixes, plus native navigation-intent
tracking that tolerates UIKit container refreshes. All 72 frozen host tests,
39 core tests and 25 native cases on each of Android, iPad and iPhone pass.
Concurrent folder improvements are excluded from this frozen audit. These fixes
and evidence remain local under the user's commit hold; main.07 stays unchanged.

Native comic geometry checks wait for three consecutive centered samples after
chrome transitions, with a 15-second deadline. This replaces a fixed 300 ms delay
that could sample the previous viewport during slow hosted Android layout. The
same two-pixel centering and fullscreen-height assertions still apply.

## Android collection drive selection

`features/rclone/mobile/storage_location.py` owns the shared Local/LocalCrypt
location. Private `collection-storage.json` records the selected volume and a
random identity matching `<volume>/Logistics/.logistics-storage`. Unconfigured
installs retain the existing private `LocalFiles`/`LocalCryptFolders` layout.
Configured drives use `Logistics/Local` and `Logistics/LocalCrypt`; neither
credentials nor `mirror-jobs.json` move. All provider, Folder Hub, library and
transfer destination resolution uses this boundary. Retained collection providers
revalidate the selected marker before filesystem operations. No missing-card
fallback or replacement directory is created.

`logisticsmobile/storage_ui.py` enumerates mounted Android storage volumes and
opens the app-specific All files access Settings screen. The manifest helper
declares `MANAGE_EXTERNAL_STORAGE` idempotently. The user grants special access;
no ADB permission override is part of the workflow. This direct-path file-manager
access supports the existing native rclone bridge and ordinary SD-card folders.
It is distinct from document import/export URI grants.

Switching is blocked during active cloud/transfers and while provider readers are
open. It checkpoints managed text, prevents new cloud mutations, inventories both
trees, checks free space, copies into unique staging directories, flushes copied
file bytes and compares SHA-256 inventories. Symlinks, hardlinks and special files
are refused during migration. Different nonempty destination collections are
never merged or overwritten. An empty source permits adoption of an existing
collection. The private pointer changes last. Original trees remain for recovery;
failed switches can retain already verified destination trees for retry. The app
exits after success so retained providers cannot continue using an old location.
Root-level marker and private state must be preserved when manually moving cards.

Android and iOS now share the Show Legacy preference and filtering; dummy/desktop
hosts preserve their existing unfiltered behavior. Tests in `test_storage_location`,
`test_storage_ui`, `test_reader_build` and `test_workspace_navigation` cover
migration, missing media, conflicts, private metadata, permission gating, restart
and cross-platform visibility. Physical SD-card performance and removal during
native rclone I/O need device verification; availability is checked before each
host operation, not by a native mid-transfer media monitor.

Android comic immersive mode now asks the shared navigation chrome adapter to
hide Android system status/navigation bars as well as app bars. The shared
component owns visibility/behavior restoration and inset reapplication; Logistics
continues to own which visible reader route requests fullscreen. See commonUtils'
native component guide for its contract. Android Settings also exposes a direct
`APPLICATION_DEVELOPMENT_SETTINGS` intent, and the deployment helper caches local
SDK paths in ignored `Mobile/.tools/android-sdk.json` and reconnects advertised
`_adb-tls-connect._tcp` endpoints. It never pairs silently or enables debugging.
