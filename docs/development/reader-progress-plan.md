# Unified document progress investigation and refactor plan

Status: investigated and implemented November 7, 2026 across coordinated storage,
mobile, format-adapter and independent-acceptance work. Final native acceptance
and release delivery are separate gates below. Remaining integrated-device
coverage belongs to the release run; duplicate pre-release runs are not required.

The investigation reproduced lost durable progress in ordinary mobile file readers
and independent reading sessions when the same nested file opened through Home and
Local. Synthetic EPUB, CBZ and PDF documents exercised the actual mobile host
controllers. The refactor addresses document identity and progress storage together,
then connects format adapters to a shared observation and lifecycle contract.

The [private state contract](reader-state.md) remains the encryption and history
clearing baseline. This plan does not authorize weakening that contract.

## Implementation and validation status

The shared implementation lives in `services/documents/progress.py`,
`progress_identity.py` and `progress_store.py`. Mobile provider and imported-library
readers now use it, along with notebook, video and desktop reader adapters.
`PrivateSessions` uses canonical identity while retaining independent access checks.
Credential encryption remains in its existing owner.

Focused host acceptance passes nested Home ↔ Local opening and fresh app instances
for EPUB, CBZ, ZIP and PDF. Core tests exercise actual separate-process persistence,
newer observations overriding stale writers, independently coalesced bookmarks,
interrupted writes, encrypted password migration and clear fences. Independent
video acceptance uses separate processes and real credential-password ZIP encryption
for playback time and options. These results do not establish native rendering.
Native Duo process-relaunch acceptance now restores the measured EPUB passage,
comic/PDF pages, text and Markdown scroll, notebook page UUID after reordering,
and supported image zoom. The native bridge verifies protected EPUB/video
checkpoint encryption and wrong-password rejection. Focused iOS video restart
checks cover ordinary and LocalCrypt titles with embedded subtitles or explicit
Off, audio selection, delays and subtitle size. Android has separate passing
ordinary EPUB Home/Local and encrypted-comic restart receipts. The final isolated
Android process-restart check also restores protected EPUB and comic locators,
authenticates unchanged ciphertext and rejects wrong passwords in both processes.
An earlier overloaded diagnostic's initialization timeout remains separate evidence.
A focused iOS process-restart check also verifies actual external
subtitle selection despite a conflicting language preference. Android video
restart checks pass ordinary and LocalCrypt titles with embedded subtitles or
Off, actual playback time, audio selection, delays, size and AES authentication.
Failed or incomplete native attempts are retained separately from passing receipts.

The tracked regression owners are `Python/tests/readers/test_unified_progress_core.py`,
`test_formats_progress.py`, `test_unified_video_progress_acceptance.py`, and
`mobile_build/tests/reading/test_unified_progress_acceptance.py`. The focused native
driver selects `mobile_build/native_tests/tests/logisticsmobile/unified_progress_probe.py`
with `--probe unified-progress`; its orchestration has separate tooling tests.
Raw reports, build manifests and captures remain in ignored test evidence.

Current platform limits are explicit: protected sources without a credential ZIP
authority remain session-memory only; a separate cloud/home-server follow-up covers
the Saved-credential authority gap. Session-Only credentials imported from an
encrypted ZIP can supply durable encrypted progress after the same credentials
are unlocked again. Standalone images persist supported zoom, while the
shared canvas has no portable pan setter. Android PDF restores supported zoom;
iOS also exposes a normalized center. Text and Markdown preserve mode and normalized
scroll within a compatible content revision; supported native source editors also
use a UTF-16 line anchor without saving document text. A text edit invalidates an old locator
rather than applying a stale location to unrelated content.

## Confirmed causes

### Ordinary files are routed into a credential-only store

`services/documents/mobile_storage.py:open_provider_document()` opens local EPUB,
comics, PDF and text through the provider reader. Its normal opening workflow
constructs `mobile/provider_progress.py:ProviderProgress`, which always constructs
`services/documents/credential_state.py:CredentialState`.

