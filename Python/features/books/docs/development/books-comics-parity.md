# Books and Comics desktop/mobile parity

[Developer index](../../../../../docs/development/development.md) · [Mobile architecture](../../../../../docs/development/mobile-architecture-roadmap.md)

Updated October 15, 2026. Delivery order: EPUB navigation/resume/search, comic
spreads/navigation, then library/editing. The core implementation below is local;
full desktop/mobile parity is not claimed. Differences and validation scope are
explicit so shared parsing is not mistaken for matching product capabilities.

## Current capability assessment

| Capability | Native implementation | Remaining desktop differences |
| --- | --- | --- |
| EPUB parsing and XHTML | Shared feature package/parser and named-entity handling | Simplified renderers retain different supported presentation styles |
| EPUB contents and links | Imported and provider rich rendering share nested contents and safe archive-local links | Simplified HTML/CSS remains less complete than the desktop renderer |
| EPUB turns | Imported and native provider WebViews move a viewport at a time and cross chapters | Desktop has discrete adaptive page/spread layout; unsupported-backend provider fallback uses bounded text passages |
| EPUB resume/bookmarks | Imported chapter path + UTF-16 DOM text offset; exact session passage anchors for providers | Desktop Qt offsets and browser DOM offsets use the same units but have different rendered-text models; records are not interchangeable |
| EPUB search | Feature-owned Unicode casefold search, wrap, UTF-16 ranges; imported and native provider WebViews highlight selection | Search remains within the current chapter |
| EPUB speech/appearance | Native offline read-aloud, selected/current passage, speed, sentence-boundary pause/resume, range follow; local font families, custom spacing/width and shared desktop themes | Resume repeats the current utterance; physical-device audio/accessibility and fixed-layout EPUB fidelity remain to validate |
| Comic page policy | Shared natural order, resource-fork exclusion, explicit native decoder limits | Mobile PNG/JPEG/static WebP only; broader native decoders remain outstanding |
| Comic spreads | Shared page rules and manga order; one native composite zoom/pan surface with proportional pages | Mobile composite output is bounded to 16 MP / 8192 pixels per side; physical pinch ergonomics remain to validate |
| Comic navigation | Spread-aware turns/swipes, direct page selection, imported first/last and adjacent comics; provider adjacent comics within a managed folder | No adjacent-folder route for standalone encrypted-copy UUID storage; no desktop slider/held-key UX |
| Comic resize | Imported and provider auto layouts share a feature-owned viewport watcher; defer while zoomed | Physical-device gesture and resize validation remains outstanding |
| Imported library | Incremental persistent ordinary-import metadata index and shared suggestions; imports open directly and remain in document sessions | Catalogue shows configured folders only; provider-wide indexing and native processing/organization remain outstanding |
| Single metadata editing | Shared feature patch helpers for provider and ordinary imported EPUB/comics | Standalone encrypted imports need a native archive writer before rewriting is enabled |
| Comic batch metadata | Ordinary-local and managed LocalCrypt recursive selection; suggestions, explicit fields, all-file preflight, verified per-file publication, cancellation/retry and private retirement | Imported-library selection UI removed; standalone encrypted imported publication and live-remote recursive editing remain outstanding |
| Processing | Existing desktop compression/encryption/conversion untouched | Native compression, CBR conversion and organization require additional codec/job work |

Provider EPUB positions/bookmarks deliberately remain in memory. Ordinary import
records remain UUID/digest-owned. Private models, titles and image bytes must not
enter ordinary recovery, recent files or persistent collection caches.

## Ownership and implementation

Keep separate Books and Comics engines under the established Books & Comics
feature group. No new combined feature package or runtime ID is needed.

Books owns:

- `xhtml.py`: shared offline named-entity parsing; no DTD/network fetch.
- `locations.py`: validated location shape, nested contents/link destinations,
  sanitized-body text indexing, Unicode search and UTF-16 range conversion.
- `mobile/content.py`: inert HTML, local-link encoding and provider text fallback.
- `mobile/presentation.py`: WebView bridge, screen turns, visible text anchors,
  resize restoration, selection highlighting and navigation rejection.
- `mobile/provider_reader.py` and `private_view.py`: private native rich EPUBs,
  shared safe HTML/bridge, nonpersistent iOS store, Android storage/cache restrictions,
  byte bound before toolkit calls and explicit disposal. Unsupported backends use
  `mobile/text_reader.py`'s bounded native passages.
- `mobile/appearance.py`: common native appearance form; hosts save preferences.
- `mobile/metadata.py`: native EPUB field values and sparse patches.

Comics owns:

