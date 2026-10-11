# Rename a batch of files

Use **Bulk Rename** from the navigation rail or a File Browser selection to
transform filenames while keeping file contents. Review the new names before
applying. Opening another selection reuses the main tool and retains its rules;
check those rules before the next batch.

## Using the window

The folder tree keeps the filesystem/drive hierarchy visible as you navigate.
The current folder remains selected alongside its parent folders and siblings;
expanded branches stay open. The navigation tree includes hidden directories so
a directly opened path can always be shown; the **Hidden** file-list filter still
controls which candidates are displayed. Expand a folder to choose a deeper location. The up arrow, path field and **Browse** navigate directories. Double-click a
folder row to enter it. Filters accept filename wildcards or a Python regular
expression. Files are included by default; folders and hidden names/OS hidden attributes are opt-in.
**Subfolders** scans recursively without following directory symlinks. Depth zero
means all levels, one includes immediate child folders. **Apply filter** or
**Refresh** rescans the directory; selecting rows changes only the rename scope.
Scans report permission errors rather than silently claiming complete results.

All initially displayed candidates are selected. Ctrl/Cmd-click or Shift-click
changes the selection, and **Select all / Select none** manage it. Only selected
rows participate in the preview or rename. Fix every displayed error first;
unchanged names require no disk operation. Numbering uses natural full-path order
(`page2` before `page10`), independently of selection click order.

Rules combine in this order:

| Panel | Behavior |
| --- | --- |
| 1 · Regular expression | Python pattern/replacement with `\1` or `\g<name>` groups; optionally include the extension |
| 2 · Name | Keep, replace the entire stem with a fixed name, or remove the stem |
| 3 · Replace | Literal substring replacement, case-sensitive or insensitive, all matches or first only |
| 4 · Case | Keep, lowercase, uppercase, title case, sentence case or swap case |
| 5 · Remove | First/last characters, a range, specific characters, digits, punctuation/symbols, accents, or surrounding whitespace |
| 6 · Move / copy a part | Move or duplicate a character range to another position in the stem |
| 7 · Add | Prefix, positioned insertion and suffix |
| 8 · Date | Add modified/creation/current date with a `strftime` format, separator and day offset |
| 9 · Parent folder | Add one or more parent-folder names with a separator |
| 10 · Numbering | Prefix/suffix/positioned counter, start/step/padding, optionally restart per folder |
| 11 · Extension | Keep, lowercase, uppercase, replace or remove the final file extension |

Positions are zero-based and count Unicode characters. Insertion past the end
appends. A file's final extension is protected until the Extension step unless
regex explicitly includes it; folders treat their entire name as the stem,
including dots. Dotfiles without a suffix keep their entire name. Creation date
is offered only when the filesystem exposes birth time; it never substitutes
metadata-change time on Unix (older Windows Python versions use their creation-time
`st_ctime` field when birth time is unavailable). Date rules change names, not file timestamps.

**Save rules / Load rules** store a plain JSON preset. Loading never executes code;
invalid presets leave existing controls unchanged. **Reset rules** restores the
neutral pipeline. **Preview** reruns the live preview explicitly.

## Applying, cancelling and undo

Scanning, planning and renaming run in background workers with progress and cancellation.
Selection and rule previews update rows together without showing a progress panel
or moving the main layout. While calculating, **Preview** becomes **Cancel preview**
in the same space. Scans and rename/undo operations still show full progress.
Changing a rule supersedes an older preview; Rename stays disabled until the
current preview is ready. Python regex matching cannot be interrupted mid-match;
use sensible patterns for large lists. Cancellation is checked between items.

Each batch rechecks source identity/size/mtime and destination occupancy. Duplicate,
existing, reserved or invalid destinations block the whole batch. Case and Unicode
normalization equivalents are treated as collisions by default, even on a
case-sensitive filesystem. Names are restricted to portable Windows-compatible
basenames. Select a folder or its descendants, **not both in the same batch**.
This version renames in place: it does not copy or move files between folders,
edit attributes/timestamps, run scripts, or inspect EXIF capture dates.

Renames temporarily stage files beside their originals. This supports swaps and
case-only changes without overwriting occupied destinations. A filesystem without
the required exclusive rename support refuses the operation. Files retain their
contents and metadata; directory contents and symlink targets are not rewritten.

A failure or cancellation rolls the batch back. Rollback is never cancelled and
never overwrites externally created files. If recovery is blocked, the status
shows the current staged path and original path so data can be recovered manually;
do not delete these `.bulk-rename-*` entries. This is rollback on handled errors,
not a crash-recovery journal or a filesystem lock. A process/power failure can
leave staged paths, and external concurrent changes can block recovery.

**Undo last rename** reverses the last successful batch in this window. It refuses
when renamed items have since changed or original names have become occupied.
The receipt is in memory and is not retained after closing. Rules remain after
applying, but the tool requires a fresh preview before another rename. Closing a
busy window requests cancellation and waits for work and rollback to finish.


[Application guide](../../../../USER_GUIDE.md)

The file preview and rules share a vertical splitter. Drag its divider to give
either area more room, or toggle **Rules** to hide/show the rule controls without
resetting them. The current rules continue to apply when hidden.

**Scope…** contains file/folder, hidden-item, recursive and depth options; use
Apply filter after changing them. **Rule presets…** contains load/save/reset.
Rule cards reflow into fewer columns in narrow windows.