An ordinary `LocalFiles` provider has no credential ZIP authority. Consequently,
`CredentialState.save()` catches the missing authority and saves only to that
store instance's `memory` dictionary. A fresh store cannot recover the position;
no durable position file was created in the reproduction. `load()` also labels
this ordinary no-credential case as `locked_state`, although there is no old
encrypted checkpoint needing a previous password.

This is incorrect store selection, not evidence that credential encryption itself
is broken. Ordinary local persistence must not be added as a fallback inside
`CredentialState`, because that would weaken private readers too.

### Home and Local can disagree about document identity

`mobile/document_sources.py:_reopen_file()` opens a Home/Recent local reference
using `LocalFiles(file.parent)` and the basename. `mobile/files_ui.py:read_managed_file()`
and browser drawers can supply the collection root and a nested relative path.

`mobile/private_sessions.py:PrivateSessions.identity()` hashes the provider root,
a separator and the supplied key independently. These refer to the same file but
produce different identities:

| Entry point | Provider root | Key |
| --- | --- | --- |
| Home/Recent | `Local/Books` | `Fixture.epub` |
| Local browser | `Local` | `Books/Fixture.epub` |

The manager then creates two controllers and two independent positions. Its
same-process `positions` cache uses that same identity, so it cannot bridge the
two openings. This also consumes two document slots. Top-level files whose root
and key happen to match do not demonstrate this particular identity defect.

### Existing progress mechanisms are fragmented

The older imported library persists EPUB locations and comic positions through
`mobile/library.py:LibraryStore.progress()`. It is a different owner from the
ordinary provider reader. Existing library restart tests therefore do not certify
current Local/Home opening behavior.

`PrivateSessions.positions` separately remembers page/offset or text/preview
scroll in RAM. Provider checkpoints carry page, per-chapter offsets and comic
half; they do not include text/Markdown scroll. Video has another persistence
policy in `services/documents/video_progress.py`, including content fingerprints
and encrypted storage paths. Notebook `Editor` initializes its selected page to
zero, and its page-navigation command changes in-memory state without invoking
the content checkpoint. These owners need explicit progress adapters.

Desktop EPUB and comics already have ordinary local state implementations in
`features/books/preferences.py` and `features/comics/reading_state.py`. Desktop
PDF conditionally uses the credential-state adapter. Reuse the shared contract
across hosts while preserving working desktop locators and preferences.

## Reproduction and build scope

The host reproduction opens a nested synthetic file using Home's local reopen
function, moves within it, waits for the progress task, and opens the same file
using the Local browser's provider-root representation. It then closes readers
and constructs another app instance over the same storage.

| Format | Position reached through Home | Opening through Local | Fresh app, Home reopen |
| --- | --- | --- | --- |
| EPUB | Chapter 1, UTF-16 text offset 1234 | Offset 0, separate controller | Offset 0 |
| CBZ | Second page | First page, separate controller | First page |
| PDF | Second page | First page, separate controller | First page |

All three produced two controllers and no durable provider position files.
The PDF probe substitutes the existing host PDF decoder fixture; the checks do
not establish native rendering, WebView timing or physical device lifecycle behavior.
The manager's scratch context owned and removed the synthetic fixture storage.
The ten existing credential-state regressions also passed, covering encryption,
password migration, tampering, source binding and history clearing. Those checks
exercise the protected store, not native mobile resume behavior.

The latest successful Duo deployment receipt located during the investigation
completed November 6, 2026 at 22:23 Toronto time, with Logistics source
`082fde365963a804020aec3f2af700c180da23e7`. The four relevant identity and persistence
files were byte-for-byte identical to the investigated checkout. This associates
the defects with a delivered build; it is not a fresh query of the device's
currently installed app. Device installation and data were not changed.

## Proposed shared contract

Keep app policy in `services/documents/`. Hosts supply identity, access authority
and lifecycle events; format owners translate visible locations. Reuse commonUtils
atomic persistence and existing credential encryption. Do not introduce a second
crypto implementation or store progress in document contents.

### One identity independent of navigation

Introduce a document identity resolver used by session lookup, checkpoint lookup
and reopen references. A destination tab, browser root, view instance, temporary
decoded path or writable/read-only flag must not define document identity.
Access grants remain independent: matching identities must never upgrade a
read-only session or reuse revoked authority.

