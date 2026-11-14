# Comic reader and archive development

Comics owns CBZ reading and ComicInfo metadata on desktop, Android and iOS.
Desktop also compresses, encrypts, converts and organizes comic archives.
The Books & Comics setting enables both reader engines. Comics requires
Images. See the [desktop guide](../user/user.md), [mobile guide](../user_mobile/user_mobile.md)
and [compression contract](compression.md).

## Try a compression threshold change

On desktop, right-click a disposable CBZ in **File Browser** and choose
**Compress Comics…**. `Python/features/comics/ui_contributions.py:register()`
registers the action. `ui/browser_services.py` opens `CompressCbzDialog`
with the selected targets, and the batch worker calls the CBZ encoder.

Try raising `cbz_img_min_allowed_compression_percentage` from 75 to 76 in
`Python/features/comics/cbz.py`. `CBZFile._select_compression_pages()`
uses this cutoff to choose which page bytes reach the rebuilt archive.
Update the 75% expectation in
`test_threshold_is_strict_and_override_is_preserved`, keeping the strict
comparison and the explicit always-keep case. The test creates a small
archive and controls the encoded size, so the boundary is reproducible.
From the repository root with the desktop environment installed, run:

```sh
python3 dev.py test desktop --exact-file Python/tests/comics/test_comics.py
```

Expect the file to pass. With the example edit, 75 bytes out of an original
100 keeps WebP, 76 bytes keeps the PNG, and the explicit override keeps
WebP at 76 bytes. Batch compression skips archives already marked with a
root `CompressionLog.txt`, so use a fresh copy when trying it again.

## Find the desktop edit point

