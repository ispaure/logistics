# Comics Feature

Comics owns CBZ reading, metadata editing, compression/encryption, CBR conversion
and library integration. It requires the Images feature. See the
[user guide](user_docs/index.md) for controls and configuration, the
[compression contract](COMPRESSION.md) for output rules and ComicRack compatibility,
and [file browser development](../FILE_BROWSER.md) for panels, context menus and
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

The `ui/file_browser.py`, `ui/filesystem_model.py`, `ui/navigation.py` and
`folder_stats.py` compatibility imports delegate to commonUtils. Extend the
shared browser through declarations rather than adding Comics checks to it.
Registration is idempotent and does not parse archives; UI imports remain lazy.

## Browser and library boundaries

The general browser and comic library consume the same declaration. Only the
library adds tabs and automatic collection-wide suggestion indexing; it supplies
its existing controller to coordinate catalog refresh and safe closing. The
controller owns readers, editors and jobs for its window. Open readers can outlive
the library; closing a reader raises its originating browser if still visible.
Shared navigation, generic panels, selection filtering and feature toggles are
covered by the [central browser guide](../FILE_BROWSER.md).

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
real edit. Use [XMLFile](../../commonUtils/XML.md) for generic XML mechanics;
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
[compatibility policy and evidence](COMPRESSION.md#comicrack-compatibility-rebuilding-page-records)
must be retained when modifying the parser.

## Reader and catalog contracts

Readers sort pages and sibling comics naturally and load without extraction.
Qt decoding falls back to Pillow; display transforms must not modify archive bytes.
Spread selection respects landscape/DoublePage pages and manga direction.
Only the latest queued page load is displayed, and failed loads retain the current
image with an error. Metadata saves refresh the archive snapshot and direction
while retaining page position; external archive changes require reopening.
Closing during a load waits for its worker. Reading progress is session-only.

`LogisticsComicsData/metadata.json` stores normalized suggestions and compact
relative-path records using modification time/size. Index only list fields and
Publisher/Imprint/Format, never image payloads, plot text, titles or metadata hashes.
Changed/deleted records remove obsolete suggestions. Invalid caches rebuild;
write failures leave session suggestions usable. Skip linked/data folders and
retry unreadable archives on refresh. Background suggestions must not overwrite
pending edits. Encrypted metadata must never enter this persistent cache.

## Password-protected CBZs

Use `services.zip_passwords` for ancestor `[LogisticsZIP] archive_password` policy;
see [Archives](../archives/README.md#password-configuration). Ordinary CBZs remain
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
rules; see the [contract](COMPRESSION.md).

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
in [UI architecture](../UI_ARCHITECTURE.md#long-running-workflows-and-safe-closing)
and [commonUtils recipes](../../commonUtils/RECIPES.md).

CBR conversion deletes its source only after building/verifying the CBZ and refuses
existing destinations; actual extraction requires patool's external RAR extractor.
Organization copies before deleting the source. Archive rebuilds use isolated staging
and reject source changes. See [replacement rules](COMPRESSION.md#replacement-boundary)
before changing compression.

## Validation

Use the [project test commands](../../../README.md#development) and
[cross-platform checks](../../tests/PLATFORM_CHECKS.md). Comic tests cover compression,
metadata, reader/spreads/decoding, catalog, file-type integration, passwords,
encryption and asynchronous cancellation using disposable fixtures. Shared ZIP and
browser tests belong to commonUtils. The [parity report](ZIP_COMPRESSION_PARITY.md)
records decrypted full-run comparisons; ZIP container timestamps are not expected
to match. Tests do not reproduce the ComicRack crash, invoke a real RAR extractor
or replace native desktop/remote-mount validation. EPUB is not implemented.