- `pages.py:comic_page_names` and `double_page_indices`: shared page/metadata rules.
- `reading.py:visible_pages`: common spread decisions. The desktop filesystem
  sibling import is now lazy so importing these decisions is portable.
- `mobile/{pages,validation}.py`: mobile page-format/image bounds.
- `mobile/navigation.py`: validated spread loading, forward/backward spread bounds
  and naturally ordered neighboring identities supplied by the host.
- `mobile/composite.py`: bounded, memory-only native bitmap composition with
  common-height proportional pages, manga order and transparent gutter. The gutter
  is computed from the fitted viewport to retain the desktop's eight-point spacing.
- `mobile/presentation.py`: one native canvas per page/spread, shared zoom/pan,
  fit/dispose and prevention of swipe paging while zoomed. Its shared viewport
  watcher refreshes fitted imported/provider pages and spreads in every layout mode;
  hosts own task/session lifetime. Explicit viewport bounds prevent Android from
  clipping the second page when an ancestor retains a larger minimum width.
- `mobile/metadata.py` and existing `edit_state.py`: native field/patch semantics,
  mixed-field state and explicit-field batch form.

The mobile host owns the catalogue, providers, credentials, UUID identities,
session ownership, routes, persistence callbacks and publication. The remaining
host reader methods compose those services; format parsing/search/spread rules
are not duplicated there. commonUtils continues to own generic archive sources,
atomic publication, native canvases/gestures and toolkit mechanisms.

`Mobile/tools.py` explicitly stages every added runtime module. Portable feature
imports do not load Qt, Toga, Pillow, Rubicon or Java. Platform presentations may
load Toga; native image decoding remains subject to the mobile bounds.

## EPUB location and lifecycle contract

Legacy schema-1 records, integer chapter positions and chapter bookmarks remain
readable. Optional `location` stores `{path, offset}`; `epub_bookmarks` stores the
same bounded shape. Legacy chapter bookmarks open chapter starts; new bookmarks
can distinguish multiple passages in one chapter. Location writes retain
revision/conflict checks and are bounded by the existing private record size.

Each rich WebView has a fresh root token for each rendered chapter. The trusted
bridge checks a host-injected meta token, rather than `document.baseURI`: Android
Toga uses `data:` URLs for small documents and ignores the supplied root URL. Book
scripts and external resources remain stripped/blocked. Trusted application code
is injected through the native evaluation API after load; no book-provided script
is enabled. Internal-link callbacks resolve through the feature's archive-local
path policy. Bridge messages contain only actions/offsets and are rejected on a
stale reader/epoch/session. Scroll saves are debounced; abrupt termination can
lose the last unsaved movement. Closing during a pending location save is refused
until that operation retires.

Text offsets index sanitized DOM text. They are stable across viewport/font
changes within that rendering model, not a promise of a common desktop/mobile
synchronization file format. Images, blocks and Qt document separators can affect
platform-specific offset interpretation.

The EPUB touch handler suppresses single-finger page scrolling only. Two-finger
movement reaches the host font-size gesture, which reflows the DOM without
changing the WebView scale. SVG-wrapped raster covers pass through the bounded
archive-local image loader; SVG markup and active attributes are discarded.

Provider text anchors and bookmarks stay controller-owned and clear on close.
Suspend disposes provider rich/passage/spread presentation; reentry reads again
under the originating provider's existing revision and credential checks. Private
rich EPUBs use a nonpersistent WKWebsiteDataStore on iOS; Android disables DOM and
form storage, file/content access and HTTP cache. A UTF-8 byte bound refuses HTML
larger than 2 MiB before Toga's large-content disk fallback. Close detaches the view,
clears the native document and disables callbacks; Android also destroys it. This
is not a claim about operating-system memory snapshots or secure RAM erasure.

Applying appearance retires the suspended flag after rendering so returning does
not schedule a second asynchronous load that disposes the new WebView. Closed
bridges reject late load/navigation callbacks. Provider viewport tasks cancel on
suspend/close and are restarted when the current session renders again.

## Imported metadata publication

`logisticsmobile/library_edits.py` owns the import-copy transaction:

1. Revalidate the library record/checksum and prepare the feature metadata patch.
2. Stage a replacement and verify the complete resource manifest and format model.
3. Compute the new checksum/revision and durably write a bounded `.edits/<id>.json`
   journal containing the before/after records.
4. Publish the archive, then the checksum record, then remove the journal.

On reopening, a journal with the new archive checksum completes the record write;
a journal with the old checksum and old record is abandoned. Unexpected record
or archive changes preserve the journal and report a conflict. Malformed journals
are preserved. Symlink journal paths are refused. The original external import
source is never changed. Publication is not cancelled between the archive and
record steps; this prevents cancellation from intentionally creating a half-save.

