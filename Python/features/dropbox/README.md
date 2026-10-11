# Dropbox Feature

For workflows, settings and troubleshooting, see the [user guide](user_docs/README.md).

Developer notes. See the [user guide](user_docs/README.md) for controls and setup,
and [UI architecture](../../../docs/developer/features.md) for shared contribution conventions.

Provides Dropbox-specific maintenance tools for Logistics.

## Responsibilities

- Detect Dropbox conflicting-copy files.
- Determine whether a conflicting copy still has its original file.
- Report conflicting copies that require manual review.
- Review candidates and remove only unchanged, byte-identical conflict copies.

## Structure

- `detection.py` locates Dropbox account roots and lists their folders.
- `ui_contributions.py` contributes folder sources and the cleanup workflow.
- `conflicts.py` contains conflicting-copy detection, reporting, and cleanup behavior.

## Conflicting Copy Safety

The Folders page offers one source per account discovered through Dropbox's platform-specific `info.json`, listing immediate child directories of each account root. Missing or unconfigured installations contribute no sources. Local folders inside detected roots receive a Conflicting Copies workflow.

Review records identities and hashes without changing files. Apply rechecks the
conflict and original before deleting the identical copy. Unique edits, missing
originals, ambiguous names and changed files remain. The dialog retains results
and runs scanning/deletion on owned workers with cooperative cancellation.
