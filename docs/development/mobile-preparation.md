# Mobile document host and validation

Logistics Mobile is the native Toga application for iOS and Android. The host
composes Workspaces browsing and transfers, document editing and reading,
feature-gated Chat, and Settings. The desktop Qt launcher and its dependency
pins are separate. Mobile code uses portable commonUtils APIs and native
adapters without loading desktop initialization.

| Responsibility | Source owner |
| --- | --- |
| Application entry and startup | `Python/mobile/__main__.py` calls `main().main_loop()`; `Python/mobile/app.py` constructs the application and composes its workflows. |
| Installed entry and dependencies | `mobile_build/pyproject.toml` declares the Briefcase app key, source roots, test sources and platform requirements. `mobile_build/tools.py` generates the staged `logisticsmobile/__main__.py` entry, which calls the same `mobile.app.main`. |
| Payload selection | [Owner-declared source selection](#owner-declared-source-selection) defines what enters the mobile source payload. |
| Destinations and window lifetime | `Python/mobile/navigation.py` defines destination metadata. `window_scenes.py` binds UIKit scenes to hosts, and `window_owners.py` arbitrates process-local writer ownership. |
| Build and deployment | Follow the [mobile handbook](mobile-handbook.md) and [build tooling map](build-tooling.md) for generated projects, native bridges and deployment ownership. |

Use the [mobile host code guide](mobile-runtime.md) for current implementation
owners and the [mobile user guide](../user_mobile/user_mobile.md) for supported
workflows.

## Owner-declared source selection

The mobile host, services and selected features each declare a
`mobile_sources.json` file with schema 1 and explicit paths relative to their
owner. Update the owning manifest when adding a source dependency. The
`SOURCE_OWNERS` list in `mobile_build/tools.py` selects the manifests without
importing feature registration. The staging tool validates the selected imports
and packages the manifests with the payload. Type-checking-only imports and
uncalled registration factories do not pull additional modules into the payload.

Before creating the staging destination, preflight also requires the generated
launcher's `mobile.app` target and checks existing child packages referenced by
`from` imports. Imported attributes are not treated as missing modules. The
`source_sha256` digest includes selected HTML, JavaScript and CSS paths and bytes
alongside Python sources, so changing staged web content changes the fingerprint.
`Python/tests/test_mobile_packaging.py` covers these omissions and digest changes.

Staging combines the selected Logistics files with portable commonUtils sources
and declared package data. It rejects linked source paths and excludes the local
external feature checkout. Clean staging requires tracked shared sources.
Local dirty staging is identified in the source manifest and is ineligible as
clean runtime evidence. Generated Briefcase projects and
`mobile_build/payload/` are build outputs.

## Validation gates

Use the [host validation commands](mobile-launchers.md#host-validation) for
focused checks and [platform checks](platform-checks.md) for release gates.
The [native build workflow](../../.github/workflows/mobile-build.yml) produces
Android and iOS development artifacts and runs native UI validation.
The [document runtime workflow](../../.github/workflows/mobile-runtime.yml)
checks the embedded Python runtimes with a separate case inventory. The runtime
verifier checks the platform and runtime identity, source identity, exact case
inventory and passing results. Desktop harness runs cannot supply mobile runtime
evidence.

Keep packaging, native interaction and device acceptance distinct. Picker
fixtures exercise import lifetimes without proving OS permission behavior.
iPad scene evidence requires actual scenes and separate workspace and writer
checks. Android resize and Activity recreation exercise one host. Physical
pickers, keyboard/touch and accessibility, device eviction, minimum-iOS
interaction and physical fold gestures require platform-specific evidence.
Use the [Duo rotation and fold checks](mobile-handbook.md#duo-rotation-and-fold-verification)
when changing foldable layouts.

## Offline component notices

Settings → About → Open-source licenses uses `services/open_source.py` for installed
Python dependency notices, the vendored rmscene notice and the Go build's
`mobile/native-licenses/manifest.json`. The Python inventory follows the platform's
declared requirements and their installed dependencies, excluding unrequested extras
and unrelated host tools. Package metadata and license files must remain in the
final app; missing texts are displayed explicitly.

Staging copies `Python/services/licenses/` as package data and writes the Android
and iOS Python requirements to `mobile/open-source-dependencies.json`, so the
viewer needs neither the source checkout nor network access. Native catalog
versions and source addresses in `services/licenses/native.json` must be updated
with their pinned dependencies. The bundled LGPL, GPL, Apache and Python texts
are upstream license resources, not application guides.

The Android Gradle hook collects the resolved runtime and Chaquopy support
artifacts, including transitive dependencies, selected versions and Maven parent
license declarations. The resulting `logistics-open-source.json` asset is read
offline through the native asset manager. Go collection includes package-local
notices for both supported architectures under the target OS. Desktop-only source
notice catalogs are excluded from the mobile payload.

See [open-source notices](open-source-notices.md) for collector ownership, refresh
commands, exact validation scope and unresolved publisher/provenance items.
This viewer does not establish redistribution permission or complete source and
relinking obligations; verify the final artifact before store publication.

Host coverage: `test_open_source.py`, `test_settings_page.py`,
`test_settings_ui.py`, `test_license_inventory.py`, `test_license_build.py` and
`test_mobile_packaging.py`. Native device layout and
final APK/IPA contents require separate release validation.

## Launcher artwork

`mobile_build/resources/icons` contains pre-sized PNGs derived from the supplied light,
dark and monochrome artwork. iOS uses 20–180 pixel legacy slots and 1024 pixel
light/dark/tinted slots. Android uses 48–192 pixel legacy icons and 108–432 pixel
adaptive layers, with night-qualified artwork and API 33 monochrome resources.
Adaptive foregrounds include padding to retain the complete supplied tile within
the launcher mask. Android launchers control whether night/themed icons refresh.

`mobile_build/build_support/icon_build.py` installs these resources from `cloud_build.py` after
Briefcase create/update, including device deployments and isolated TestFlight
archives. It also replaces the template launch artwork. Build-time installation
uses only the standard library; Pillow is needed only for asset regeneration:

```sh
mobile_build/.venv/bin/python mobile_build/build_support/icon_build.py /path/to/light.png /path/to/dark.png /path/to/monochrome.png
```

Regeneration downsamples the complete square images with Lanczos filtering,
without cropping or retouching. iOS copies flatten transparency over matching
white/navy backing because app icons must be opaque. Android's separate themed
mask converts inverse grayscale luminance, multiplied by source alpha, to opacity;
this retains the original shading when the launcher supplies its tint. Original
downloads are not changed. Native launchers apply their own final icon masks.

Verify catalog and resource installation with `mobile_build/tests/tooling/test_icon_build.py`.
Compile the generated iOS catalog with Xcode's asset compiler when changing its
appearance slots. Home-screen appearance and launcher cache refresh still need
device validation; host tests do not establish those behaviors.

## Native destination routes

The destination metadata lists Home, Workspaces, Documents, Chat and Settings.
Workspaces retains the internal `files` route key. Chat is available when the LM
feature is enabled. Destinations have independent screen
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

`features/text_editor/mobile/ui.py` owns a native editor per text session. Change callbacks capture that
owner rather than the app's current selection. The app retains compatibility
aliases for existing feature controllers. Asynchronous import/export captures its
origin and rejects UI completion after that session closes; a background import
does not switch a different active document. Closed ordinary drafts remain stored.
Session generations prevent late results from reviving closed or invalidated
resources. `workspace_navigation.py` supplies the active adaptive presentation
inside the native destination and Back stacks on Apple and Android. It can
place a browser or retained editor beside the current document when the pane
allocation permits it. Compact layouts use a drawer or the current document.
Resizing preserves open sessions. The [workspace navigation guide](mobile-workspace-navigation.md)
covers platform thresholds, Android fold geometry and rail behavior. `action_menu.py` isolates native editor
command presentation and rebinds commands to their editor owner.

A replacement host with the same private root and window identity retires its
predecessor, invalidates old session generations and cancels pending private file
work. Android uses this replacement path for Activity recreation and uses the
adaptive workspace for side-by-side panes. iPad supports independent UIKit
scenes. Each scene owns its host, navigation and workspace state. The scene
manager shares ordinary document storage and uses `WindowOwners` to prevent
competing writers. Protected sessions are restricted to a single window.
See the [independent scene lifecycle](#independent-uikit-scenes)
and [workspace navigation guide](mobile-workspace-navigation.md).

## Ownership and contracts

| Module | Contract |
| --- | --- |
| `documents.py` | Explicit absolute app-private root; UUID file identities; 1 MiB bounded Unicode text; original encoding/endings; exclusive creation, atomic saves and recovery JSON; stale/deleted-file rejection and safe copies |
| `access.py` | Scoped binary imports; Android content URIs are handled by ContentResolver streams; iOS URLs retain security-scoped access until reading finishes; every handle/scope is closed on failure |
| `pickers.py` | Android ACTION_OPEN_DOCUMENT and iOS UIDocumentPicker open mode; native grants are consumed immediately to import a private copy; no broad storage permission or persisted external write access |
| `app.py` | Application composition, startup, document workflows and window attachment |
| `preference_schema.py` | Serialized defaults and value validation, independent of INI I/O |
| `preferences.py` | Bounded private INI, migrations, atomic replace, malformed-file preservation and concurrent-edit rejection |
| `preview.py` | Bounded basic Markdown HTML; escaped raw input, inert links and offline CSP |
| `smoke.py` | Fresh-interpreter desktop-dependency rejection, real runtime identity, exact test inventory and structured evidence |
| `mobile_build/tools.py` | Whitelisted Logistics sources, tracked/clean shared Python sources, licenses, source SHAs and dirty-state records; strict emulator/simulator evidence verification |

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

The editor queues ordinary draft checkpoints through `DocumentStore`, batching
edits before background publication. Focus loss and exit provide additional
checkpoint opportunities. See [document responsiveness](mobile-runtime.md#startup-and-document-responsiveness)
for the persistence and validation scope.

## Selected features and dependencies

The app uses the platform Toga backends declared by Briefcase. For current
feature selection and import boundaries, follow the
[mobile feature selection guide](mobile-runtime.md#mobile-feature-selection)
and the [payload manifests](#owner-declared-source-selection). The portable
testbed adds test modules and fixtures for runtime contracts. Briefcase's native
UI test entry is separate from the normal application entry.

## Reader contracts

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

## Chat contracts

`features/lm/mobile/storage.py` uses the existing `features.lm.domain` conversation schema, validation and
whole-turn request budgeting, with a mobile-owned bounded private store. Desktop
QLockFile/Qt storage and transport are not imported. Optimistic revision/snapshot
checks reject stale saves; valid recovered streaming messages become interrupted.
The profile schema deliberately excludes API keys. `features/lm/mobile/transport.py` uses
HTTPConnection/HTTPSConnection with default certificate verification, no redirects,
bounded JSON/SSE, explicit socket cancellation and no model tool execution.
An owned background reader isolates file-backed HTTP reads. Cancellation is
checked every 100 ms by the consumer even when Windows does not wake a blocked
read after socket shutdown. The reader closes its own response and retains the
15-second socket timeout; it cannot publish further fragments after cancellation.
`features/lm/mobile/ui.py` owns native controls, explicit connection/model actions, draft and
partial-response checkpoints, and retained failure/cancelled states. HTTP remains
available for existing LAN servers and is labelled as unencrypted in the guide.
No external server is contacted in tests: `chat_fixture.py` binds loopback only
with synthetic text/key values. Native UI test mode adds the same workflow to its
required cases. iOS declares NSLocalNetworkUsageDescription; physical-device
network consent/ATS/provider behavior remains a separate gate. Conversation export
uses the existing bounded system export-copy workflow.

## Embedded rclone contract

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

`mobile_build/rclone_bridge` is a pinned Go module using rclone 1.74.1 and yeka/zip for
WinZip AES/ZipCrypto interoperability. `cloud_build.py` builds Android arm64/x86_64
C shared libraries with NDK 27.2.12479018 and explicit 16 KiB ELF page alignment, and iOS arm64 device plus host-architecture
Simulator C archives. Generated projects link only the narrow C bridge. Go 1.26.9
is pinned in the native workflow; checks run module tests before native builds.
Compiled-module license notices and the Go runtime license are included in the
native Python payload before Briefcase creates the app.

The bridge exposes scoped credential, browse and transfer operations.
Drive/dropbox/onedrive/s3/webdav/smb/memory backends are linked (plus crypt). Parsed credentials
are checked against explicit per-backend option allowlists before publication.
Config uses the synchronized Storage in `mobile_build/rclone_bridge/vault.go`;
configfile.Install is never called. A nonempty logical config path allows rclone to
install that custom Storage without using a plaintext config loader. Session mode
uses only RAM. Saved mode writes AES-256-GCM snapshots with fresh random nonces,
a versioned vault-ID AAD, exclusive 0600 temporary files and atomic replacement.
Bounded no-follow reads reject links, and optimistic byte comparisons reject
concurrent edits. The same encrypted storage path persists rclone token-save callbacks;
failed saves remain visible to subsequent read/list operations. Native backend
config maps bind getters/setters to their storage generation; late callbacks from
retired connections cannot update a replacement package or recreate forgotten files. Plaintext serialization
is disabled. Import validates all members before publishing its package context. A
session-only context has no persistence parent and preserves the saved ciphertext.

The `add_smb` bridge action appends an explicitly named SMB server to its saved or
session-only network-shares context, rejects duplicates, and preserves existing connection settings and OAuth
identity pins. `smb.go` validates the host, explicit username and port, obscures the
form password for rclone, and publishes through the same encrypted vault. Session
mode keeps its context in detached memory while leaving saved ciphertext
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

For reader and transfer behavior, see the [rclone developer guide](../features/rclone/development/development.md).
It separates [remote browsing](../features/rclone/development/remote-browsing.md)
from [reviewed transfers](../features/rclone/development/transfers.md).

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
document/library records. EPUB uses a generic archive source. See [LocalCrypt](../features/rclone/development/localcrypt.md)
for API boundaries, limits and validation.

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
Reports: iOS (local artifact `test-results/mobile-evidence/2026-10-13-shared-browser-ios-native-ui-local.json`),
Android (local artifact `test-results/mobile-evidence/2026-10-13-shared-browser-android-native-ui-local.json`).
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
checks. Reports: iOS (local artifact `test-results/mobile-evidence/2026-10-13-streaming-navigation-ios-native-ui-local.json`),
Android (local artifact `test-results/mobile-evidence/2026-10-13-streaming-navigation-android-native-ui-local.json`).
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
iOS (local artifact `test-results/mobile-evidence/2026-10-13-search-final-ios-native-ui-local.json`),
Android (local artifact `test-results/mobile-evidence/2026-10-13-search-final-android-native-ui-local.json`).

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
Reports: iOS (local artifact `test-results/mobile-evidence/2026-10-13-standalone-comics-ios-native-ui-local.json`),
Android (local artifact `test-results/mobile-evidence/2026-10-13-standalone-comics-android-native-ui-local.json`).
These are local development snapshots; native file pickers and physical devices
were not exercised. The host native decoder, Go bridge suite and 15 mobile widget
checks also passed, including AES and legacy passwords, retry and locking.


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


### Memory-only provider sessions

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
`test-results/mobile-evidence/2026-10-14-phase1-*-native-ui-local.json` retain the exact local
staged fingerprint. They remain development evidence, not clean release gates.


Phase 1 Part 3 adds scoped memory-pressure subscriptions: iOS memory-warning
notifications and Android application ComponentCallbacks2 trim/low-memory events
schedule cleanup on the owning UI loop. Disposal unregisters each subscription
when a host is replaced or exits. Cleanup releases decoder/image/thumbnail caches
while preserving private text and metadata widgets. Native mixed-session checks
also exercise the cleanup callback without losing either draft.


### Repeatable one-way folder pulls

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

## Unified Files

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
retained browser state. Reports: iOS (local artifact `test-results/mobile-evidence/2026-10-14-phase2-ios-native-ui-local.json`)
and Android (local artifact `test-results/mobile-evidence/2026-10-14-phase2-android-native-ui-local.json`). These
are labeled local source snapshots; physical provider/device checks remain limits.
The 57 host widget/workflow tests and native Go bridge suite also pass.

## Native reader presentation

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

## Independent UIKit scenes

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

`mobile_build/build_support/scene_build.py` applies scene support reproducibly to the generated plist
because the pinned template otherwise forces it off. It does not modify Toga
packages. The iOS release job runs both iPhone and iPad tests, requiring explicit
`independent_windows_tested` evidence on iPad rather than accepting resize as a
substitute. The native case creates actual scenes, rejects duplicate writers,
closes and restores a distinct draft and selected destination. Device-specific
picker and OS eviction checks remain unverified.

## Managed mobile transfers

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
sandboxes reject. Native cases exercise guided copy, ordinary background pull/push
and ciphertext folder pull/edit/push.

## Scoped ciphertext and transfer preflight

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

## Android collection drive selection

`features/rclone/mobile/storage_location.py` owns the Local/LocalCrypt/Received Files
location. Private `collection-storage.json` records the selected volume and a
random identity matching `<volume>/Logistics/.logistics-storage`. Unconfigured
Android installs retain the existing private `LocalFiles`/`LocalCryptFolders` layout.
Configured drives use `Logistics/Local`, `Logistics/LocalCrypt` and
`Logistics/Received Files`; neither
credentials nor `mirror-jobs.json` move. All provider, Workspaces, library and
transfer destination resolution uses this boundary. Retained collection providers
revalidate the selected marker before filesystem operations. No missing-card
fallback or replacement directory is created.

`mobile/storage_ui.py` enumerates mounted Android storage volumes and
opens the app-specific All files access Settings screen. The manifest helper
declares `MANAGE_EXTERNAL_STORAGE` idempotently. The user grants special access;
no ADB permission override is part of the workflow. This direct-path file-manager
access supports the existing native rclone bridge and ordinary SD-card folders.
It is distinct from document import/export URI grants.

Switching is blocked during active cloud/transfers and while provider readers are
open. It checkpoints managed text, prevents new cloud mutations, inventories all three
trees, checks free space, copies into unique staging directories, flushes copied
file bytes and compares SHA-256 inventories. Symlinks, hardlinks and special files
are refused during migration. Different nonempty destination collections are
never merged or overwritten. An empty source permits adoption of an existing
collection. The private pointer changes last. Original trees remain for recovery;
failed switches can retain already verified destination trees for retry. The app
exits after success so retained providers cannot continue using an old location.
Root-level marker and private state must be preserved when manually moving cards.

On Android, `CollectionFiles` first attempts exclusive rename for new-file
publication. SD-card/FUSE filesystems can reject that operation with `EINVAL` or
an unsupported-operation error. For regular files only, the provider then uses
the rooted provider's exclusive-create operation, verifies SHA-256 bytes and removes the
source after verification. Existing destinations are never overwritten. The copy
fallback exposes the new file while writing and is not atomic; directory renames
still require native exclusive-rename support. `test_storage_location.py` covers
successful publication, a racing destination and partial-copy cleanup.

October 25 physical Boox Note Air5 C validation used the main app's normal New
document and New folder controls on its selected SD card. Build 202610302 created
a valid one-page `.rmdoc` and opened its notebook editor. The in-place update
retained existing document, preference and credential bytes; existing library
metadata records also remained present. This verifies the creation path, not
stylus latency or every file-management operation.

A follow-up on the same build created plain-text and Markdown documents in two
additional new SD-card folders and opened their respective editors. Direct file
readback confirmed both destinations. A plain-text edit/save wrote the exact
37-byte test line but reported a reopen-verification failure and retained its
draft; that creation check did not certify edit/save round trips.
Existing files and library records remained present, and the earlier notebook's
archive members were unchanged. Only the main Logistics package remained installed.

Build 202610303 resolves this SD-card reopen failure by retrying a changed-revision
verification read once, requiring a stable revision and exact saved bytes. On the
same Boox, the main app edited, saved, closed and reopened both test documents;
Markdown also rendered the saved heading correctly. Direct readback matched both
documents exactly. The isolated native SD-card probe additionally passed two
consecutive saves and reopenings for each format and removed its test directory.
Regression tests retain rejection of real external changes and strict ordinary
reads. The update used the existing app identity and preserved its data.

### Incoming files and Inbox

`mobile/incoming_files.py` consumes complete native handoffs into ordinary
**Received Files** storage. iOS uses `Documents/Received Files`, beside the
file-sharing `Local` directory; Android uses `<collection-base>/Received Files`
(`Logistics/Received Files` on a selected drive). App internal storage keeps the
folder private. Workspaces, Browse All Files and the browser location picker use
the same name and destination. Android's `DeviceFiles` provider admits only Local
and Received Files; private state and raw LocalCrypt paths are rejected, including
direct requests. It is excluded from physical filesystem search indexing.

Legacy private and system `Inbox` trees are copied with SHA-256 inventory
verification and durable private `inbox-upgrade-*.json` receipts. Sources remain
as backups. An occupied destination gets a uniquely named `Previous Inbox`
subfolder; retries reuse the journaled destination instead of duplicating files.
Changed destinations stop migration and preserve both copies. iOS receipts avoid
absolute container paths so restores can resume. Startup creates Received Files
even before the first share. It never creates or writes Apple's system
`Documents/Inbox`; UIKit URLs in that directory now enter the normal native queue.

Android collection copying, recovery, empty-location checks and explicit inactive
location erasure include Received Files. The storage UI serializes these actions
with intake and migrates legacy Inbox before copying. Intake pauses during a
storage change. If a selected drive is unavailable, ready handoffs stay queued;
there is no silent internal fallback. Received documents reuse normal resource
opening and private-copy identity tracking.

Android's tracked `ReceiveActivity.java` accepts `ACTION_SEND` and
`ACTION_SEND_MULTIPLE` content-URI streams, including ClipData fallback. It owns
the temporary grants until copying finishes. iOS's native `IncomingFiles.m`
handles file URLs from cold/warm UIKit scene activation; `ShareViewController.m`
receives file representations inside their item-provider callbacks. Extension
intake uses an App Group; the main app consumes it when opened. Extensions do
not force-launch the app. Some document interaction menus present the extension
through the same share sheet.

`mobile_build/build_support/incoming_build.py` configures both generated native
projects. iOS adds and embeds the `io.github.ispaure.logisticsmobile.inbox`
extension and gives both targets the App Group
`group.io.github.ispaure.logisticsmobile`. Enable that capability for both Apple
app identifiers and refresh their provisioning profiles under the existing
team. The main bundle identity remains unchanged. Automatic signing configures
both targets; manual TestFlight archives require `--profile` and
`--inbox-profile`, each authorizing the same App Group. Extension build numbers
follow the containing archive. No provisioning material belongs in Git.

Native receivers stream at bounded memory into private `.partial` directories,
then atomically publish `.ready` directories with a filename record and payload.
Intake is excluded from backup (Android no-backup storage; iOS resource values)
and iOS applies file protection. Limit: 100 attachments, 1 GiB per file and a
4 GiB queued-data ceiling; Android additionally caps each batch at 2 GiB.
Interrupted partial handoffs expire after 24 hours when the consumer runs.
Ready handoffs remain available for retry after publication failures. The Python
consumer validates names, records and regular files, stages on the destination
volume, verifies SHA-256, publishes with exclusive rename, flushes the directory,
and only then removes the handoff. A private receipt makes interrupted cleanup
retryable without a duplicate copy. Reset also erases the shared iOS intake.

`start_receiving()` checks host liveness and storage-change state under the
publication mutation lock before admitting a batch. Cancellation while waiting
for that lock leaves the handoff queued. Cancellation lets an admitted batch's
publication and receipt cleanup settle under the lock; the receiver drains the worker,
including repeated cancellation, before propagating. A retired host receives no
late status or browser refresh. `test_incoming_files.py` covers both admission
boundaries, successor consumption without duplication and a late storage error.
These host regressions do not exercise native share-extension delivery.

Focused tests (`test_received_files.py`, `test_incoming_files.py` and
`test_ios_storage.py`) cover visible roots, legacy-copy conflicts and retries,
collection-drive copying, publication conflicts, interruption, linked/traversal input,
size limits, resource identities and repeated native project configuration.
The reusable `received_files_probe.py` QA entry point checks the real iOS
Documents root, legacy-byte preservation, Browse All Files navigation and native
URL intake. These checks passed on an iOS 27 simulator on October 24, 2026;
physical-device share-extension and Android native acceptance remain separate.
Reusable native sender fixtures live in `mobile_build/native_tests/android/incoming/`
and `mobile_build/native_tests/ios/IncomingSender.m`; iOS menu tests use
`IncomingFilesUITests.swift`. Keep generated projects, screenshots and test
reports outside the wiki. Physical iPhone/iPad acceptance still requires properly
provisioned App Group handoff; simulator results do not satisfy that gate.

### iOS shared Local storage

`mobile/ios_storage.py` prepares production iOS storage before any
preferences, workspace, providers or transfer services are created. Toga iOS
0.5.7's `paths.data` is the system `Documents` directory, so enabling file sharing
requires relocating the old private root to `Library/Application Support/Logistics`.
Fixture `storage_root` overrides are unchanged; secondary scenes reuse the prepared
private root. `UIFileSharingEnabled` and `LSSupportsOpeningDocumentsInPlace` expose
Documents through computer file sharing and the Files app. The iOS plist sets
`CFBundleDisplayName` and `CFBundleName` to `Logisticks`, so the intended Files
path is `On My iPhone/iPad → Logisticks → Local`. `Local` is created directly
under Documents; no additional app-name directory is created.

A durable private `ios-file-sharing-migration.json` journals the original root
entry names, moves them into Application Support (except the system import Inbox),
then publishes legacy `LocalFiles` children into `Documents/Local`. Old-layout names
identify an existing install; a fresh install without these names keeps any
already-added files in the shared root. `NSFileManager.moveItemAtPath:toPath:error:`
performs exclusive same-container moves without a second full copy or decryption.
Conflicts never merge/overwrite existing directories. Interrupted phases resume
from entries present at source or destination; missing entries stop migration.
Errors stop startup before services can use a partial layout. Completion is
journaled so later shared-root files, even with formerly private names, are left in place.

On every production launch, Documents receives `NSURLIsExcludedFromBackupKey`
before migration or provider registration; failure stops startup. This excludes
the shared Local root from both iCloud and computer device backups. It does not
enable iCloud Drive synchronization. The feature's process-local shared-root
registration is rebuilt each launch, avoiding persisted absolute iOS container
paths. `collection_path(private_root)` resolves to `Documents/Local`, while crypt
paths remain in their existing private location. Startup creates `Local` and `Received Files` on every
launch, including fresh installs, completed journals and after deletion in Files,
so both ordinary folders are visible before any remote is pulled or file is shared.
No migration is added for files previously pulled directly into Documents; files
beside `Local` remain untouched and outside Workspaces's Local collection. Mapping records retain their relative targets and stay private;
arbitrary computer imports do not create mapping records. Android's drive switch
is refused for a registered iOS root.

Installation enables the static plist capability before first launch. Old root
contents can therefore be visible to a trusted computer between installation and
the first successful migration; users must open the update before file sharing.
There is no runtime plist switch that can defer this capability until migration.
`mobile_build/tests/storage/test_ios_storage.py` covers data/mapping preservation, fresh installs,
relaunch, interruption in both phases, conflicts, links, and backup failure.

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
SDK paths in ignored `mobile_build/.tools/android-sdk.json` and reconnects advertised
`_adb-tls-connect._tcp` endpoints. It never pairs silently or enables debugging.

Native validation for these changes passed on the Android emulator using the
disposable `storage_chrome_probe.py` harness. The actual comic canvas measured
1079×1919 inside a 1080×1920 window with status/navigation bars hidden; both
controls and route exit restored them. The probe also exercised Android volume
enumeration, external app-specific file copying, the Legacy switch and dispatch
of developer settings. This does not establish physical removable-card behavior.
See retained proof (local artifact `test-results/mobile-evidence/2026-10-15-storage-android-fullscreen.json`).

The portable document runtime harness declares 45 tests, including credential
replacement, session privacy and retired mirror-operation checks. Its declared
method list must match the cases loaded by `mobile.smoke` exactly.

The Android privacy lifecycle proxy explicitly handles the activity configuration
callback during uiMode changes. Native reader checks wait for layout-triggered
reloads before toggling controls; compact iOS Home checks scroll the selected
action into view before testing native hit dispatch.

## Side-by-side credential contexts

`mobile_build/rclone_bridge/credential_sets.go` owns up to 32 package contexts. The
process-wide rclone config is a nonpersistent aggregate view whose remote aliases
delegate to their original package stores. Names remain unchanged unless they
collide; collision aliases incorporate the ZIP filename and package digest.
Account and crypt identities hash original package configurations, so adding a
context cannot retarget existing downloaded copies. Crypt backing lookup stays
within the source package; the aggregate translates only the resulting backing
remote name. Connection refresh callbacks capture their owning store and its
generation. Reloaded or retired contexts reject late callbacks.

A saved package store delegates encrypted publication to the private vault root.
The root contains only saved package snapshots; session stores have no persistence
parent or path. Saved-package reload preserves session contexts. Existing LGCV1
snapshots remain readable and migrate through normal saved publication/alias
normalization; multi-package envelopes use LGCV2 so older builds fail closed
rather than rewriting only one package. Device key aliases and vault paths are
unchanged. Package limits and aliases are validated before admitting a vault.

Credential mutations retain the native credential write scope; offline local
reads keep their independent read scope during transfers. The C response carries
nonsecret package modes, aliases and identity hashes with a monotonically
increasing state epoch. `CloudClient` serializes mutation/publication across
scenes and publishes shared package records and separate session privacy gates.
ScreenPrivacy shields all loaded session contexts and requires their outstanding
password gates after backgrounding. Explicit Lock clears all contexts. Retained
ZIP metadata keeps only its own remotes plus optional alias hints; it never
includes decoded credentials or other loaded packages.

Workspaces, encrypted library discovery and transfers resolve existing job
identities against the loaded package metadata without native I/O while rendering.
The actual native operation still validates its account/cipher identity.

### Android tablet comic viewport sizing

WorkspaceNavigation reserves Android rail width only while the native rail is
visible. The fullscreen route retains its existing reader and uses the reclaimed
allocation after chrome changes. Native reader checks measure both canvas axes
against the window, as well as the rendered image center, to catch blank space
outside an otherwise centered canvas. `comic_viewport_probe.py` exercises a
synthetic cache-only comic through repeated control/fullscreen transitions at
phone and BOOX-sized tablet dimensions. Shared native container behavior is
documented in commonUtils rather than duplicated here.

Mobile ComicNavigation maps Auto to a two-page spread only when the measured
reading pane is wider than tall; portrait, square and not-yet-measured panes use
one page. This mobile policy does not change desktop fit-based decisions.
Preferences default to Auto while retaining explicit Single/Double overrides.
ComicInfo Manga direction flows from the imported/provider reader into the spread
compositor and swipe direction; logical indices stay in archive reading order.
Landscape images and DoublePage metadata remain standalone. Native
`comic_spread_probe.py` checks native composition at injected pane sizes, while
host pixel tests verify metadata-driven visual order and page turns.

### Fullscreen comic hold magnifier

`ReadingFrame.set_immersive` enables the native canvas magnifier only for
fullscreen comics. Imported and provider reader page replacements apply the
current mode to each new canvas; spreads forward the property to their shared
canvas. The shared native image component owns gesture arbitration, lens drawing
and cleanup. EPUBs, ordinary image previews and comics with controls visible
leave it disabled. The lens uses the current in-memory page/spread without
creating files. Native touch/render validation remains a separate device check.
