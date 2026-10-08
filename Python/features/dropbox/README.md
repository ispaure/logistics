# Dropbox Feature

Developer notes. See the [user guide](user_docs/index.md) for controls and setup,
and [UI architecture](../UI_ARCHITECTURE.md) for shared contribution conventions.

Provides Dropbox-specific maintenance tools for Logistics.

## Responsibilities

- Detect Dropbox conflicting-copy files.
- Determine whether a conflicting copy still has its original file.
- Report conflicting copies that require manual review.
- Safely delete conflicting copies only when every detected conflict has a corresponding original.

## Structure

- `detection.py` locates Dropbox account roots and lists their folders.
- `ui_contributions.py` contributes folder sources and the cleanup workflow.
- `conflicts.py` contains conflicting-copy detection, reporting, and cleanup behavior.

## Conflicting Copy Safety

The Folders page offers one source per account discovered through Dropbox's platform-specific `info.json`, listing immediate child directories of each account root. Missing or unconfigured installations contribute no sources. Local folders inside detected roots receive a Conflicting Copies workflow.

Conflicting-copy deletion is intentionally conservative.

Before deleting anything, Logistics analyzes all detected conflicting copies in the target directory.

Deletion is aborted when:

- A conflicting copy does not have a corresponding original file.
- A conflicting filename cannot be interpreted safely.

When either condition occurs, no conflicting copies are deleted.
