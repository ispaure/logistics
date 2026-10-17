# rclone desktop/mobile consolidation

[Developer index](../../../../../docs/development/development.md)

This records the agreed scope, implementation history and current source audit.
Keep implementation and validation changes local; do not commit or push without
further user instruction. Preserve existing staged and unstaged work.

## Current audit — 2026-10-15

The managed Push/Pull consolidation and feature ownership move are implemented,
including the four items found in the preceding source audit:

| Completed item | Current behavior |
| --- | --- |
| Desktop directory review | Adds directory additions/deletions/matches from the same filtered inventories used for review revisions. Labels end in `/`; crypt labels decode according to directory rules. Directory revisions track membership/type rather than volatile timestamps, sizes or backend IDs. |
| Hashed-layout retirement | Removed `Connection.legacy`, `_component` and schema-1 lookup/publication. Fixtures now verify preservation and refusal of unsupported mappings rather than exercising the old layout. Same-account unsupported records block new publication; old records and ciphertext are not deleted or guessed into a new location. |
| Engine alignment | Desktop INI, fallback manifest, Go module and native build flags pin rclone 1.74.1. All six official desktop ZIP hashes match the published SHA256SUMS; extracted executable hashes are pinned too. The local macOS arm64 executable was installed and used in regressions. Other platform binaries were hashed, not executed on macOS. |
| Preview ownership | `mobile/previews.py` constructs native crypt sources and sends encrypted thumbnail requests. The generic app preview host delegates this I/O and retains presentation/format metadata. Mobile packaging includes the new adapter. |

Crypt directory decoding appends a synthetically encoded final file component and
then strips its decoded label. This lets the CLI file-name decoder apply the
right directory-name rules for standard, obfuscated, filename-encryption-off and
directory-name-encryption-off configurations. It creates no probe file and writes
no decoded report to disk. Existing crypt authentication and descriptor/path,
connection and destination safeguards remain mandatory.

The removed mirror list/read/stat/mkdir/write endpoints have no production callers
or implementations; their names remain only in rejection tests. `PullJobs`, its
UI, old Push plans and snapshot recovery are no longer runnable. The schema-3
mobile binding loader only drops unused baseline metadata; it does not revive the
old workflow. `crypt_raw_read` retains a bounded fallback for clients without
streaming.
`crypt_decode` is also used to verify staged text saves in production, in addition
to non-streaming opens and fixtures. The real `CloudClient` advertises streaming,
but its text readers are memory-backed, so the staged-save decoder is not dead
code. Consolidating fallback readers is optional later cleanup; deleting these
APIs wholesale would remove current validation. Crypt encode, metadata,
range/archive and validation APIs still serve active editing/reading/security paths.

Most Python rclone/crypt behavior is under `Python/features/rclone`: portable
policy/review at its root, desktop adapters/UI beside it, native-host adapters in
`mobile/`. Generic provider documents, navigation, privacy, local file pickers and
format-specific readers remain with their owners. `Mobile/rclone_bridge` remains
the native build/C-ABI boundary and also provides ordinary archive/image I/O;
moving the whole bridge for folder symmetry would mix feature and generic code.
Host controller callbacks still couple the feature UI to the app; this is an
ownership consolidation, not a complete interface redesign. No further Python
ownership move specific to this feature is identified by this audit.

Agreed platform differences remain: mobile has one transfer with no queue,
app-private credential ZIP storage and mobile screen hiding; desktop retains
multiple transfers and external ZIP paths. Existing platform limits also remain:
mobile has a restricted backend/configuration allowlist, container-bound storage,
no mounts and at most 16 managed mappings. Transfer preflight has no fixed entry
cap: Python inventories and the embedded bridge validate the entire local tree
with cancellation checks. Comparison rows and generated-file cleanup plans also
have no fixed entry cap in either host. CLI comparison inventories have no byte
cap, and bridge review requests admit cleanup plans without a request-size cap.
Desktop has the full CLI backend scope and supports relocated LocalCrypt roots. These limits
are existing capability boundaries, not new user-approved parity decisions.
Direct encrypted folder copies also differ: desktop preserves a
ciphertext folder hierarchy; mobile creates per-file offline records, so empty
folders have no representation in that copy workflow. Managed Sync preserves
empty folders on directory-capable backends on both platforms. These copy/storage
and capability boundaries are documented; they are not interchangeable Sync APIs.

