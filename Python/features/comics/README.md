# Comics Feature

Provides comic-related integration for Logistics.

## Responsibilities

- Detect and configure comic-reader integrations.
- Work with CBZ and CBR comic archives.
- Edit ComicInfo.xml metadata.
- Support comic-specific conversion, compression, and organization workflows.
- Keep comic-specific behavior isolated from Logistics core and UI code.

## Structure

- `actions.py` contains user-facing comic actions such as reader launching and CBZ organization.
- `detection.py` contains ComicRack and YACReader detection/configuration helpers.
- `cbz.py` orchestrates CBZ compression and keeps the public entry points and settings.
- `sanitization.py` contains archive cleanup, wrapper flattening, and page-padding rules.
- `comicinfo.py` parses ComicInfo XML, rebuilds page records, and serializes consistent formatting while preserving other metadata.
- `compression_stats.py` contains compression statistics and text logging.
- `archive_io.py` builds, verifies, and commits replacement archives.
- `conversion.py` contains CBR to CBZ conversion behavior.
- `metadata.py` contains ComicInfo.xml metadata editing behavior.
- `__init__.py` exposes the feature to the Logistics feature registry.

## Initialization

This feature does not require startup initialization.

It is discovered and loaded by the Logistics feature registry, but performs no work until comic functionality is used.

## Safety Notes

Several Comics operations modify or replace files.

CBR to CBZ conversion deletes the original CBR only after the CBZ has been built and verified. Existing CBZ destinations are refused. RAR extraction uses patool's platform-specific extractor discovery and requires an installed compatible external extractor.
ComicInfo metadata operations unpack and rebuild CBZ archives.
CBZ organization copies each archive into a new folder and then deletes the original after the copy succeeds.
CBZ compression and metadata edits use isolated temporary workspaces. A replacement ZIP is staged beside the destination, checked for the exact expected files, fully CRC-checked, and compared with the staged source files before atomic replacement. Existing file permission bits are retained. Source files changed during processing are refused. Other adjacent `.zip` files are untouched.

Image encoding uses shared `ImageFile.compress()` dot-file staging within the compressed-images directory: `.01.webp` is verified and renamed to `01.webp` before the normal retention decision. Dot prefixes never enter final page names or ComicInfo records.

Copy, image encoding, metadata, archive-building, verification, and replacement failures retain the original CBZ. Empty, unsafe, duplicate, and colliding archive/page paths are rejected. A nested ComicInfo.xml that cannot be flattened under the established rules is rejected rather than silently discarded. Batch compression continues after individual archive failures and returns aggregate statistics; workflow dialogs report partial failures.

These operations should be tested against disposable data when behavioral changes are made.

## Compression Contract

The established output rules are preserved:

- WebP quality is 60 for color and 35 for grayscale, with method 6, the shared color heuristic (with the approved uniform-color fix), EXIF orientation handling, RGB conversion, and Lanczos resizing from the shared image helper.
- Height is capped at 2400; no longest-edge cap is enabled. Images are never upscaled.
- Keep WebP only when its byte size is **strictly less than 75%** of the original. Exactly 75% keeps the original. The explicit override always keeps WebP.
- `preserve_animated_and_multipage_originals=True` skips encoding images containing more than one frame/page and retains their original bytes. Static pages still follow the normal size rule. Preservation is enabled by default in the dialog and for normal API compression. An omitted API preservation argument allows an explicit always-keep request to convert the first frame; an explicit false argument also permits first-frame conversion. Explicitly enabling preservation together with `always_keep_compressed=True` logs `Severity.ERROR` and rejects the operation before processing; batch calls return `None`, single-file calls return `False`. The dialog displays the same incompatibility and remains open.
- Retained original pages are copied byte for byte. Files are visited in the existing lexicographic directory order, not a newly introduced natural sort.
- Numeric padding is triggered by single-digit page names. The existing count thresholds remain: fewer than 90 files uses two digits, fewer than 950 uses three, otherwise five. The count includes recognized metadata files, as before. Mixed/non-numeric names are refused when repair is needed.
- Delete `__MACOSX`, `.DS_Store`, `Thumbs.db`, and `Thumbs1.db`. Keep the existing removal list for unwanted text/web/sidecar extensions; reject other unsupported files.
- Flatten one wrapper folder, including the existing special case of one empty wrapper containing one leaf folder. Multiple leaf folders remain separate; unsupported deeper layouts and mixed root pages/subfolders are refused.
- Missing ComicInfo.xml is allowed. When present, parse XML and update PageCount and rebuild Pages from the chosen images, with page zero marked FrontCover. Compact XML, different indentation, empty page sections, and missing PageCount/Pages elements are supported. Other metadata, namespaced elements/attributes, and comments/processing instructions inside the root are preserved. Output uses UTF-8 and two-space indentation; namespace prefixes may change. Malformed XML, incorrect roots, and duplicate page sections/counts fail safely before archive replacement.
- Write CompressionLog.txt and use its presence at the archive root as the batch skip marker. Single-file compression still permits explicit recompression.

