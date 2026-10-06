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
- `metadata.py` contains the legacy author/series batch replacements.
- `library.py` owns single-CBZ document loading, edit validation and transactional saving.
- `ui/library.py` owns library controls and comic editing/reader services around the shared browser.
- `browser_support.py` contributes CBZ information, thumbnails, actions and activation through file-object hooks.
- `ui/file_browser.py` preserves compatibility imports for the reusable commonUtils view component.
- `pages.py` reads archive pages lazily and renders cover thumbnails without extraction.
- `reader.py` owns native reader windows; `ui/reader.py` handles page display and navigation.
- `reading.py` decides page spreads and naturally orders adjacent comic files.
- `folder_stats.py` and `ui/filesystem_model.py` preserve imports for shared filesystem totals and the object-driven Qt model.
- `ui/navigation.py` preserves imports for shared root-bounded navigation.
- `desktop_actions.py` opens the default application and reveals items through the OS file manager.
- `ui/metadata_editor.py` coordinates loading, saving and protected navigation.
- `selection.py` resolves folder/file selections and coordinates batch validation and saving.
- `edit_state.py` owns shared/mixed values and explicit pending patches without Qt dependencies.
- `ui/metadata_form.py` owns the measured tab layouts and field feedback.
- `ui/metadata_widgets.py` owns numeric controls, field creation and lossless widget/text conversion.
- `ui/value_popup.py` provides floating Lists, Check and Text entry for list-valued fields.
- `catalog.py` builds incremental library suggestions; reusable JSON parsing/atomic writing lives in `commonUtils.fileTypes.jsonType.JSONFile`.
- `library_config.py` reads configured immediate-child library names from `remoteConfig.ini`.
- `ui/operations.py` provides the shared background file-operation worker.
- `__init__.py` exposes the feature to the Logistics feature registry.

## Initialization

Comics has a hard feature dependency on `images`. Reader actions support external applications, and a native Python reader is available for CBZs.

The feature exposes `register_file_types()` so startup registers the existing
`CBZFile` globally before any feature initializer lists files. Standalone comics
library windows also register it idempotently. Registration does not parse archives.

It is discovered and loaded by the Logistics feature registry, but performs no work until comic functionality is used.

## Comics Library and Metadata Editor

Use **Open Comics Library...** in a detected Comics folder. ComicRack-configured
folders are available on macOS and Linux as well as Windows. The browser starts
collapsed and offers **List**, **Tiles**, and **Columns** views. List mode keeps
Name, Date Modified and Size columns; tiles show asynchronously loaded first-page
covers, and column mode follows folder hierarchies horizontally. Three icon buttons
switch views. Tile cells share the available width evenly, resizing covers before
adding columns. Folder-only directories use smaller square cells, and folders in
mixed directories use half-size icons by default. The tile-only **Size** menu adjusts
folder size from 25% to 100%. Layouts update immediately on resize or navigation;
a reserved scrollbar gutter keeps columns stable. Column chevrons are compact,
files end the trail, and unused space follows the current theme.
Covers and selected previews use physical pixels for the display
scale, keeping them sharp on high-DPI screens. Tile covers are
loaded for visible items and kept in a bounded 128-entry memory cache; they are
not added to the metadata JSON. Double-click folders in any mode to enter them.
Back, Forward and Up navigate previous and parent folders within the selected
library. A clickable breadcrumb path starts with the selected library root and
continues through descendant folders; selected files never appear in it. The root
stays visible on the left, and each folder can be clicked to navigate there.
Changing view modes preserves the current nested location and selection.

The reusable `commonUtils.ui.file_browser.FileBrowser` owns navigation, selection,
listing, filesystem actions and information panels. Logistics owns the library
dropdown and metadata/reader services. Every selected file has a **File Information**
tab using the File object’s generic metadata. Registered CBZFile objects add a
default-enabled **Comic Metadata** tab, thumbnails, editing actions and reader
activation. The shared browser contains no comic-specific type checks. Its **Panels**
menu can show/hide additional information tabs while retaining generic information.
Panel fields use compact aligned labels and selectable wrapped values. Folder
previews use the same system icon as the listing and a smaller preview area.

Selecting a single CBZ shows its first-page thumbnail and key fields (Series,
Author, Volume, Issue, count, title, publisher, year and description) in the adjacent
panel. The panel remains visible for empty and multiple selections. Selecting a
folder shows its path, modification time, recursive file size, and comic/file/folder
counts. Folder totals also appear in the Size column and are calculated in a
cancellable background scan without opening archives. Symbolic links and unreadable
items are excluded and reported; these totals stay in memory, outside the suggestion
JSON. Refresh updates totals, suggestions and selected-comic previews. File menus
include **Open in Default App** and an OS-specific **Reveal** action; folder menus
start with Reveal and omit Open in Default App. **Edit Metadata** is contributed
for CBZ files and folders. Linux reveal uses the standard file-manager service when
available, with a containing-folder fallback.

At the collection root, configure the libraries shown in the browser:

```ini
[LogisticsComics]
libraries = Artbooks,Comics,Comics [Marvel],Mangas,Manhwa
```