Final-four validation: all 251 mobile host tests, 48 desktop rclone tests and
52 desktop LocalCrypt/remote/provisioning tests passed. Seven real native
ciphertext/archive/file-operation tests passed against the host bridge with the
new desktop executable; this includes encrypted preview generation through the
moved adapter. All 44 Go tests passed uncached and under the race detector.
Focused lint and whitespace checks passed. The full mobile host run is clean for
this snapshot; the older reader/privacy failures below are historical evidence.

The rebuilt iPhone simulator passed all 30 cases plus final UI/navigation review.
[Exact local evidence](../../../../../docs/development/mobile-evidence/2026-10-15-rclone-completion-ios-native-ui-local.json)
records source snapshot `7d9b6cffc747f94f55f8356b6197e001dddc4146b6e434e8cdcad0c67309440a`.
The moved preview adapter and generic host match the tested payload. Native tests
covered encrypted previews/readers and edits, crypt failure/lock behavior,
reviewed folder Pull/Push, early review retirement, and LocalCrypt reads through
Documents and library shortcuts during downloads. Android and physical devices
were not rerun; non-macOS desktop binaries were verified by hash, not executed.
No staging, commits, uploads or publication were performed.

The remainder of this page is chronological implementation history. Statements
about pending work or original blockers describe that increment, not current state.

## Agreed behavior

| Area | Decision |
| --- | --- |
| Review | Detailed review before both Push and Pull, showing additions, replacements and deletions. |
| Slow review | While scanning, offer an explicit action to proceed without the full review, after destination/direction confirmation. Mark partial results incomplete. This bypasses the comparison scan, not required credential, destination or LocalCrypt integrity checks. |
| Destination inference | Preserve desktop conventions: whole-folder Push uses the local folder name as the remote name in the selected account; specific-folder Push targets that folder name beneath the selected remote; Pull uses the remote name for its managed local folder. Do not introduce user-managed arbitrary persistent source/destination pairs as the primary workflow. |
| Account ownership | Preserve credential associations and LocalCrypt backing-target routing; name inference must not discard account context. |
| Ordinary file links | Follow file links for ordinary Local transfers on both platforms, using desktop behavior as the model. |
| LocalCrypt links | Reject links inside LocalCrypt on both platforms. Root relocation/link behavior needs separate assessment. |
| Credential ZIP location | Keep current behavior: mobile retains its protected package inside the app; desktop uses the externally accessible ZIP location. |
| Transfer options | Bring mobile to desktop parity for rename tracking, bandwidth limits and Push exclusions, including their defaults and scope. |
| LocalCrypt Push cleanup | Use desktop behavior on both platforms: remove narrowly allowlisted generated junk before actual Push, then validate ciphertext. Review is read-only. |
| Transfer concurrency | Desktop retains multiple transfers. Mobile permits one active transfer, with no queue. |
| Browsing during transfer | Mobile LocalCrypt browsing and reading must remain available during a download. The one-transfer restriction must not block local crypt reads. |
| Screen privacy | Preserve existing mobile hiding/capture protection. Do not add desktop capture blocking or a new desktop hiding action. |

Both current transfer engines use rclone Sync. Cancellation can leave completed
destination changes. No new backup/rollback policy has been requested.

## Incremental delivery

1. Complete the behavior matrix against current source and tests. Ask about
   consequential differences with concrete examples. Correct stale guidance as
   each behavior is implemented; do not describe planned behavior as available.
2. Introduce portable transfer requests, options, scope resolution and result
   contracts under `Python/features/rclone`, then migrate Pull and Push in
   separate runnable increments. Keep CLI and embedded execution as adapters.
   Share the review lifecycle, including partial results, scan cancellation,
   explicit early execution and stale-review handling.
3. Consolidate credential/copy ownership and LocalCrypt policy. Preserve
   platform-specific storage, native crypt I/O and credential protection.
   Reuse existing resource-provider and publication contracts.
4. Adapt desktop and mobile presentations to the shared operations. Keep
   toolkit rendering separate while aligning actions, defaults, errors and
   final results. Update user guides alongside changes.
5. Move remaining feature-specific mobile Python controllers/providers under
   the feature once dependencies are explicit. Keep app navigation, scenes,
   generic document hosting and device-wide privacy integration host-owned.
   Assess the Go source/build boundary separately rather than move it only for
   directory symmetry. Update explicit mobile source packaging at each move.