For ordinary local files, resolve the admitted full path first. Inside managed
storage, derive identity from a stable storage-root identifier plus relative path,
including the existing iOS Documents relocation rules. Registered external roots
need their own stable identity. Keep resource IDs and content revisions separate.
App-managed moves should update an alias through the existing mutation owner;
independent copies remain separate unless explicitly associated.

For LocalCrypt and remote sources, use provider authority, stable storage namespace
and normalized logical document key. Private lookup identifiers remain keyed and
opaque on disk. Do not expose private paths, titles, text anchors, content hashes
or source mappings in plaintext indexes, Recent entries or diagnostics. A downloaded
copy and its remote original share progress only with verified provenance and an
explicit policy, never by filename or decoded-content coincidence.

### Explicit storage selection and outcomes

| Source policy | Progress store |
| --- | --- |
| Ordinary local document, including read-only content | Bounded app-owned atomic local store |
| LocalCrypt or private remote with usable credential ZIP authority | Existing password-bound encrypted store and opaque lookup keys |
| Protected source without usable persistence authority | Shared session-memory store, explicitly reported as session-only |
| Locked, corrupt or old-password encrypted state | Preserve original; distinguish unavailable state from a new document |

Make persistence capability an explicit provider contract. In particular, the
current mobile cipher excludes saved credential records; inventory both Saved and
Session-Only connection modes instead of assuming either can supply ZIP authority.
If a source lacks an approved key, durable encrypted progress requires that key
to become available. Do not quietly use a device key or an unencrypted fallback.

Return distinct outcomes such as restored, absent, incompatible revision,
session-only, locked/migration-required and write-failed. Ordinary local files
must never show a credential-password recovery notice. Surface a useful save
failure and retain the newest unsaved observation for retry.

### One coordinator for capture and restoration

Use a versioned checkpoint envelope containing identity binding, locator kind and
version, content revision, monotonic write sequence and clear-history generation.
Keep bookmarks separate from reading positions and appearance preferences.

The coordinator owns loading, restoring, accepting a successfully displayed
location, coalesced persistence, flushing and retirement. Restore before allowing
initial layout callbacks to publish a default page. A failed or cancelled page
load must leave the last successfully displayed position intact.

Update the shared in-memory position immediately, then persist on bounded
debounced intervals. Serialize writes per document; stale sessions, background
workers and close callbacks must not overwrite a newer observation. Resolve
multi-window conflicts using observation order, not the furthest page read or the
time an old window happens to close. Reading backward is a valid new position.

Capture and flush on route changes, close, host replacement and platform
background transitions while the necessary access authority is still valid.
Do not delay privacy shielding or revive revoked credentials to finish saving.
Continuous checkpoints limit loss when the OS terminates without a final callback;
force termination before a durable write cannot be promised lossless.

Retire the separate `PrivateSessions.positions` authority after its locators are
covered. Clear-history generations must invalidate both disk and memory caches
across scenes, so old readers cannot restore or republish cleared state.

### Format adapters

| Format | Durable locator | Restore rule |
| --- | --- | --- |
| EPUB | Spine resource identifier and UTF-16 text offset; optional bounded structural anchor | Resume the passage after layout/font/fold changes; screen page number is derived |
| Comics, including CBZ/ZIP | Archive member identity, page-index fallback and split-page half | Resolve member first; validate half against current layout and reading direction |
| PDF | Page index and normalized in-page viewport; validated page identity where available | Clamp to valid content and restore after canvas readiness |
| Text and Markdown | Logical text/section anchor and mode; normalized scroll fallback | Restore source or rendered preview after its content is ready, without persisting document text |
| Notebooks | Stable page UUID, index fallback and optional normalized viewport | Survive page insertion/reordering; navigation alone must not dirty or save ink |
| Video | Playback time, selected audio and subtitle tracks, subtitle Off state, external subtitle reference, supported subtitle scale/delay and audio delay, plus existing playback options | Apply after track discovery; preserve completion policy, global defaults and verified fingerprint migration |
| Standalone images | Optional normalized zoom/pan state | A single image has no page progress; restore view state only if supported |

