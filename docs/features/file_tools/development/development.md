# File Tools Feature

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

Developer notes. See the [user guide](../user/user.md) for controls and setup,
and [UI architecture](../../../development/features.md) for shared contribution conventions.

Provides small filesystem maintenance and diagnostic tools for Logistics.

## Responsibilities

- Find files whose paths contain configured problematic Unicode characters.
- Delete Python bytecode (`.pyc`) files from a selected directory.

## Structure

- `filesystem.py` contains filesystem diagnostics and maintenance operations.
- `ui/dialogs.py` owns background scans/cleanup and persistent results tables.
- `ui_contributions.py` declares folder-only File Browser selection actions.
- `register()` supplies a unified feature declaration with no Debug actions.

## Weird Character Detection

The weird-character diagnostic preserves the character set used by the original Logistics tool.

Some entries appear visually identical because they use different Unicode representations, such as precomposed and combining-character forms.

The operation is read-only. The results window displays paths, matched character
sequences and their Unicode code points. Scanning does not follow directory links.

## PYC Cleanup

The PYC cleanup operation deletes `.pyc` files from the selected directory.

When recursive mode is enabled, matching regular files in subdirectories are also
deleted. File links are preserved and directory links are not traversed. Multiple
selected roots are deduplicated. Cleanup records per-file success/failure and
unprocessed paths on cancellation; it continues after an individual failure.

This operation should be tested against disposable or regenerable data when its behavior is changed.

## Reviewed deletion boundary

The dialog calls `scan_pyc_files` to capture a read-only candidate snapshot, then
passes that snapshot to `cleanup_pyc_files` only after confirmation (default No).
Changing roots or recursion invalidates the preview. Both scan and cleanup call
`services.folders.safety.require_safe_folder`, using `Python/maintenance.ini`.
The policy resolves paths, rejects protected roots and descendants, and rejects
recursive ancestors of protected roots. Cleanup rechecks each file's device,
inode, size, nanosecond modification time and mode, its root membership, and
whether any parent has become a symlink before unlinking it. This is a pre-delete
identity check, not a filesystem lock against concurrent changes.

The older `delete_pyc_files` helper is not the dialog's reviewed-delete entry
point; maintain the scan/confirmation/snapshot handoff when changing the UI.
The diagnostic matches configured sequences anywhere in the full path, including
parent-folder names; it is not a general Unicode validity checker or renamer.

## Platform and validation scope

Registration supplies desktop browser actions only; there is no mobile adapter
or entry in `Python/services/mobile_features.py`. See
[mobile availability](../user_mobile/user_mobile.md).

`Python/tests/files/test_file_tools.py` covers composed/combining matches, parent
paths, reviewed candidates, changed/new files, links, partial failures,
cancellation, confirmation, persistent results and feature toggling. These tests
were read during this documentation audit, not executed: runtime/Qt acceptance
remains outside the source and static checks permitted by the release quiet hold.
