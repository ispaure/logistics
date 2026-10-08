# File Tools Feature

Developer notes. See the [user guide](user_docs/index.md) for controls and setup,
and [UI architecture](../UI_ARCHITECTURE.md) for shared contribution conventions.

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