6. Verify shared behavior against both execution adapters, then exercise affected
   desktop and native mobile workflows. Record accepted platform exceptions and
   distinguish host tests, simulator/emulator evidence and physical-device checks.

Each increment must leave the app runnable. Remove replaced implementations only
after callers migrate. Shared portable imports must not load Qt, Toga or native
platform bindings. Use local test fixtures rather than live account transfers.

## Initial assessment topics (historical)

- Supported mobile backend/configuration scope versus the full desktop CLI.
- Credential-store scope and retry behavior: desktop has separate child
  processes; mobile currently has a process-global embedded session.
- Existing subfolder copy compatibility while adopting desktop inference.
- LocalCrypt root relocation versus the ban on links inside encrypted copies.
- Detailed comparison accuracy with exclusions, rename tracking and crypt
  routing, including what is known when a user proceeds before review completes.

## Original mobile LocalCrypt browsing blocker (resolved)

The initial source inspection confirmed two separate blockers, not just disabled buttons:

- `logisticsmobile/folder_hub_ui.py` disables non-Local browse actions while
  `cloud_busy` is set and rejects entry into those folders. Its current status
  explicitly says encrypted operations must wait.
- `Mobile/rclone_bridge/main.go` takes the same `serial` mutex for transfers and
  local crypt requests. A long `mirror_sync` therefore blocks local path decoding,
  stat/range reads and archive operations. Only ordinary local image/archive work
  and transfer-progress queries currently bypass that lock. The bridge also uses
  one active cancellation handle, which concurrent reads must not replace.

Fix both layers together. Keep credential replacement/revocation synchronized,
scope read cancellation independently from transfer cancellation, and preserve
revision checks when the download changes a file being read. Browsing a download
destination must tolerate files arriving or changing; incomplete content must not
be presented as a completed readable file. Do not enable UI actions over a bridge
that still blocks until the transfer finishes. Validation needs a deliberately
held transfer with completed ciphertext available, local listing/range/archive
reads finishing before transfer completion, and independent cancellation checks.

## Local implementation progress

First increment:

- Extracted immutable transfer options, exclusion validation and generated-junk
  constants to `features/rclone/transfers/transfer_options.py`. Desktop consumes them;
  mobile packages the portable module. Mobile option controls and execution
  wiring are still pending, alongside shared review semantics.
- Made the rclone package initializer defer desktop API imports so portable
  modules can load in the mobile payload without configuration/UI dependencies.
- Separated native local crypt read scopes from the serial transfer lock and
  its cancellation handle. A shared credential read/write lock keeps replacement
  and revocation synchronized; the cipher cache now has its own mutex.
- Enabled mobile LocalCrypt folder entry, navigation and private document opens
  during managed folder transfers. Mutation actions remain blocked. Listings
  omit rclone's hashed `.partial` download objects and tolerate removed entries.

At the end of that first increment, detailed Push/Pull reviews with early
execution were pending. The second increment below implements those reviews.
Mobile option controls, ordinary file-link parity, mobile crypt cleanup,
remaining scope/naming migration and final feature ownership moves remain pending.

Validation for this increment: 227 mobile host tests, 24 desktop rclone tests and
18 core/native-bridge tests passed. The rebuilt host bridge was loaded for native
ciphertext/text/archive round trips. The Go suite passes with the race detector;
its throttled crypt pulls exercise both readable Local and ciphertext LocalCrypt
downloads, reading existing local ciphertext before the transfer finishes. UI host
tests cover opening a LocalCrypt document while transfer busy state/cancellation
remain intact and keeping mutations blocked. Packaged startup imports the portable
options module without desktop dependencies. No new iOS/Android native UI or
physical-device evidence has been collected for this increment.

Second increment:

- First validated the concurrent browsing fix in a native iPhone simulator build:
  all 29 case groups passed. The new case reads an existing encrypted note while
  an actual bandwidth-limited embedded download is still running, refuses a
  second transfer and cancels the first without cancelling the reader. The
  protected contents and native I/O are real; all data is synthetic. [Evidence](../../../../../docs/development/mobile-evidence/2026-10-15-rclone-concurrent-read-ios-native-ui-local.json).
- Shared `ReviewRequest`, `ReviewSnapshot` and `ReviewScan` now live under the
  feature and are used by both desktop and mobile presentations. Desktop uses
  rclone's JSON sync-comparison logger and metadata inventories; mobile uses
  the embedded Sync comparison logger with a read-only context and metadata
  revisions. Both use their execution engine's comparison, rather than a second
  hash-based definition of which files Sync will change.