The Library dropdown preserves this order and shows the selected folder's
contents in the existing Name/Date Modified/Size tree. Missing folders are disabled;
empty or invalid settings show a message. Without this setting, the browser keeps
whole-root browsing for existing collections. This section alone enables the
Comics library folder action. Switching libraries clears the preview and collapses
the tree; existing metadata dialogs remain associated with their original files.
The suggestion cache stays at the original collection root.

Double-click a CBZ to open a native PySide reader window. Pages are naturally
sorted and read on demand without extraction or modification; image decoding runs
in a background worker. PNG, JPEG, WebP, GIF, BMP and TIFF pages are supported.
Automatic mode shows two portrait pages when both fit at full canvas height;
otherwise it shows one. Landscape pages and pages marked `DoublePage` remain
single. **View** also offers explicit Single Page and Two Pages modes. A spread
uses the same display height for both pages and reverses its visual order for
right-to-left reading: page 3 appears left of page 2. The footer shows the visible
page numbers, total and percentage, such as `2 & 3 / 182`.

Previous/Next page controls sit together at the lower left. Left/Right arrows
follow `Manga=YesAndRightToLeft`; absent/other values default to left-to-right.
For right-to-left comics the slider starts at the right end and moves left as pages
advance; the Next control is left of Previous. Up/Down navigate sequentially;
Home/End jump to first/last page. Navigation advances past the displayed spread,
and these shortcuts work immediately with focus on any reader control, without
a preliminary click on the slider. Metadata dialogs and menus retain their own
keyboard handling. Holding a key does not
trigger repeated navigation.

Separate Previous/Next File buttons are grouped above the canvas. They use naturally
sorted CBZ files in the same folder, excluding symbolic links, and disable when no
adjacent file is available. Next File starts at the first page; Previous File opens
the final page. At either reading boundary, two presses in the same direction within
0.4 seconds open the adjacent comic. A single boundary press shows a brief hint;
there is no wraparound. A file that cannot open leaves the current comic available.

The **File** menu provides Open Comic, adjacent-file navigation and Close.
**Edit > Edit Metadata…** opens the existing metadata dialog for the current comic.
Saving there refreshes the reader's archive snapshot and reading direction while
preserving its page position, and refreshes an associated library's preview and
suggestions. External archive changes still require reopening the reader.
Full Screen/F11 toggles full-screen display; Escape returns to the normal window.
The current page or spread stays visible while its replacement decodes. Images
and page labels switch together after a successful load; failures keep the current
image visible and report the error in the status bar. Initial opening alone uses a
loading placeholder. Rapid navigation loads only the latest queued page, and closing during a load
safely waits for that worker. Reopening an unchanged comic raises its existing
reader; reader windows are independent of the library window. Progress is displayed
for the current session and is not persisted.

The independent dialog provides **Details** and **Plot & Notes** layouts. The reference images measure 789 x 673/677 pixels including their title
bars. The default client area is 789 x 635 logical pixels, with 22-pixel inputs,
105 x 28-pixel action buttons, and column proportions of 267:74:74:74:184.
Volume, counts and dates use blank-capable integer spin controls; invalid
non-numeric typing is rejected immediately. Number and AlternateNumber provide
numeric arrows while still accepting suffixes/fractions as the schema requires.
Absent fields and untouched legacy strings/sentinels retain their original XML. The latter contains Summary, Notes, and Review sub-tabs. **Apply** saves
without closing, **OK** saves and closes, and **Cancel** immediately discards pending edits and closes without a prompt.
Apply and OK do not ask for confirmation; already applied changes remain saved.
Previous/Next navigate the CBZ siblings currently loaded in the browser, with the
same save/discard/cancel protection. Disk operations run in background threads;
windows cannot close while their operation is active.

Bulk editing supports extended selection of CBZ files, folders or both. Folder
contents are included recursively and overlapping selections are deduplicated.
The editor works on the resolved file list loaded at opening time; files added later
are included when the editor is reopened. Symbolic links are excluded from folder scans;
explicit link selections and hard-linked archives are refused before editing. Shared values
use the normal OS palette; differing values appear as muted “Multiple values —
unchanged” placeholders. Editing any field restores normal text and marks its
caption with `*`; the adjacent revert arrow restores its original value(s).
Only explicit pending fields are applied. The × control explicitly clears a mixed
field even when its display is already blank. Field tooltips show samples of the
original differing values. Previous/Next
are disabled for batches. Bulk preflight and archive work run off the UI thread.

Characters displays one name per line in its large text box and accepts pasted
comma-separated names. Explicit edits save comma-separated XML; opening or
reverting the field preserves the original XML spelling.

List-valued fields have a diamond button that opens a floating helper. **Lists**
adds/removes selected suggestions, **Check** toggles values, and **Text** accepts
one value per line or comma-separated text. A filter and new-value entry support
large suggestion lists and custom values. Switching modes or opening/closing the
helper leaves untouched XML unchanged; actual edits update the pending field and
its `*` marker. Clicking outside closes the popup. A mixed field starts with no
selected values; choosing values explicitly replaces the field for all selected
comics. Per-field revert still restores individual original values.