The uniform-color detection bug was subsequently fixed with approval: the shared detector checks mean chroma distance from neutral as well as the existing variation test, with the same tolerance. Uniform colors and sufficiently tinted pages now receive color quality 60. This intentionally changes their compressed bytes and can change whether WebP meets the retention threshold; marked archives remain skipped.

## Output-Sensitive Findings Left Unchanged

These need a deliberate policy decision because fixing them changes page bytes or metadata:

- When preservation is disabled, GIF/TIFF/animated WebP/APNG compression saves only the selected initial frame. With preservation enabled (the normal default), multiframe files are kept unchanged. Comics explicitly uses `preserve_alpha=False` when encoding pages, converting alpha/palette images to RGB without compositing onto a background; retained originals keep any alpha. Standalone Images compression preserves WebP alpha by default. The shared encoder now preserves ICC/EXIF metadata as well, normalizing applied orientation and dimensions and converting non-RGB profiles to sRGB for WebP.
- Rebuilding Pages discards old per-page attributes such as bookmarks, page types other than the synthesized FrontCover, and DoublePage flags. This is the existing rule, not a new XML merge policy.
- Grayscale/color detection runs on the source before resizing. Recompression markers do not encode the settings, so changed settings do not cause marked archives to be recompressed automatically.
- Statistics labeled Archive measure the sum of image payloads, excluding ZIP overhead, XML, and logs. The forced-compression option can increase the resulting archive size.

Batch dialogs still execute synchronously on the UI thread, so large runs can make the window unresponsive. Moving them to background workers with cancellation is a separate UI improvement; it was not attempted without a working Qt runtime for validation.

## Verification

Run from the repository root:

```sh
PYTHONPATH=Python python3 -m unittest discover -s Python/tests -v
```

The regression suite uses disposable fixtures and simulated failures. It covers exact retention boundaries, unchanged encoder settings, forced compression, original page preservation, resize/page XML results, padding cutoffs, cleanup/flattening, concurrency isolation, collisions, invalid archives/XML, failed copies/encoding/builds/replacement, existing destinations, metadata escaping, and conversion commit ordering.

A comparison before the structural XML update covered six fixture/override combinations against the original compressor: page bytes, member names, ComicInfo XML, and logs matched exactly except timestamps. Only the original multiline log export incompatibility was patched to make that comparison runnable. ComicInfo formatting is now normalized, while its other metadata values and the established page attribute policy are preserved. ZIP container bytes/timestamps are not claimed to be identical. Real RAR extraction and desktop dialogs require separate platform validation; conversion tests simulate the external extractor.

## Future Work

`logisticsUtils/epubUtils.py` is intentionally retained for future EPUB development.

Image utilities remain separate because they are also used outside the Comics feature.
