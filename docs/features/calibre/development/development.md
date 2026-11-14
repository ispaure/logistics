# Calibre library and export development

Calibre adds desktop controls to open a Calibre library and mirror its books to
a dedicated export folder. For setup and controls, see the [Calibre user guide](../user/user.md).

## Try an export filename change

On desktop, select a local folder in **Workspaces** with a Calibre library as an
immediate child. In the **Calibre** section, select the library, choose
**Export books…**, select an empty disposable destination and click **Review
export**. For an isolated naming experiment, a temporary library can use an
empty `metadata.db` marker, an author folder and a book folder with a fixture
`.epub` and `metadata.opf`. Planning reads the files and sidecar metadata.
It needs no Calibre process or device.

`Python/features/calibre/ui_contributions.py:get_contributions()` registers
the folder widget. `ui/folder_widget.py:CalibreFolderWidget._export()` opens
`ui/export_dialog.py:ExportDialog`, which reviews the plan from
`export.py:build_export_plan()`. Try changing “Vol” to “Volume” in
`Python/features/calibre/metadata.py:get_metadata_book_name()` and adjust the
expected generated name in `test_metadata_series_and_existing_volume_are_not_duplicated`.
Keep the rule that an existing series prefix or volume label in the title
counts toward the name.

From the repository root with the desktop environment installed, run:

```sh
python3 dev.py test desktop --exact-file Python/tests/calibre/test_calibre.py
```

Expect the file to pass. For example, the title `Title`, series `Series`
and index `5.00` should generate `Series - Title - Volume 5` after the edit.
A title already containing `Volume 5` still gets a single volume label.
The suite uses disposable directories and mocked launchers.

## Find libraries and launch Calibre

`detection.py` checks for `metadata.db` in immediate child folders of a
Logistics Local folder. No `[Calibre]` section in `remoteConfig.ini` is
required. `library.py:CalibreLibrary` is the operation facade and `actions.py`
connects it to the folder controls. `launching.py` passes argument lists to
the resolved program. Linux checks native Calibre and then uses `flatpak info`
to find user or system installations. Windows uses the bundled executable.
macOS can install from the bundled archive and checks installation before
launch. Platform launch behavior needs a local Calibre installation for
acceptance.

## Change export or recover from failure

A reviewed plan describes a complete one-way mirror into a dedicated folder.
Planning is read-only. It checks the library marker, nonoverlapping paths,
regular files and destination entries. It rejects links and case or
Unicode-equivalent name collisions. Missing or malformed OPF metadata
falls back to a sanitized book-folder name. Checksums identify changes
even when sizes match.

Execution verifies the directory/device identity and file signatures.
It stages and verifies all changed copies before replacing any existing
export, so allow temporary space for all staged copies. Replacements are
atomic per file. Once they succeed, execution prunes obsolete files,
including other extensions. Staging failures preserve existing exports
and skip pruning. Failure or cancellation during publication can leave a
partial mirror. A disconnected device may retain staging files until a
later export cleans up.

The dialog consumes its review when Apply starts. After failure or
cancellation, reconnect or correct the destination and review again to
plan against its current state. **Echo EPUBs to BOOX-SD** uses the same
review dialog with a prefilled path when `/Volumes/BOOX-SD` is mounted.
`ui/manage_dialog.py` retains an older confirmation workflow for its
direct callers. The focused test covers plan invalidation and recovery
using temporary folders. Exporting to mounted hardware requires platform
validation.

## Feature boundaries

Calibre is optional and desktop-only. The mobile feature registry has no
Calibre entry. Books owns EPUB parsing, reading and direct metadata editing.
Calibre export copies existing formats without conversion or database
synchronization. See the [mobile availability guide](../user_mobile/user_mobile.md)
and [feature contribution conventions](../../../development/architecture/features.md).