Library suggestions are indexed in the background at browser opening and after
metadata saves. The root contains `LogisticsComicsData/metadata.json`, with unique nonempty suggestions stored once per field. Suggestion whitespace is
trimmed and collapsed to single spaces, including line breaks in dropdown values.
Existing cached suggestions are normalized automatically without changing XML;
untouched source values retain their exact contents. Relative file paths map
to compact `[modification_time_ns, size, suggestion_references]` records, allowing
changed/deleted files to remove obsolete suggestions without reparsing unchanged
archives. Only list fields and Publisher, Imprint and Format are indexed; Series,
titles, plot text, empty fields and metadata hashes are excluded. Existing caches
migrate automatically on opening without rereading unchanged archives. New or
changed archives are read again; removed files and values disappear. Image
payloads are never read for indexing. The cache is disposable: invalid records
are rebuilt and write failures leave session suggestions usable.
Errors are shown in the browser status tooltip; unreadable archives are skipped
and retried on the next refresh. Folder scans exclude symbolic links and data
folders. Suggestions cover list-valued fields and Publisher, Imprint and Format
dropdowns, while custom values remain editable. Suggestions updating in the
background never overwrite pending edits.

All documents are validated and checked for external changes before the first
write. Each CBZ is replaced independently after verification; the batch is not a
single filesystem transaction. A later I/O failure reports exact file paths and
keeps pending edits, while successful files retain their updated in-memory state.
Retrying skips no-op edits on files that already succeeded. After a partial save,
field baselines are refreshed from the successful and failed documents so Revert
accurately reflects their current, potentially mixed values.

Field mappings follow the [Anansi ComicInfo documentation](https://anansi-project.github.io/docs/comicinfo/documentation)
and [v2.0 schema](https://github.com/anansi-project/comicinfo/blob/main/schema/v2.0/ComicInfo.xsd),
with Tags and Translator from the [v2.1 draft](https://anansi-project.github.io/docs/comicinfo/schemas/v2.1):

- Number and AlternateNumber are strings; fractional and suffixed issues are accepted.
- Count, Volume, AlternateCount, Year, Month and Day are integers. Blank removes a
  field; `-1` is the legacy unknown sentinel. Month and Day reject values above
  12 and 31 respectively. Existing legacy values remain untouched unless edited.
- Manga writes Unknown/No/Yes/YesAndRightToLeft, and BlackAndWhite writes
  Unknown/No/Yes. AgeRating offers the schema choices. An absent value remains
  absent unless changed. Unknown existing enum values are displayed and retained.
- Language choices display names but write codes such as `en` or `fr`. Custom
  tags such as `zh-Hant` remain supported.
- Creator, Genre, Tags, Characters, Teams and Locations values retain comma-separated
  text. Web can hold multiple space-separated URLs. No filename inference or
  automatic splitting/reformatting occurs.
- Series complete and Proposed Values occupy their screenshot positions but are
  disabled. These are [ComicRack library fields](https://github.com/maforget/ComicRackCE/blob/master/ComicRack.Engine/ComicBook.cs),
  not standard ComicInfo fields. The editor does not invent XML tags for them or
  change a ComicRack database. Existing extensions and ComicBook.xml are retained.

Only changed visible fields are patched. Fields omitted from the editor (including
GTIN, StoryArcNumber and CommunityRating), arbitrary extension elements/attributes,
namespace declarations, comments, processing instructions and Pages survive.
Existing XML formatting may change on a real edit; no-op saves retain the original
archive bytes. Emptying a visible field intentionally removes that field. New
known fields are inserted in schema order without reordering existing nodes.

`commonUtils.fileTypes.xmlType.XMLFile` now provides reusable `from_bytes`,
`read_xml`, `xml_root`, `get_text`, `set_text`, and `to_bytes` methods. Its DOM keeps
the complete document, including nodes before/after the root and unused namespace
declarations. Text methods address direct children in the root namespace and
reject ambiguous duplicates/complex fields. Tree editing is independent of
`line_lst` and inherited text-file operations. `ComicInfoXML` adds field mappings,
type checks and properties such as `writer`, `series`, and `language_iso`.
The compressor's `read_lines` and `update_pages_in_line_lst` are unchanged.

The editor validates metadata before staging, checks original file identity and
modification timestamps, verifies all output member CRCs, retains permissions,
and atomically replaces the CBZ. Failed saves retain edits so they can be reviewed;
external file changes require closing and reopening the editor before retrying.
ZIP container bytes/compression may change; decompressed image bytes do not.

## Safety Notes

Several Comics operations modify or replace files.

CBR to CBZ conversion deletes the original CBR only after the CBZ has been built and verified. Existing CBZ destinations are refused. RAR extraction uses patool's platform-specific extractor discovery and requires an installed compatible external extractor.
Legacy batch ComicInfo operations unpack and rebuild CBZ archives. The library editor streams ZIP members into a verified replacement without extracting or re-encoding images.
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

EPUB support is not currently implemented in this feature.

Image utilities remain separate because they are also used outside the Comics feature.