- User-facing Push and Pull, including creation of a mobile copy, scan before
  confirmation. Completed reviews are checked again; changed comparisons require
  another confirmation. Early proceed explicitly confirms incomplete comparison,
  retires its worker and then invokes existing execution preflight. Cancel and
  failure never imply approval. New-copy review does not create the destination
  or publish a mapping. Crypt Push execution still authenticates local ciphertext.
- Reports and decoded names stay in RAM. Credential changes invalidate the
  binding, clear displayed paths and revoke cached native comparisons. Desktop
  private resource leases close after review. No desktop screen-capture behavior
  was added.
- The native iPhone suite then passed all 30 case groups, adding cancelled Pull,
  confirmed Pull/Push, and early proceed into a new Local copy. [Evidence](../../../../../docs/development/mobile-evidence/2026-10-15-rclone-shared-review-ios-native-ui-local.json).

Regression validation: 229 mobile host tests passed. The desktop rclone/session/
LocalCrypt group passed 66 tests; the final expanded review group passed all 8
tests, including exclusion-aware revision checks, Qt early proceed, stale review,
revocation, mandatory crypt validation and a new encrypted destination. The Go
suite passed under the race detector, including read-only native reviews and
metadata revision changes. Ruff and whitespace checks passed. The shared-review
iPhone source snapshot is `a0f1c671a6b844d7184075aece24d3dffe2026f63a27d0ff97bdbdf7823b34a6`.

Metadata revisions detect changes observed by the engine; neither dry-run review
nor a last check provides a transaction lock against an external writer after
that check. Early proceed deliberately waives complete comparison, never the
credential/scope or encrypted-integrity checks. Native iOS evidence is from a
simulator, not a physical device; Android native runtime was not rerun here.

## Source baseline before the ownership cleanup

Desktop workflows live in `Python/features/rclone/{actions,sync,push_policy}.py`;
mobile workflows live in `Python/logisticsmobile/{mirror_jobs,mirror_ui}.py`
and `Mobile/rclone_bridge`. The mobile packaging allowlist is in `Mobile/tools.py`.
Both sides already share lower-level commonUtils resource and persistence
primitives. Mobile now packages the portable rclone options and review modules;
the rest of the mobile backend/presentation ownership migration is pending.
The older backup/non-destructive mobile paragraph was corrected: current
desktop and mobile transfers both use destructive Sync.

## Review audit fixes and shared behavior increment

The follow-up audit reproduced two correctness gaps: desktop cleanup could turn
an unchanged encrypted generated file into an unreviewed remote deletion, and
mobile's legacy suffix migration could rename a reviewed destination at execution.
The unused suffix migration has been removed at the user's request. No migration
or new `Books-<id>` naming path remains.

- Read-only reviews now project generated-file cleanup: local removals have a
  separate `cleanup` row, and a matching/replaced remote ciphertext object becomes
  a planned deletion. Cleanup candidates and their versions participate in stale
  checks; actual encrypted cleanup still requires full authentication.
- Desktop ordinary Pull rechecks/publishes account ownership after approval and
  before starting Sync, so a competing account claim blocks all transfer writes.
- Mobile executes the exact approved job identity, remote, prefix and local target.
  A changed/removed existing mapping is rejected. A newly approved mapping is
  published only during execution; execution never re-resolves or renames it.
- Plex transfers and YouTube config/season GUI actions use detailed reviews.
  Low-level/background APIs retain explicit noninteractive execution semantics.
- Shared portable scope inference and local inventory/cleanup policy live in
  `features/rclone/transfers/scope.py` and `local_policy.py`. Desktop and mobile consume them.
  Ordinary mobile file links follow regular-file targets; crypt links still fail.
- Mobile Transfer settings exposes rename tracking, positive integer bandwidth
  and Push-only exclusions with desktop defaults. One immutable option snapshot
  feeds initial review, recheck and execution. Native filters are request-local;
  excluded destination files remain excluded from deletion, and Pull is unfiltered.
- Ordinary mobile folders can Push before Pull, inferring `Books:` from `Books`,
  or `Books:Comics` from specific local `Comics` and selected remote `Books`.
  Recorded account ownership is checked before adopting a folder.

