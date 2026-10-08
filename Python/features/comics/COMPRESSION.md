# Comic compression contract

Developer reference for changes to `cbz.py`, `sanitization.py`, `comicinfo.py`
and `archive_io.py`. Start with the [feature overview](README.md); controls and
options are in the [user guide](user_docs/index.md). These rules are covered by
`test_comics.py`, the image tests, `test_async_comic_operations.py` and
`test_encrypted_comics.py`. The [historical parity report](ZIP_COMPRESSION_PARITY.md)
records comparisons against the pre-password implementation.

## Output rules

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

### ComicRack compatibility: rebuilding page records

**Do not merge old page records when compression changes page files.** Discard
all children of `Pages`, including old page attributes, per-page extension data,
comments and processing instructions. Generate fresh indices, `ImageSize` byte
counts, widths and heights from the final selected images; only page zero receives
the synthesized `FrontCover` type. `PageCount` must match those images.

Evidence for this policy:

- In the chat **Switch folder sources to tabs**, October 2, 2026 at 12:19 EDT,
  the maintainer explicitly said: “ok yeah it's ok to not preserve the attributes,
  id rather have it that way.” This followed a discussion of losing `Bookmark`,
  `DoublePage` and existing `Type` attributes during rebuilding.
- The implementation before commit
  [`8537151`](https://github.com/ispaure/logistics/commit/85371518f610d3d82d1d4eaab2038ee827ddbdab)
  skipped the old `Pages` contents and generated new records. Structural parsing
  in [`8cb4676`](https://github.com/ispaure/logistics/commit/8cb46761cf902cc732ab8376440833abfc559b79)
  retained that policy.
- On October 8, 2026, in **Map RemoteCredentials and Software**, the maintainer
  explained that keeping stale information after modifying page files causes
  ComicRack to crash when opening the comic. This is a maintainer-reported
  compatibility issue; our tests do not run ComicRack or reproduce its crash.

This does not require deleting book-level metadata or comments outside `Pages`.
Metadata-only edits keep image bytes unchanged and preserve page records. Image
ICC/EXIF handling is separate: the October 2 instruction at 12:56 EDT explicitly
requested preserving color profiles and EXIF in the shared image compressor.
The regression suite checks that obsolete page records and their contents are
discarded and that generated values match the actual output images.

## Deliberate limitations

These need a deliberate policy decision because fixing them changes page bytes or metadata:

- When preservation is disabled, GIF/TIFF/animated WebP/APNG compression saves only the selected initial frame. With preservation enabled (the normal default), multiframe files are kept unchanged. Comics explicitly uses `preserve_alpha=False` when encoding pages, converting alpha/palette images to RGB without compositing onto a background; retained originals keep any alpha. Standalone Images compression preserves WebP alpha by default. The shared encoder now preserves ICC/EXIF metadata as well, normalizing applied orientation and dimensions and converting non-RGB profiles to sRGB for WebP.
- Rebuilding Pages discards old per-page attributes such as bookmarks, page types other than the synthesized FrontCover, and DoublePage flags. This is the existing rule, not a new XML merge policy.
- Grayscale/color detection runs on the source before resizing. Recompression markers do not encode the settings, so changed settings do not cause marked archives to be recompressed automatically.
- Statistics labeled Archive measure the sum of image payloads, excluding ZIP overhead, XML, and logs. The forced-compression option can increase the resulting archive size.

Compression, CBR conversion, author/series batch edits and folder organization
run in background workers. Forms capture their inputs before starting and disable
changes while processing; progress and errors arrive on the GUI thread.
**Cancel after current comic**, Escape and closing the dialog request cooperative
cancellation and wait for the current comic to finish. Compression never passes
that cancellation into its ZIP rebuild: the current archive must finish encoding,
verification and atomic replacement (or fail with its original intact). Remaining
comics are untouched. Summaries distinguish cancellation, failures and unprocessed
files, and per-file failures remain visible. A failed comic does not stop later
compression candidates unless cancellation was requested. Folder organization
retains its existing stop-on-first-error policy.

## Replacement boundary

Use an isolated workspace and stage the replacement beside the destination.
Verify the expected member set, CRCs and staged payloads, retain permission bits,
and reject source changes before atomic replacement. Copy, encoding, XML, build,
verification or replacement failures must preserve the original CBZ. Reject empty,
unsafe, duplicate or colliding paths and unsupported nested layouts; do not silently
drop a nested ComicInfo.xml that cannot be flattened.

Encryption must leave the extraction, sanitization, image retention, XML and log
rules unchanged. Compare decrypted manifests, with log time frozen, rather than
ZIP container bytes or timestamps. Separate ZIP creation may cancel between
chunks; comic compression must finish its current archive before batch cancellation.
