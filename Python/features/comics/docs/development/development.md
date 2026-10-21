# Comics Feature

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

Comics owns CBZ reading, metadata editing, compression/encryption, CBR conversion
and library integration. It requires the Images feature. See the
[user guide](../user/user.md) for controls and configuration, the
[compression contract](compression.md) for output rules and ComicRack compatibility,
and [file browser development](../../../../../docs/development/file-browser.md) for panels, context menus and
activation hooks.

## Implementation map

| Area | Modules and responsibility |
| --- | --- |
| Declaration | `ui_contributions.py:register()` declares CBZ type ownership, browser actions/activation, folder controls and workflows. `__init__.py` exports it; `register_file_types()` remains a compatibility helper. |
| Compression | `cbz.py` orchestrates; `sanitization.py` cleans layouts and pads names; `comicinfo.py` rebuilds page records; `compression_stats.py` reports results; `archive_io.py` builds, verifies and commits archives. |
| Other batch operations | `conversion.py` handles CBR conversion, `metadata.py` legacy author/series edits, `actions.py` organization and external reader integration. |
| Metadata model | `library.py` loads and transactionally saves documents; `selection.py` resolves batches; `edit_state.py` tracks shared/mixed values and explicit patches. |
| Metadata UI | `ui/metadata_editor.py` coordinates jobs/navigation; `metadata_form.py`, `metadata_widgets.py` and `value_popup.py` build field controls. |
| Reader | `pages.py` loads pages/covers; `reading.py` decides spreads and sibling ordering; `reader.py` and `ui/reader*.py` own windows, decoding, controls and keys. |
| Browser integration | `browser_support.py` loads CBZ panels/thumbnails and folder counts; `ui/browser_extension.py` owns per-window state; `ui/browser_services.py` shares handlers between hosts. |
| Library | `ui/library.py` adds library tabs and catalog services around the shared browser; `library_config.py` reads library names; `catalog.py` maintains suggestions. |

Comics imports shared filesystem, desktop actions and browser modules directly
from commonUtils. Extend the shared browser through declarations rather than
adding Comics checks to it.
Registration is idempotent and does not parse archives; UI imports remain lazy.

## Browser and library boundaries

The general browser and comic library consume the same declaration. Only the
library adds tabs and automatic collection-wide suggestion indexing; it supplies
its existing controller to coordinate catalog refresh and safe closing. The
controller owns readers, editors and jobs for its window. Open readers can outlive
the library; closing a reader raises its originating browser if still visible.
Shared navigation, generic panels, selection filtering and feature toggles are
covered by the [central browser guide](../../../../../docs/development/file-browser.md).

`[LogisticsComics] libraries` names immediate-child library folders in order.
Without it, existing collections retain whole-root browsing. This section or an
external-reader detection enables the folder contribution. The catalog always
belongs to the collection root, even when a library tab selects a subfolder.

## Metadata editing contract