This increment deliberately keeps mobile controller/provider files in their
current locations. Platform crypt I/O, credential storage and execution remain
adapters; mobile's restricted backend/configuration scope and managed-copy size/
count limits are not a promise of full CLI capability parity. ZIP placement,
mobile screen privacy and the agreed platform concurrency differences are retained.


Validation of this increment: the full mobile host suite passed 236 tests; the
main desktop rclone/session/LocalCrypt/YouTube regression group passed 86, and
Plex/YouTube worker checks passed 25. The final focused review suite passed 11
checks, including cleanup projection and competing-account destination ownership.
The final mobile mapping/review/folder-hub group passed 41. The Go suite passed
with the race detector, including actual exclusion-aware Sync and ordinary links.
Ruff and whitespace checks passed.

The rebuilt iPhone simulator completed all 30 native case groups plus final UI
and navigation checks. The expanded shared-review case confirms crypt cleanup
and its remote deletion, saves native option controls, and pushes an inferred
ordinary folder through a crypt remote with a followed file link and excluded
file. [Exact local evidence](../../../../../docs/development/mobile-evidence/2026-10-15-rclone-shared-behavior-ios-native-ui-local.json)
uses source snapshot `9679f166f243a6307e899ffdc9a324a10cb60b2ea3541fb9d2bb019a56b486d8`.
Older comic/EPUB test assertions were updated to inspect the currently displayed
canvas, text view and passage bookmarks; their content/privacy assertions remain.
These are simulator results; Android and physical devices were not rerun.


## Incremental mobile ownership cleanup

The Python ownership move is split into runnable backend and native-presentation
steps. No files are committed or staged in Git. All storage layouts, record schemas,
credential identifiers and native request names remain unchanged.

1. Moved the bridge client, credential packages/vault, remote copy jobs/downloads,
   ciphertext stores/providers and crypt range adapter to `features/rclone/mobile`.
   Split memory-only format readers and ordinary text resources into app-owned
   `provider_readers.py` and `text_resources.py`. The first focused mobile group
   passed 43 tests, including isolated packaged startup.
2. Moved remote/transfer/review/catalog screens to the same feature package. Split
   the shared provider reader/editor UI into app-owned `ProviderUI`; private-session
   controllers inherit that generic UI directly. Kept ordinary/native archive
   facades in `logisticsmobile/native_archives.py`. The focused presentation group
   passed 50 tests.
3. Moved the local-Push chooser form into the feature review controller, leaving
   Folder Hub with navigation/action dispatch. Updated the separate Qt proof to
   package/import the feature-owned bridge, with an isolated import regression.
4. Updated all source/test callers directly and removed old module paths, without
   compatibility forwarding files. Packaging explicitly lists feature modules and
   validates host-to-feature and feature-to-host imports before building. Added
   regression coverage for missing feature dependencies, package ownership and
   core imports that must not initialize the app, credentials or either UI.

Folder Hub, generic Files/document hosting, navigation/scenes, OS picker access,
private-session lifecycle and screen privacy stay app-owned. Generic ID validators
live in `services/identifiers.py`; generic resource-import records do not depend
on a transfer-job module for hash validation. Mobile adapters consume generic host
reader/navigation services; policy continues to live at the rclone feature root.
The Go bridge stays with native build/link tooling under `Mobile/rclone_bridge`,
including the ordinary archive/image actions shared with app document readers.

Validation: the full mobile host suite passed 239 tests after the presentation
move. Further focused archive-boundary/startup tests passed (21), as did the
portable/workspace/shared-review group (39), Qt proof/packaging checks (5), and
final chooser dispatch/startup checks (22). Seven real native bridge tests passed
against a locally rebuilt shared library, covering ciphertext reads, protected
inner archives and encrypted file operations. Final isolated packaged startup
passed; changed production modules passed focused lint and `git diff --check`.

The final iPhone simulator run passed all 30 native cases plus the UI review and
navigation checks. [Exact local evidence](../../../../../docs/development/mobile-evidence/2026-10-15-rclone-ownership-ios-native-ui-local.json)
matches source snapshot
`6e1de15ec7e056623bf0b1f008b41e0672ad023b5f391bf2ea6d489741109af1`.
Reader test helpers now resolve the displayed canvas across responsive reflows,
and EPUB checks inspect the active text/WebView; content, geometry, chrome and
privacy assertions remain. Android and physical devices were not rerun.


## Final workflow cleanup and retry alignment