Comic batches preflight every selection before the first write. Publication is
per file, not an all-or-nothing collection transaction. Successful records refresh
the retry baseline; failures retain form values. Batch cancellation is checked
between comics and is not forwarded into the active comic replacement.

## Verification and remaining validation

Generated-book tests cover entity handling, local links/fragments, UTF-16 offsets,
casefold expansions, search wrap, legacy/new bookmarks, spread bounds, landscape/
DoublePage decisions, failed-second-page retention, natural siblings, resource
preservation, stale edits, batch preflight and checksum-record recovery.

Mobile widget tests cover imported search/resume/bookmarks, provider search and
close cleanup, spreads, metadata editing and existing reader/session/workflow
contracts. Desktop Books and Comics regression checks retain existing behavior.
A headless Chromium check additionally exercised real DOM anchor geometry,
Unicode selection, viewport turns and resize restoration.

Targeted Android emulator and iPad simulator evidence is recorded separately from
release certification. Both use a separate probe app ID and synthetic files. The
Android probe rebuilds the Java/Python app with the existing JNI bridge; the iPad
probe uses the existing simulator executable with current staged Python sources.
Neither is a rebuilt Go bridge, full release suite or physical-device result.
Real pinch/swipe ergonomics, physical-device storage behavior and release builds
still need device validation.

The general portable smoke harness has an existing declaration mismatch: credential
replacement/lock tests are absent from `smoke.py:EXPECTED_TESTS`. Its contract is
unchanged by this work. Reader/format/packaging tests can run directly with the
portable import blocker; no full-smoke success is claimed.

### Recorded local results

- 47 desktop Books tests passed.
- 78 format/library/comic regressions passed; the portable subset was also run
  with desktop-only imports rejected (31 tests).
- The 232-test mobile widget run found two integration regressions, corrected
  and verified by targeted reruns. Its two localhost-chat errors came from the
  sandbox socket restriction; the affected chat/workflow tests passed when
  permitted to bind their synthetic loopback server. This is aggregate run plus
  rerun evidence, not a claim of one final clean full-suite invocation.
- Reader-session, provider-reader and new reader-parity widget tests passed after
  the final controller/persistence changes. Ruff and diff whitespace checks passed.
- Eight targeted iOS checks passed: bridge installation, screen-turn location
  saves, Unicode search highlight, precise bookmark/reopen, imported metadata
  publication, provider search/bookmark cleanup, manga spread turns and native
  explicit-field batch metadata.

See the [simulator report](../../../../../docs/development/mobile-evidence/2026-10-15-reader-parity-ios-native-probe.json),
[probe source](../../../../../docs/development/mobile-evidence/2026-10-15-reader-parity-ios-probe.py) and
[synthetic manga spread](../../../../../docs/development/mobile-evidence/2026-10-15-reader-parity-manga-spread.png).
The report includes the dirty staged-source manifest and probe/executable hashes.
No production bundle, real book, remote account or real device was used.


### Android and iPad reader validation, October 15

The standalone synthetic probe now checks 14 cases on each target: trusted EPUB
bridge installation, nested TOC anchors, viewport turns and location saves,
Unicode range highlights, appearance anchors, portrait/landscape passage retention,
internal/external link policy, bookmark/reopen, private rich search/appearance/
suspend/reentry/cleanup, manga/DoublePage/landscape spread turns, failed-page
retention, fitted spread bounds and controls, imported/provider auto rotation, and
precise resume in a second process. Screenshots are inspected separately from the
navigation assertions; the spread check also verifies equal content widths and
that both pages fit inside the window.

Android validation found the `data:` URL bridge rejection. Native appearance
reentry also exposed a duplicate provider load, fixed by retiring the suspended
flag when the new page renders. Screenshot inspection found an Android spread
extending beyond the phone; feature-owned page bounds now constrain it to the
actual window, and fitted readers refresh on viewport changes in every layout
mode. Private reader and search messages use short lines to avoid forcing a wide
phone layout. The shared Books bridge also watches its current pane width so
Android EPUBs return to portrait width while preserving the text anchor. Hosts
cancel those watchers with their reader sessions. No commonUtils/native bridge
edits were needed for these fixes.

The private view checks confirm the native nonpersistent/cache configuration and
scan the app cache/data container for a random synthetic plaintext sentinel after
closing. They do not certify physical-device storage or OS memory behavior.