| Visible action | Owner |
| --- | --- |
| Double-click a CBZ, or choose **Comic Reader** in **New / Open Document** | `ui_contributions.py` registers both routes. The browser uses its `ComicBrowserExtension` controller, and the chooser uses `services/documents/ui/readers.py`. `reader.py` and `ui/reader*.py` own the window, page workers and controls. |
| **Edit metadata…** | Books' shared browser action dispatches by format. `ui/metadata_editor.py` owns the ComicInfo edit workflow and `edit_state.py` tracks mixed values and explicit patches. |
| **Open Comics Library…** | `ui_contributions.py` exposes the Workspaces folder action when a Comics library configuration or a supported external reader is detected. `ui/library.py` adds tabs and suggestion services around the shared browser. |
| **Compress Comics…** or **Compress CBZ...** | The browser and Workspaces workflows open `ui/dialogs.py:CompressCbzDialog`. `cbz.py` owns compression. See [replacement rules](compression.md#replacement-boundary). |
| **Convert CBR to CBZ...** or **Move CBZ into Individual Folders...** | `conversion.py` and `actions.py` own the operations. Conversion requires patool's external RAR extractor, refuses an existing destination and deletes the source only after verifying the CBZ. Organization copies before deleting and stops on the first failure. |

`[LogisticsComics] libraries` lists immediate child folders in tab order.
Without that setting, the existing collection opens at the root. The
catalog belongs to the root even when a tab selects a subfolder. The library
and File Browser share the contribution and browser handlers. Independent
readers can outlive the library. See [file browser development](../../../development/architecture/file-browser.md)
for shared activation and selection behavior.

## Edit ComicInfo fields or suggestions

`comicinfo.py:ComicInfoXML` maps fields. A metadata-only patch changes
explicitly edited fields, removes fields cleared by the user and preserves
image bytes and existing page records. A no-op preserves archive bytes.
Unknown XML, namespace information, comments and processing instructions
survive edits. New known fields follow schema order. XML formatting can
change. Compression follows the separate [ComicRack page record policy](compression.md#comicrack-compatibility-rebuilding-page-records).

Number and AlternateNumber are strings, including fractions or suffixes.
Counts, volume and date components accept integers, blank removal and
the legacy `-1` sentinel. Month and Day cap at 12 and 31. Untouched
unknown enums and language tags survive. List edits use comma-separated
text. ComicRack's Series complete and Proposed Values are library fields
and remain disabled in the archive editor.
See the [Anansi ComicInfo guide](https://anansi-project.github.io/docs/comicinfo/documentation),
[v2.0 schema](https://github.com/anansi-project/comicinfo/blob/main/schema/v2.0/ComicInfo.xsd)
and [v2.1 draft](https://anansi-project.github.io/docs/comicinfo/schemas/v2.1).

`selection.py`, `library.py` and `mutations.py` resolve and preflight
the batch before the first write, including the 4 MiB ComicInfo encoded
limit after escaping. Exclude links from scans and reject explicit
symlinks and hard-linked archives. Each verified replacement is atomic.
If a later file fails, earlier saves remain. Refresh each baseline so
retry or revert uses the current state.

`catalog.py` caches normalized suggestions and compact relative-path
records under `LogisticsComicsData/metadata.json`. Persist only list
fields and Publisher, Imprint and Format. Keep protected metadata out
of this index. Refresh removes suggestions for changed or deleted
records. If cache loading fails, rebuild it. A write failure leaves
session suggestions available. Keep background refreshes from
overwriting pending edits.

## Password-protected CBZs

`services.documents.zip_passwords` owns ancestor `[LogisticsZIP]`
`archive_password` lookup. See the [Archives password policy](../../archives/development/development.md#password-policy-and-the-two-creation-flows).
Readers and single-file editors prompt if needed and cache successful
unlocks in memory until the archive or configuration changes. Background
previews show a placeholder for locked files. Compression uses only the
configured password and reports failures per comic.

A rewrite authenticates all members and uses the successful password with
AES-256, upgrading legacy ZipCrypto. Mixed encrypted/plain entries can
be read. Rewriting requires a uniform encryption policy and one valid
password for the archive. ZIP member names stay visible. Compression uses
a disposable plaintext workspace with ordinary file cleanup.

The browser's **Encrypt unencrypted comics…** action requires ancestor
configuration for the accepted selection. The dialog recursively
deduplicates without following symlinks and refuses execution if a
plain comic lacks a configured password. Direct API callers can supply
a fallback password. Encryption streams unchanged content, names, order,
empty folders and comments into a verified AES-256 CBZ. It skips
already-encrypted inputs and rejects hard links.

## Change page order or reading position

`pages.py` reads page bytes without extraction. Readers use natural page
order with decimal runs sorted numerically. Superscript and circled
numerals sort as text. `reading.py` owns spread eligibility and manga
direction. Desktop decoding uses Qt with a Pillow fallback. Mobile
`collection/pages.py` filters resource forks and applies the native
PNG/JPEG/WebP policy. An unsupported provider page fails explicitly.
`mobile/decoding.py` owns bounded native decoding, including ImageIO
sampling. The desktop and mobile spreads use zero artificial gap.
An active physical hinge can reserve space.

Desktop `reading_state.py` records the last successfully displayed
page, debounces writes and flushes on file switches and close.
Restore by member name before clamping the zero-based index. Bounded
128 KiB state includes the page total for the thumbnail badge.
The thumbnail worker seeds names for legacy lookups so painting can
use one state snapshot without opening the archive. Oversized or
malformed records leave the existing file intact. The shared
`Reader.remember_position_bool` preference controls retention. Failed
decodes retain the visible page. Reopen an archive that changed
externally. Closing waits for the worker to retire.

## Change mobile layout or volume navigation

`mobile/navigation.py:ComicNavigation` prepares the requested index,
spread and half. The imported and provider controllers commit these
after the prepared view publishes. `mobile/presentation.py` stages
pixels before replacing the displayed bitmap so the outgoing page can
animate and decode errors retain the current image and anchor. Follow
the [host publication contract](../../../development/architecture/mobile-runtime.md#reader-publication-boundary).

`comic_split_wide` defaults to true, including for older preferences.
A landscape source in a portrait viewport can be split in any page
layout. Square viewports and landscape windows retain the full page.
`mobile/composite.py` uses normalized horizontal bounds `[0, .54]`
and `[.46, 1]`. The halves overlap by 8% and traversal respects manga
direction. Imported checkpoints can store half 0 or 1. Older records
start at the first half. Provider half state stays with the session.
Previous-spread probing may cache dimensions without committing a
new half or view.

The same compositor creates one RAM-only native bitmap per spread,
limited to 16 million pixels and 8192 pixels per side. UIKit uses scale
1. One canvas owns zoom, pan and gestures. Viewport reloads defer
while zoomed unless a fold region changes. An active vertical hinge
separates paired pages and can leave a lone page across the whole canvas.
A horizontal hinge constrains the page region above it. Preserve the
selected logical page when recomposing a spread around a fold.

Run this host check for split eligibility, traversal, failed composition,
resume and Duo relayout. It uses synthetic pages and the Toga dummy
backend. Use native checks for actual gestures and rendered geometry.

```sh
python3 dev.py test mobile --exact-file mobile_build/tests/reading/test_comic_split.py
```

`mobile/reader_controller.py` and `mobile/provider_controller.py` own
imported and provider navigation respectively. Local, LocalCrypt and
cloud readers list neighboring CBZ or ZIP files in the current folder
by case-insensitive filename. Pass the full relative path to
`PrivateReader`, including nested folders. Legacy imports resolve
siblings from their original folder. A successful switch retires
the outgoing session after publishing the neighbor. Failure keeps
the current reader and page. Desktop provider-backed comics have
no sibling navigation.

The host's `mobile/comic_feedback.py` owns the 2.5-second repeat window.
Only an available offered neighbor arms the next swipe. A route or
privacy change clears it. `mobile/comic_guidance.py` presents a native,
noninteractive cue respecting reduced motion and E Ink. Keep it
outside the canvas and external image. The managed `comic-guidance`
probe supports scoped native checks for cues, neighbors, lifecycle
and folds. `test_comic_file_navigation.py` exercises corrupt-target
recovery and LocalCrypt/cloud folder traversal using fixture providers.

## Change mobile metadata or external output

`collection/` owns bounded selection and metadata plans.
`mobile/collection/` owns batch forms and controller state.
`mobile/private_batch.py` caps metadata-only snapshots at 8 MiB and
keeps retry baselines in memory. The host provides credential checks
and verified publication. Concealment, memory release and revocation
retire the plan and wipe the form. The managed-copy recovery contract
lives under [imported metadata publication](../../books/development/development.md#imported-metadata-publication).
Add new portable/mobile imports to `Python/features/comics/mobile_sources.json`.

`Python/mobile/external_display.py` publishes the existing decoded image
to iOS scenes or Android Presentation displays. Screen-privacy gates
across the process clear output, even when unlocked. A phone-only
status badge follows the published image and disappears on blanking or
retirement. While sharing, temporarily choose paired pages and whole
wide pages. Disconnect restores the saved layout and half. Preserve
the preference file across those transitions.

iOS external output depends on tracked scene configuration.
iOS 27 also requires `UISceneAccessory` registration on the visible
host controller. Changing owners must unregister the previous accessory.
Use the explicit native `setHidden:` selector when showing the external
window. `test_external_display.py` and `test_comic_sharing.py` cover
routing, privacy and temporary layout. Simulator output verifies rendering
through the simulated surface. A wireless receiver check on iOS 26.6.2
confirmed picture-only output via a noninteractive external scene after
the selector change. Page-turn synchronization still needs a receiver
check. Android uses Presentation and implements no Google Cast sender.