Removed the obsolete snapshot-style `PullJobs`/`PullJobsUI` modules, app mixin,
packaging entries and native-window override. Existing downloaded trees and old
record files are preserved; there is no migration or automatic transfer. The
older `push_plan`/`push` hash-comparison implementation, its pending-review screen,
confirmation path and revocation scaffolding are also removed. Current Push/Pull
entrypoints and native workflow checks use `TransferReviewUI` and the same
`ReviewScan` contract. Tests for retired snapshot publication were removed;
confirmation, stale comparisons, account binding and integrity coverage remain
on the current path. Transfer-baseline validation now belongs to `mirror_jobs`.

Moved encrypted provider/store resolution into feature `mobile/file_resources.py`,
the downloaded-crypt catalog action into `mobile/localcrypt_ui.py`, and encrypted
root lookup for Folder Hub deletion into `mobile/mirror_ui.py`. Generic Files
continues to host browsing, mutation controls and ordinary text/document opening;
it calls feature adapter functions without constructing crypt provider classes
or knowing their storage layout.

The bridge now starts rclone error accounting once and retains rclone defaults:
three Sync attempts, ten low-level retries, one-minute connection timeout and
five-minute I/O idle timeout. `sync_retries.go` implements the CLI command's
high-level retry classification using operation-local stats. Fatal/non-retryable
errors stop immediately; retryable failures retry up to the configured count,
including errors recorded by the engine when the immediate return is nil.
Retry-After and retry-interval waits are cancellable. Progress exposes the attempt,
maximum attempts and retry-wait state. Managed Sync has no fixed overall deadline;
explicit cancellation still retires its handle. Comparison failures remain
incomplete and need retry or explicit early-proceed approval; bounded browsing,
comparison and other download/read operation deadlines remain.

Empty source folders are preserved on both platforms where the backend supports
directories. Desktop execution and dry-run comparison now explicitly pass
`--create-empty-src-dirs`; embedded Sync already supplied the equivalent option.
This is an explicit Logistics policy, not a Windows-specific rclone default.


Validation: the complete mobile host suite passed 236 tests, including isolated
packaged startup and the generic Files/private-session integration. All 44 desktop
rclone tests passed, including real CLI Push/Pull preservation of nested empty
folders. The Go suite passed uncached and with the race detector (38 top-level
tests); new tests cover retry recovery/exhaustion, fatal and non-retryable errors,
cancellation with Retry-After, progress fields and default timeout/retry values.
Seven real native ciphertext/archive/file-operation tests passed against a rebuilt
host bridge. Focused lint and whitespace checks passed.

The rebuilt iPhone simulator passed all 30 cases plus the final UI/navigation
review. Native pins/pulls and ordinary/crypt Push checks now drive the current
shared review controls instead of the removed workflows.
[Exact local evidence](../../../../../docs/development/mobile-evidence/2026-10-15-rclone-final-cleanup-ios-native-ui-local.json)
matches source snapshot `272ea7ab7f2f2709b4b51c620f51b753d8e389cdd8f64f053f179f2377a65437`.
Packaged rclone and app-host modules match the current checkout. Separate Books
speech edits made during the run are outside this saved native snapshot and this
validation scope. Android and physical devices were not rerun. All changes remain
local and unstaged; no commits.


## Final four consolidation items

- Shared `logisticsmobile.files_ui.local_read_available` admits offline encrypted
  reads during a managed transfer from Files, Documents and library shortcuts.
  Documents keeps crypt roots available, retains scoped provider/account identity,
  and rejects a credential generation change before publishing rows or opening.
  Credential operations still block private entry; file mutations and a second
  transfer remain blocked.
- Native comparisons record directories as well as files, including engine
  directory callbacks carrying `fs.ErrorIsDir`. Directory rows use a trailing slash
  and crypt directory decoding. Their revisions track membership/type rather than
  backend-dependent timestamps, so repeated scans are stable and an empty-folder
  addition/removal invalidates review.
- Removed persistent whole-tree content-hash baselines, the unused `initial`
  argument and schema-1/2 snapshot recovery/automatic-backup deletion. Schema 4
  persists only copy bindings. Schema-3 bindings load in place with their baseline
  ignored; loading is read-only, and the next normal save writes schema 4.
  Unsupported older records and backup trees are preserved. Metadata inspection
  retains symlink/junction/regular-file/hard-link checks and the entry bound.
  Crypt Push still authenticates every file through `mirror_validate`, validates
  encoded directory paths, and compares file and tree versions before Sync.