Revision policy belongs to each adapter. Exact-revision rejection is safe but
should not unnecessarily reset a book after a metadata-only update. Revalidate
locators against content structure; reject unrelated replacements at the same
path. Avoid hashing entire large local or remote documents on every open.

## Implementation sequence

1. **Regression coverage and core repair.** Add the reproduced Home → Local and
   reverse flows to storage/reading tests, including nested folders. Implement
   canonical identity and explicit local/encrypted/session-memory store selection
   together. Verify EPUB, CBZ/ZIP and PDF with fresh managers and app instances.
2. **Unified coordinator.** Move capture, restoration, write sequencing and
   flush/retirement policy out of provider widgets. Reuse existing worker-draining,
   revocation and replacement protections. Add host lifecycle integration and
   accurate persistence status; remove duplicate RAM authority after migration.
3. **All format and host adapters.** Connect text/Markdown and notebooks; adapt
   video without dropping working resume/settings behavior. Migrate imported
   library and desktop readers to the same contract. Keep format parsing, native
   readiness and locator validation with their existing owners.
4. **Legacy migration and history controls.** Import recognized library, desktop,
   video and encrypted checkpoint versions once, with verified source association.
   Preserve bookmarks and unreadable originals. Use existing previous-password
   migration for protected records. Do not scan unrelated storage or invent
   progress for local readers that never persisted it. Clearing Recent must remain
   independent from clearing positions.
5. **Native acceptance and delivery.** Validate the matrix below through the build
   manager's owned disposable devices, then have the release coordinator validate
   and deliver on Duo. Record source/build identity and preserve the main app/data.

Phase 1 should be independently deliverable; fixing only session identity leaves
restart loss unresolved, and adding only local persistence leaves duplicate-reader
and conflicting-writer behavior unresolved.

## Acceptance matrix

- Every multipage format: open from Home, Local, drawer, Recent, favourites and
  Open documents; switch entry points both ways; close/reopen; restart the process.
  A file has one logical progress record regardless of entry point.
- Storage: ordinary app Local, Received Files, nested and read-only folders;
  relocated iOS Documents; LocalCrypt and remote with usable ZIP authority; Saved
  and Session-Only credentials; locked and passwordless sources with explicit outcomes.
- EPUB: within-chapter page turns and slider seeks, chapter boundaries, Unicode
  offsets, font changes, portrait/landscape and Duo front/inner display reflow.
- Comics/PDF/notebooks: split-page halves, manga direction, inserted/reordered
  pages, failed decode, delayed native rendering and notebook page UUID fallback.
- Video: selected audio/voice track, embedded or external subtitles, subtitles Off,
  supported subtitle scale/delay and audio delay survive close and process restart;
  delayed track discovery or changed track IDs cannot silently select another
  track. Verify per-video settings separately from global defaults and inspect
  LocalCrypt settings through the encrypted progress path.
- Lifecycle: immediate navigation after a seek, background/foreground, successful
  flush then forced termination, close during a write, host replacement, credential
  revocation and two scenes reading the same document in different directions.
- Integrity: interrupted atomic writes, full disk, corrupt state, unknown versions,
  replaced document at the same path and metadata-only changes. Failed persistence
  must be visible and must preserve the previous readable checkpoint.
- Privacy/history: no plaintext private locators or bookmarks; wrong-password and
  cross-source rejection; password migration; clear positions while locked; old
  pending writes and in-memory caches cannot resurrect cleared state. Clearing
  positions retains bookmarks, documents and Recent.

Existing starting tests are `mobile_build/tests/storage/test_storage_reader_opening.py`,
`reading/test_reader_lifecycle.py`, `reading/test_reader_sessions.py`,
`reading/test_reader_progress.py`, `reading/test_reader_history_controls.py` and
`Python/tests/readers/test_credential_reader_state.py`. Current opening coverage
and same-manager close/reopen checks do not substitute for cross-entry and fresh-process
coverage. Native acceptance must verify the visible passage/page, not only a stored
number or a successful open call.
