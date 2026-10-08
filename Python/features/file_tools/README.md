# File Tools Feature

Developer notes. See the [user guide](user_docs/index.md) for controls and setup,
and [UI architecture](../UI_ARCHITECTURE.md) for shared contribution conventions.

Provides small filesystem maintenance and diagnostic tools for Logistics.

## Responsibilities

- Find files whose paths contain configured problematic Unicode characters.
- Delete Python bytecode (`.pyc`) files from a selected directory.

## Structure

- `filesystem.py` contains filesystem diagnostics and maintenance operations.

## Weird Character Detection

The weird-character diagnostic preserves the character set used by the original Logistics tool.

Some entries appear visually identical because they use different Unicode representations, such as precomposed and combining-character forms.

The operation is read-only.

## PYC Cleanup

The PYC cleanup operation deletes `.pyc` files from the selected directory.

When recursive mode is enabled, matching files in subdirectories are also deleted.

This operation should be tested against disposable or regenerable data when its behavior is changed.