- Encrypted library-source discovery and reader-store resolution use feature
  adapter functions. Folder Hub delegates managed-target and decoded remote-path
  resolution to feature helpers. Generic library INI parsing, browsing and
  navigation stay app-owned.

Native coverage now opens private files through Documents, the main library and
Documents' library shortcut during the same real throttled encrypted Pull. Each
path must complete before the download, preserve its cancellation handle and
leave the one-transfer restriction intact.


Validation: all 243 mobile host tests and 44 desktop rclone tests passed. The Go
suite passed uncached and with the race detector (39 top-level tests), including
stable empty-directory review revisions, additions/removals and crypt directory
name decoding. New host checks cover metadata-only inspection, hard-link refusal,
mutation during crypt authentication, schema-3 binding retention, preservation of
unsupported recovery records, and private Documents/library entry during transfer
with stale-credential refusal. Seven real ciphertext/archive/file-operation tests
passed against the rebuilt host bridge. Focused lint and whitespace checks passed.

The rebuilt iPhone simulator passed all 30 cases plus the UI/navigation review.
The actual throttled encrypted Pull stayed active while Documents, the main
library shortcut and Documents' library shortcut listed and opened completed local
ciphertext. Assertions retained the transfer cancellation handle, one-transfer
restriction and reader content after cancellation.
[Exact local evidence](../../../../../docs/development/mobile-evidence/2026-10-15-rclone-final-four-items-ios-native-ui-local.json)
identifies source snapshot `6bfa84cf5919a576fa780ed1b3c3e4f458e6fa193531e21c50cad52f4c3837d6`.
The rclone/shared-policy and affected library/Files/navigation files match that
snapshot. Concurrent Settings extraction (`settings_ui.py`, `app.py` and the
build-version service) happened after staging and is outside this native snapshot.
The native suite completed successfully; its log also includes an unrelated
background imported-comic metadata-index password exception. Android and physical
devices were not rerun. No changes are staged in Git and no commits were created.

### Review retries and retirement of per-file native mirror operations

Mobile dry-run comparisons now share Sync’s CLI retry classification, limits and
cancellable retry waits, without a fixed overall deadline. Each attempt owns new
comparison rows and revisions. Shared review snapshots replace old rows
atomically, and final native results are published after the polling thread
retires. Desktop retry log boundaries discard failed-attempt rows as well.
Exhausted/cancelled scans remain incomplete; explicit early confirmation still
waits for retirement, and crypt/destination safeguards still precede execution.

Removed the obsolete native mirror list/read/stat/mkdir/write handlers,
implementations, allowlist entries and byte counter. Host mocks now expose a
test-only download hook. Go and simulator fixtures use folder Sync to seed,
read back and inspect remote data. Crypt fixture seeding authenticates ciphertext;
the large download fixture is pushed through the reviewed production workflow.
The native `mirror_validate` operation and descriptor guards remain. Regressions
cover corrupt ciphertext, digest correctness, stale remote review revisions,
changed credentials, nonzero-offset/hard-linked/nonregular descriptors, and
explicit rejection of retired operations.

Validation: 46 desktop rclone tests, 39 focused mobile transfer/UI tests and six
Python cloud-boundary tests passed. The Go suite passed uncached and under the
race detector (44 top-level tests); seven real native crypt/archive/file-operation
tests passed against the rebuilt host bridge. Focused lint and whitespace checks
passed. The full mobile host run completed 246 tests with two errors outside this
change: reader temporary-directory cleanup (`Library` still being written), and
a privacy test double missing `retire_private_comic_batch`. Those concurrent
reader/privacy changes were left intact; this is not a clean full-suite result.

The rebuilt iPhone simulator passed all 30 cases plus final UI/navigation review,
including actual migrated Sync fixture setup/readback, shared review confirmation,
crypt authentication, and Documents/library reading during an encrypted download.
[Exact local evidence](../../../../../docs/development/mobile-evidence/2026-10-15-rclone-review-retries-native-cleanup-ios-native-ui-local.json)
records snapshot `be466eacc81d801873c6296082ed3b1509975f5d2416b0e1b929a754e521756c`.
All changed review/transfer implementation files match the tested payload.
A concurrent credential-generation check added to `mobile/cloud_ui.py` after
payload creation is outside this native snapshot. Native logs also contain an
iOS widget teardown callback exception; the suite and strict report verifier
completed successfully. Android and physical devices were not rerun. No Git
staging, commits, uploads or publication were performed.