Current evidence: [Android report](../../../../../docs/development/mobile-evidence/2026-10-15-reader-validation-android.json),
[iPad report](../../../../../docs/development/mobile-evidence/2026-10-15-reader-validation-ipad.json),
[Android spread](../../../../../docs/development/mobile-evidence/2026-10-15-reader-validation-android-spread.png),
[iPad spread](../../../../../docs/development/mobile-evidence/2026-10-15-reader-validation-ipad-spread.png), and the
[reusable standalone probe](../../../../../Mobile/native_tests/tests/logisticsmobile/reader_parity_probe.py).
Each report identifies the staged dirty-source snapshot and native artifact hash.

The targeted host suite passes 22 reader/session/private-view tests; format,
location and packaging checks pass 33 tests. The isolated desktop Books suite
passes 47 tests. These results supplement the earlier aggregate runs above.

At this validation stage, read-aloud, typography and library editing were still
pending. The later sections below record the implementation and new validation;
fixed-layout EPUB fidelity, private recursive batches, processing and physical-device
validation remain open.


### Composite mobile comic zoom

Two-page spreads now share one native image and zoom owner. Native UIKit/Android
composition preserves visual manga order, proportions and alpha without temporary
files. Geometry caps the combined bitmap before allocation; iOS renderer scale is
fixed to 1, independent of screen density. Private readers prepare a replacement
before clearing the displayed view. A corrupt image that passes header inspection
therefore cannot erase a valid zoomed spread or advance the selected position.

The native probe exercises whole-spread zoom and pan, swipe suppression while
zoomed, rotation deferral until fit, disposal of old composite pixels, private
suspend/reentry and failed native decoder retention. Android panning uses native
MotionEvent delivery; iPad uses native UIScrollView zoom/content offsets. These
checks validate the native rendering/interaction path on simulators, not physical
multitouch ergonomics. Source pixel samples and screenshots verify manga order,
transparent gutter and that the fitted surface remains inside the window.

Composite evidence is recorded separately from the earlier two-canvas runs:
[Android report](../../../../../docs/development/mobile-evidence/2026-10-15-composite-comic-zoom-android.json) and
[iPad report](../../../../../docs/development/mobile-evidence/2026-10-15-composite-comic-zoom-ipad.json).


The final composite run passes 18 targeted checks on each platform, 25 mobile
widget/session checks, 37 portable geometry/reader/packaging checks and 58 desktop
Comics regressions. Desktop tests use an isolated `COMMONUTILS_STORAGE_ROOT` under
the temporary validation directory; the initial default AppData location was
blocked by the sandbox. Pixel inspection confirms the rendered native bitmap's
manga order and transparent gutter; fitted spacing follows the shared desktop gap
rather than growing with low-resolution source pages. The combined output budget
is checked before native allocation and remains independent of device DPI.


### Native speech, typography and collection editing

Books owns `mobile/speech.py`, `speech_native.py`, `speech_view.py`,
`typography.py`, shared `themes.py`, and the Android speech listener/service-query
sources. The host build registers/stages the feature's Java directory and merges
its Android TTS-service query idempotently. Android exposes only voices marked
local and installed; iOS uses installed system voices. Native completion/error
callbacks carry opaque generation IDs. Playback queues bounded UTF-16 utterances,
follows their ranges and clears all queued text on retirement. Pause/resume repeats
the current utterance boundary on both platforms. Private panels dispose speech
before suspend, chapter replacement or close; speech never writes text to recovery.

Typography validates local font families and whole-number spacing/width values,
uses the same explicit theme colours as desktop, and retains logical DOM anchors.
Selection offsets are cached across native focus/resize and cleared by new reader
interaction. Short restoration suppression prevents delayed native scroll events
from rounding a restored anchor back to the beginning of its wrapped line; explicit
user turns and pointer/keyboard input retire that suppression immediately.
Rich-view width uses the native pane rather than the content's own minimum width,
preventing a shrinking-width feedback loop after returning from appearance on
Android. Batch forms constrain their controls to a phone-safe width, and bookmark
pickers ignore transient stale native indices while their choices are replaced.

Comics owns portable metadata search/suggestion extraction and recursive selection/
preflight in `mobile/collection.py`. Desktop and mobile share list-value rules via
`catalog_values.py`. At this stage, the host's imported index was memory-only, keyed by record digest,
bounded to 200 ordinary imports and 4,096 characters per field, and excludes protected
metadata. Metadata edits refresh the catalogue; its Refresh action reloads imported
records as well as folder discovery. Batches support ordinary local CBZ/ZIP trees
with 200-comic/10,000-entry/16-level bounds. All baselines and patches validate before
writing. Publication remains per comic with cancellation between saves; partial
success and retry baselines are retained. Forms reject reentrant Apply and disable
fields/suggestion controls until publication returns.

