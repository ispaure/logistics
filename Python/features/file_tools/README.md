# File Tools Feature

Provides small filesystem maintenance and diagnostic tools for Logistics.

## Responsibilities

- Find files whose paths contain configured problematic Unicode characters.
- Delete Python bytecode (`.pyc`) files from a selected directory.
- Keep filesystem operations out of debug popup UI code.

## Structure

- `filesystem.py` contains filesystem diagnostics and maintenance operations.
- `__init__.py` exposes the feature to the Logistics feature registry.

## Weird Character Detection

The weird-character diagnostic preserves the character set used by the original Logistics tool.

Some entries appear visually identical because they use different Unicode representations, such as precomposed and combining-character forms.

The operation is read-only.

## PYC Cleanup

The PYC cleanup operation deletes `.pyc` files from the selected directory.

When recursive mode is enabled, matching files in subdirectories are also deleted.

This operation should be tested against disposable or regenerable data when its behavior is changed.

## Initialization

This feature does not require startup initialization.

It is discovered by the Logistics feature registry but performs no work until a File Tools action is used.