Only explicitly changed fields are patched. No-op saves preserve archive bytes;
emptying a field removes it. Unknown elements/attributes, namespace declarations,
comments, processing instructions and existing `Pages` records survive metadata-only
edits. Image bytes remain unchanged. New known fields follow schema order without
reordering existing nodes. XML formatting and ZIP container bytes may change on a
real edit. Use [XMLFile](https://github.com/ispaure/commonUtils/blob/main/formats/xmlType.md) for generic XML mechanics;
`ComicInfoXML` owns ComicInfo field mappings and validation.

Number/AlternateNumber accept strings (including fractions and suffixes); counts,
volume and dates are integers with blank removal and the legacy `-1` sentinel.
Month/Day limits are 12/31. Existing unknown enum values and legacy strings are
retained until edited. Language labels serialize as codes; custom tags remain
valid. Explicit list edits serialize comma-separated text, while untouched text
keeps its spelling. Series complete/Proposed Values are ComicRack library fields,
so their disabled controls must not invent XML tags or modify a ComicRack database.
When extending mappings, consult the [Anansi ComicInfo documentation](https://anansi-project.github.io/docs/comicinfo/documentation),
[v2.0 schema](https://github.com/anansi-project/comicinfo/blob/main/schema/v2.0/ComicInfo.xsd)
and [v2.1 draft](https://anansi-project.github.io/docs/comicinfo/schemas/v2.1).

Preflight validates all documents and checks for external changes before the first
write. Saves stage a replacement, verify every member CRC, retain permissions and
atomically replace each CBZ. A batch is not one filesystem transaction: successful
files remain saved when a later file fails. Pending edits remain available; baselines
are refreshed from both successful and failed documents so retry/revert stays correct.
Folder selections are recursive and deduplicated. Symlinks are excluded from scans;
explicit links and hard-linked archives are refused.

**Compression has a different page policy:** it discards old per-page metadata and
rebuilds records for the selected output images to avoid maintainer-reported
ComicRack crashes. Do not apply metadata-only preservation to compression. The
[compatibility policy and evidence](compression.md#comicrack-compatibility-rebuilding-page-records)
must be retained when modifying the parser.

## Portrait wide pages on mobile

`comic_split_wide` is a separate boolean mobile preference, defaulting to `false`
for new and existing preference files without that key. The shared comic appearance
form exposes it alongside page layout. It does not change EPUB preferences.
`mobile/navigation.py` stages `(source index, half, split)` until native rendering
succeeds; hosts call `commit()` only after publishing the prepared view. Next and
Previous visit both halves in source reading order, reversing the visual order for
right-to-left manga. A strict landscape source in a strict portrait viewport is
eligible, independently of Single/Automatic/Two-page layout. Square viewports and
landscape windows keep the whole image.

Horizontal source bounds are `[0, .54]` and `[.46, 1]`, with 8% source-width
overlap. `mobile/composite.py` draws the source at an offset into a bounded, RAM-only
native bitmap; archive bytes and page counts are unchanged. Android, iOS and the
Toga dummy backend share the crop contract. Swipes and page buttons use the same
navigation path; manual zoom retains the existing pan/fit gesture contract. Layout
watchers reflow fitted views after rotation or preference changes. Provider readers
also reconcile their initial window estimate with the mounted reading pane.

Imported records persist validated `comic_half` values of 0 or 1 alongside the
original source position; older records default to the first half. Provider half
state remains in memory with its reader. Rendering errors preserve the committed
half, visible pixels and source position. `Mobile/tests/test_comic_split.py` checks
crops, directions, swipe traversal, boundary buttons, failed composition, setting
persistence, imported resume and landscape restoration with Toga's dummy backend.
Native device appearance and gestures still require device/simulator validation.

## Reader and catalog contracts

Readers sort pages and sibling comics naturally and load without extraction.
Qt decoding falls back to Pillow; display transforms must not modify archive bytes.
iOS sampled decoding reads ImageIO's actual CFString option values and converts
them to Python strings before building the options dictionary. Rubicon's native
NSString proxies cannot be used as Python dictionary keys. Native reader checks
decode a 1024 × 1536 page to 64 × 96 pixels to verify this bridge and the sampling
limit together.
Spread selection respects landscape/DoublePage pages and manga direction.
Only the latest queued page load is displayed, and failed loads retain the current
image with an error. Metadata saves refresh the archive snapshot and direction
while retaining page position; external archive changes require reopening.
Closing during a load waits for its worker. `reading_state.py` saves the last
successfully displayed page after a short debounce and flushes on file switches,
close and shutdown. State uses a hashed resolved path in shared Cache/Comics;
restoration prefers the image entry name, then clamps the saved zero-based index.
Explicit adjacent-file navigation retains its start/end behavior. The Books
`Reader.remember_position_bool` setting controls both readers.

`LogisticsComicsData/metadata.json` stores normalized suggestions and compact
relative-path records using modification time/size. Index only list fields and
Publisher/Imprint/Format, never image payloads, plot text, titles or metadata hashes.
Changed/deleted records remove obsolete suggestions. Invalid caches rebuild;
write failures leave session suggestions usable. Skip linked/data folders and
retry unreadable archives on refresh. Background suggestions must not overwrite
pending edits. Encrypted metadata must never enter this persistent cache.

## Password-protected CBZs

Use `services.documents.zip_passwords` for ancestor `[LogisticsZIP] archive_password` policy;
see [Archives](../../../archives/docs/development/development.md#password-configuration). Ordinary CBZs remain
ordinary unless explicitly encrypted. Reader/single-file editor workflows prompt
for missing/incorrect passwords and cache successful unlocks per archive in memory,
invalidating them on external file/config changes. Background previews never prompt;
locked archives use a placeholder. Compression accepts only the configured password,
never a reader's cached password or an interactive prompt, and reports failures per file.

Rewrites retain the successful input password and use AES-256, upgrading legacy
ZipCrypto. Mixed encrypted/plain entries can be read but not rewritten; authenticate
all members before replacement to reject multiple-password archives. Filenames
remain visible. Compression's temporary plaintext workspace is removed normally,
without secure-erasure guarantees. Encryption must preserve compression output
rules; see the [contract](compression.md).

The encryption action requires an ancestor INI with `[LogisticsZIP]` for every
accepted selection. Its dialog assesses once on opening, recursively deduplicates
folders without following symlinks, and refuses execution when a plain comic lacks
a nonempty configured password. The API still permits an explicit fallback password;
opening an encrypted comic without an INI still permits an unlock prompt.

Encryption streams unchanged decrypted contents, member order/names, empty folders
and comments into a verified staged AES-256 CBZ. It performs no image conversion,
extraction or sanitization. Already encrypted comics are skipped unchanged; hard-linked
inputs are refused. This is distinct from packaging a CBZ inside a separate ZIP.

## Worker and file-safety contracts

Capture inputs on the GUI thread and run disk work in background callbacks.
Comic batches cancel **after the current comic**: never forward batch cancellation
into compression's ZIP rebuild. Close/Escape waits for completion before destroying
the dialog. Report per-item failures as well as worker errors and distinguish
unprocessed files from failures/cancellation. Compression continues after failures;
organization retains its stop-on-first-error policy. Shared lifecycle guidance lives
in [UI architecture](../../../../../docs/development/architecture.md#long-running-workflows-and-safe-closing)
and [commonUtils recipes](https://github.com/ispaure/commonUtils/blob/main/ui/operation_progress.md).

CBR conversion deletes its source only after building/verifying the CBZ and refuses
existing destinations; actual extraction requires patool's external RAR extractor.
Organization copies before deleting the source. Archive rebuilds use isolated staging
and reject source changes. See [replacement rules](compression.md#replacement-boundary)
before changing compression.

## Validation

Use the [project test commands](../../../../../docs/development/getting-started.md) and
[cross-platform checks](../../../../../docs/development/platform-checks.md). Comic tests cover compression,
metadata, reader/spreads/decoding, catalog, file-type integration, passwords,
encryption and asynchronous cancellation using disposable fixtures. Shared ZIP and
browser tests belong to commonUtils. The [parity report](zip-compression-parity.md)
records decrypted full-run comparisons; ZIP container timestamps are not expected
to match. Tests do not reproduce the ComicRack crash, invoke a real RAR extractor
or replace native desktop/remote-mount validation. EPUB reading/editing belongs to the separate Books engine.

## Portable document boundary

ComicInfo reads/saves and compressed page-byte access do not eagerly load Pillow
or legacy archive tools. TIFF decoding and cover rendering load Pillow on demand
and report a missing decoder at the operation boundary. Archive rebuilding keeps
its established desktop tooling. See [mobile preparation](../../../../../docs/development/mobile-preparation.md)
for the headless checks and remaining mobile-host work.

ReadingState saves the page-list total alongside the existing index/name resume
record and provides a compact thumbnail badge. ComicBrowserMixin seeds page names
from its existing thumbnail worker for legacy-state resolution and reorder-safe
labels; painting never opens the archive. Badge state is private and follows the
existing resolved-path identity and remember_position_bool setting.

The portable `comic_page_names` helper supplies identical header-only page filtering
and natural order for imports and readers. Native ordinary encrypted comics and
LocalCrypt share a decoded archive facade and retain the same ComicDocument/ComicPages;
platform password UI stays in logisticsmobile; native decoder policy lives under
`features/comics/mobile`.

After foregrounding or completing resume-password verification, `ScreenPrivacy`
asks only the visible private owner to reload a suspended page. The owner retains
its page, route and immersive state and coalesces pending resume reads; suspension
clears only after successful page presentation. A failed suspended fullscreen
read exposes controls and its error. `Mobile/tests/test_private_sessions.py`
covers repeated password resume after memory cleanup, wrong-password protection,
page navigation after resume and recovery from a failed reload.

`mobile/pages.py` applies the native PNG/JPEG/WebP policy to `comic_page_names`.
Imports, provider readers and ordinary browser covers use that policy, including
macOS resource-fork exclusions. Unsupported image pages fail explicitly rather
than being silently omitted by provider readers. See the
[desktop/mobile parity assessment](../../../books/docs/development/books-comics-parity.md)
for remaining spreads, reader controls and collection-tool gaps.

Mobile spread loading/navigation and rendering live under `mobile/navigation.py`
and `mobile/presentation.py`, reusing `reading.visible_pages` and
`pages.double_page_indices`. Native single/batch metadata semantics live in
`mobile/metadata.py` with shared `edit_state.py`; UUID/checksum publication remains
in the mobile host. Imported metadata writes have a recoverable archive/record
journal described in the parity guide.


Native two-page spreads now compose an owned bitmap in `mobile/composite.py` and
use one native ImageCanvas in `mobile/presentation.py`. Geometry preserves page
proportions at a common height and manga visual order, with no artificial gutter
between the pages. Desktop and mobile use the same zero-gap policy. Combined
output is capped at 16 million pixels and 8192 pixels per side before native
allocation. UIKit rendering explicitly uses scale 1 so Retina density does not
multiply that budget. Android and iOS compose directly in RAM; no temporary page
files or runtime Pillow dependency are added. Toga's dummy backend uses its
existing Pillow image implementation for regression checks.

Zoom, pan, fit and gesture paging have one owner for the entire spread. Viewport
reloads defer while zoomed and resume after fitting. The host constructs a new
provider spread before disposing the previous one, so decoder/allocation failures
retain the old pixels and logical position. Private session disposal clears the
single composite image and its callbacks.


Portable comic selection and metadata plans live in `collection/`.
The host owns provider identities, imported-record signatures, async work and
publication callbacks. The feature owns metadata extraction, token matching,
suggestion generation, natural recursive selection bounds and all-file preflight.
`catalog_values.py` shares field sets, list splitting and Unicode normalization
with the desktop catalogue. Private-provider metadata never enters the imported
index. Ordinary local folder batches reuse ComicDocument's verified atomic save.

Native batch forms disable editing and reentry while applying, retain unchecked
mixed fields, and provide explicit suggestion pickers without changing form values
on construction. Imported reader saves invalidate the catalogue view/index so
search and suggestions follow the new archive revision.

`mobile/private_batch.py` owns recursive private preflight, metadata-only snapshots
(8 MiB total), per-file results, retry baselines and cancellation. The host injects
the credential-generation guard, scoped readers and existing verified encrypted
publication transaction. Navigation, concealment, memory release and credential
revocation retire its plan and wipe the feature-owned form. No private batch state
is serialized. The host prevents concurrent private batches and additional scenes.

`features/books/library/index.py` owns the mixed Books & Comics disposable SQLite index for ordinary imports, incremental
digest/stat signatures, bounded field extraction, Unicode token matching,
suggestions and 50-row paging. It scans every import, commits chunks of 25, resumes
partial scans and retries errors. Protected archives retain filename search only;
the host rejects them before any password lookup or metadata parsing. Private
providers are never fed to this index. Corrupt cache files can be recreated from
imports; archive files and recovery journals are never used as cache storage.

## Format mutations

`mutations.py` owns metadata plans, content-preserving archive rewrites and post-write format validation for desktop/mobile consumers. Storage adapters retain conflict detection, encryption and atomic publication; the mobile managed library retains recovery journals and checksum records.

## Mobile source manifest

`../../mobile_sources.json` declares this feature's selected portable/mobile sources. Update it when adding an imported module. The build tool aggregates and checks the allowlists without starting desktop registration.

## Shared mobile magnifier preference

Logistics binds single-page and spread canvases through
`logisticsmobile.magnifier.bind`, alongside PDF canvases. The host persists
`magnifier_zoom` as one percentage (150–250 in 20-point steps, default 190),
merges current preferences before saving, and broadcasts updates across retained
readers and windows. Native lens corner buttons and image transforms belong to
commonUtils. One held image touch plus a corner-button tap changes the saved zoom
without paging or toggling fullscreen.

## Collection and reader workflows

`collection/` owns portable bounded scans, per-comic preflight/publication and
suggestions. `collection/metadata.py` supplies bounded ComicInfo snapshots for
both Comics batch workflows and the mixed Books catalogue; comic-only consumers
do not load Books. `collection/pages.py` preserves the mobile decoder format-acceptance
policy without importing a native toolkit. `mobile/collection/` owns imported
batch forms and a composed `ComicBatchController` for local/private folder forms.
Its declared host services supply providers, navigation and credential lifetimes;
its batch plans, cancellation and retained views are controller-owned. Legacy
mobile collection/index imports remain compatibility entries. EPUB metadata
mapping is coordinated by Books, rather than dispatched by the comic domain.

`mobile/reader_controller.py` owns page/spread preparation, neighboring-file
navigation and layout-task state for imports. `mobile/provider_controller.py`
owns equivalent provider presentation state. Layout and privacy services are
injected explicitly. The host retains workspace identities, provider operations,
metadata publication, revocation and shutdown.

## Duo reading continuity

`ComicNavigation.page` is the selected logical anchor. `visible` is the composed
spread and can start before that anchor. With `anchor_right=True`, LTR spreads
use the preceding page on the left; RTL spreads use the following page on the
left. Rendering commits anchor and visible indices only after native preparation
succeeds. Ordinary platforms keep their original spread-start navigation.

The host's `ReadingPresentation` supplies local seam geometry and reserved gap.
Inactive interior divisions preserve the physical anchor when flat. The gap is
blank in the bounded composition bitmap. Wide artwork uses one region rather
than crossing the active fold. `page_region` constrains discrete pages above an
active horizontal fold without relocating continuous articles. Layout watchers distinguish relayout from explicit
navigation to preserve wide-page halves and bypass zoom deferral only when the
fold region changes. Imported progress persists the anchor using the existing
position schema; provider progress remains session-owned.

`Mobile/tests/test_comic_split.py` exercises imported/provider round trips in both
reading directions, wide-half retention, and transparent fold margins.

## Mobile page-transition publication

Reused `SpreadView` canvases separate preparation from publication.
`prepare_replacement` composes and validates the destination image without
changing the displayed bitmap and returns a publish callback. The imported
controller returns `(view, indices, publish)`; the host starts its page slide
while the old pixels are still attached, then publishes and mounts the prepared
page. Provider comics use the same preparation/publication boundary. This also
covers turns between halves of one wide page and retains native gesture owners.
Decode/composition failures keep the previously displayed pixels and navigation.
Tests capture the outgoing image during actual swipe scheduling, including manga.

## Mobile external displays

`logisticsmobile/external_display.py` owns picture-only output for UIKit external
scenes and Android `Presentation` displays. Comic presentation marks its canvases
explicitly; routes select the visible host, and page publication refreshes output.
The native viewer fits the existing decoded image against black without taking a
workspace screenshot or writing an export. Android creates a separate Drawable
around the shared bitmap so TV layout cannot change the phone canvas's bounds.

Privacy refreshes clear output synchronously when any existing screen-privacy
gate is present, including gates in other windows and retained protected views.
An unlocked gate still blocks transmission. Inactivity, route changes, suspension
and display disconnect release output image references. Android system mirroring
uses the existing fullscreen reader and FLAG_SECURE policy; presentation output
does not implement the separate Google Cast sender/receiver protocol.

`Mobile/tests/test_external_display.py` covers publication, routing, process privacy
and disconnect cleanup. Native probes verified the UIKit viewer in a second window
of the iPad simulator's application scene, and Android 36 `Presentation` on a
synthetic 1280×720 display. They exercised fitted output, image clearing and
disconnects; Android also verified fresh source checks on reconnect. A physical iPhone on iOS 26.6.2 with a wireless 3840×2160 receiver subsequently
reported a dedicated noninteractive scene, no mirrored screens, portrait phone
geometry, and an allowed comic source. The user confirmed picture-only TV output
after switching window visibility to the explicit native `setHidden:` selector;
the live window then reported visible with its decoded comic image assigned.
Native tests now assert `isHidden()` directly. Physical page-turn synchronization,
Android casting and OS snapshot timing remain outside these checks.

External-display activation is part of the iOS scene contract, not just image
painting. `Mobile.scene_build.configure` explicitly declares application, legacy
external-display and noninteractive external-display configurations using the
tracked scene delegate. iOS 26 and earlier discover those configurations on
connection. iOS 27 additionally requires `UISceneAccessory` registration on the
visible host controller; the output owner retains/unregisters it when controllers
change or the owner is disposed. Host tests cover the scene manifest and accessory
lifetime. A second window in an application scene proves rendering only and does
not prove that AirPlay will create an external scene.

The casting owner adds a noninteractive phone-only status badge above the native
window safe-area bottom. It survives immersive chrome and is removed on privacy
blanking, route exit, host changes, disconnect and disposal. Android presentation
output owns an equivalent decor overlay; its badge appears only with a published
image on a showing presentation. Neither badge becomes part of the TV image.
Mobile preferences default to two pages and no portrait wide-page splitting;
explicit saved layout/splitting choices remain available. Pair eligibility includes
square pages, with landscape and ComicInfo DoublePage pages kept single.

`SPREAD_GAP` is zero for desktop painting and bounded native composition. The
mobile compositor permits a zero-pixel gap instead of rounding it up to one;
flat fold layouts also join at the seam, while an active reserved hinge region
retains its physical clearance. Pixel tests cover the desktop center seam and
both mobile reading directions.

`ReadingPresentation.comic_boundary` injects window-local feedback into imported
and provider comic controllers. A blocked turn shows a 2.5-second, noninteractive
arrow/text hint on the internal window (Android uses a short native toast).
A repeat from the same reader in the same direction before expiry invokes the
existing adjacent-volume workflow only when a neighbor is available. A valid
page turn, route exit or privacy cover clears the hint and repeat state. Provider
neighbor candidates explicitly match the current key's parent folder. Host tests
exercise both gesture directions for comics and manga, missing neighbors, expiry,
reader changes and folder isolation; the native UIKit probe exercises hint expiry
and actual previous/next volume opening.