At this stage, private recursive provider batches, larger collection indexing, encrypted standalone
archive writers, native processing jobs, fixed-layout EPUB fidelity, and physical
speech/gesture/accessibility/release validation remained open. No private metadata is
routed into the ordinary index to make these gaps appear closed.

Targeted evidence: [Android](../../../../../docs/development/mobile-evidence/2026-10-15-speech-typography-library-android.json)
and [iPad](../../../../../docs/development/mobile-evidence/2026-10-15-speech-typography-library-ipad.json). These use
synthetic files and a separate app ID; Android rebuilds its Java/Python app with
the existing JNI bridge, and iPad reuses the simulator executable with current Python.
The speech checks require actual native completion of a nine-unit selected passage,
exercise pause/resume and private suspension cleanup, and verify computed typography,
precise resume, metadata search and verified recursive publication on both platforms.
They are not physical-device or release certification.

Both native targets pass 23 cases, including process-restart precise resume. Android
offers nine installed offline voices and iPad 68; the probe observes real native
completion, but does not audition physical-device audio. The final scoped reader/UI
suite passes 20 tests, portable reader/collection/catalogue contracts pass 59, and
the isolated desktop Books suite passes 47. The aggregate mobile run executes 240
tests with eight errors in the concurrent rclone mirror/folder-hub work (missing
`MirrorJobs.state` and legacy `baseline` records); it is not a clean full-suite result.
Those unrelated changes were left separate.

### Private recursive batches and larger imported catalogues

`features/comics/mobile/private_batch.py` now owns the private recursive plan.
Managed LocalCrypt trees share ordinary scan bounds (200 comics, 10,000 entries,
16 levels), but retain only ComicInfo snapshots with an 8 MiB aggregate limit.
Archives open one at a time through an injected reader scope; the host closes native
archive caches and clears passwords when each scope exits. Preparation rejects an
unreadable/wrong-password archive before any write. Apply rechecks every baseline
and patch before the first publication. Existing `ManagedCopies.save_metadata`
transactions stage ciphertext, verify all resource bytes and revalidate source and
credentials before replacement. Successful baselines update for retries; a
post-publication revision error stops the batch and requires reopening.

The host owns credential/client generation, provider identity, native scene limits
and lifecycle signals. Leaving the form, concealment, resource release or credential
replacement cancels the plan and clears fields, suggestions and snapshots. A stale
callback cannot restart publication. Private batches are never workspace records,
recovery drafts, persisted suggestions or ordinary-import index entries. Live
remote trees still require a managed copy before recursive editing.

`features/comics/mobile/index.py` replaces the first-200 in-memory index with a
disposable SQLite cache under the imported library. Hosts supply UUID/digest records,
physical stat signatures and a loader that rejects protected archives before password
lookup. The feature owns field bounds, casefolded token search, incremental reuse,
chunked commits, pruning and suggestions. Every ordinary import is eligible;
completed entries survive restarts and interrupted scans. Failed entries retry on
Refresh. A cancelled scan checks its owner again after acquiring its worker lock,
before opening or pruning the database. The Books and Comics catalogue now shows
configured library folders only. The bottom imported-items section, selection
switches, batch-edit button and imported-results paging were removed at the user's
request. The folder-search field is also removed; imports still open directly and
remain available through document sessions. Single and batch comic forms
use the same persisted ordinary suggestion catalogue. Private batch suggestions
remain scoped to their current in-memory snapshots.

Native evidence: [Android](../../../../../docs/development/mobile-evidence/2026-10-15-private-batch-large-library-android.json)
and [iPad](../../../../../docs/development/mobile-evidence/2026-10-15-private-batch-large-library-ipad.json). The separate
probe uses synthetic credentials, actual native encryption/archive transactions,
plain and inner password-protected comics, and 260 real imported archives. Portable
tests additionally exercise a 5,001-entry index, incremental reopen, interrupted
scans, corrupt-cache recovery, Unicode matching and stale-worker cancellation.
These results cover emulators/simulators and do not constitute physical-device or
release validation. Native processing/organization, standalone encrypted imported
rewrites and provider-wide catalogue indexing remain separate parity work.

The final mobile regression run passes 251 tests, and portable collection/reader
contracts pass 29 tests. Each native target passes 10 collection cases, including
a second-process index reopen without archive reads. Native runs cover 260 actual
imports; the 5,001-entry scale check is portable, not a device performance claim.

Closing a private iOS book WebView disables native callbacks and clears the live
DOM before loading its blank document. This also covers a retired, hidden pane,
where WKWebView can defer replacement navigation. Android continues to destroy
the private native WebView. Closing is idempotent and rejects further content.
