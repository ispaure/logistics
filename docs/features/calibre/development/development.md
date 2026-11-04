# Calibre Feature

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

Developer notes. See the [user guide](../user/user.md) for controls and setup,
and [UI architecture](../../../development/features.md) for shared contribution conventions.

Provides Calibre integration for Logistics.

## Responsibilities

- Detect Calibre libraries contained directly within Logistics Local folders.
- Represent and operate on Calibre libraries.
- Launch libraries in Calibre.
- Export supported book formats to external reading devices.

## Structure

- `detection.py` detects Calibre libraries by looking for `metadata.db` in immediate child folders.
- `library.py` contains the `CalibreLibrary` model and Calibre-specific library operations.
- `metadata.py` reads OPF titles/series and normalizes export filenames.
- `export.py` builds a read-only export plan and stages verified copies before replacing files and pruning obsolete exports.
- `launching.py` resolves native/bundled/Flatpak executables and launches them with argument lists.
- `actions.py` exposes Calibre operations to the Logistics UI.

## Library Detection

A Logistics Local folder is considered Calibre-supported when at least one of its immediate child folders contains:

`metadata.db`

Only immediate child folders are checked. Calibre support no longer depends on a `Calibre` section in `remoteConfig.ini`.

## Notes

Calibre is an optional Logistics feature.

Book exports use a dedicated destination as a complete one-way mirror. Obsolete
files, including files with other extensions, are removed only after all changed
books have been copied successfully. Do not mix unrelated files into that folder.

Planning validates the library marker, source/destination separation, filenames,
and existing destination entries before writing. Linked library/export roots and
linked entries are rejected. Collisions, including case or Unicode-equivalent
filenames, abort the export rather than silently choosing a book. Malformed or
missing OPF metadata falls back to the sanitized book folder name.

Checksums detect changed books even when sizes match. All changed copies are
staged and verified before replacements begin; staging requires temporary space
for those copies. Each replacement is atomic, but the complete mirror is not one
filesystem transaction. A replacement or deletion failure can leave a partial
update; failed copy staging preserves existing exports and skips pruning. Changes
to planned source/destination files are checked before writes and deletions.
The destination's directory/device identity is also checked during execution;
removing or replacing it stops the export. Staging files on a disconnected device
may remain until a later export can clean them.

BOOX export requires `/Volumes/BOOX-SD` to be mounted and reports failures in the
folder UI. Linux launching prefers native Calibre, then checks the Flatpak using
`flatpak info`, covering user and system installations. Windows uses the bundled
executable; macOS retains the existing bundled-archive installation fallback.

`Python/tests/calibre/test_calibre.py` uses disposable libraries/device folders and mocked
launchers. It covers naming, collisions, links, copy failures, changed files,
disconnected storage and Linux launcher selection. Actual device exports and
desktop launching still require platform validation.

`ui_contributions.py` registers the desktop `FolderFeatureContribution`; it
requires a local entry and lazily constructs `ui/folder_widget.py`. That widget
owns the library selector and reviewed export route through `ui/export_dialog.py`.
The BOOX button in this route prefills the destination after checking the mount.
`ui/manage_dialog.py` retains an older confirmation-based BOOX workflow; do not
confuse that direct facade call with the registered folder widget's review dialog.
There is no root `folder_widget.py` compatibility module.

## Platform and ownership boundaries

The native mobile catalogue in `Python/services/mobile_features.py` has no
Calibre entry, and this package has no mobile source manifest or presentation.
EPUB parsing, reading and direct EPUB metadata editing belong to Books; Calibre
export does not implement conversion or mobile database synchronization. See
[mobile availability](../user_mobile/user_mobile.md). Shared filesystem and UI
mechanisms remain in commonUtils; this guide documents the Logistics adapter.

## Static audit scope

On November 4, 2026, documentation was checked against registration, discovery,
launching, export planning/execution, both UI routes and the test source.
`Python/tests/calibre/test_calibre.py` also covers cancellation before copying,
truncated staging, destination replacement and argument-safe launching. These
are test contracts, not newly executed results. No Qt launch, device export,
build or runtime test was performed during the release quiet hold.
