# Dropbox Feature

Provides Dropbox-specific maintenance tools for Logistics.

## Responsibilities

- Detect Dropbox conflicting-copy files.
- Determine whether a conflicting copy still has its original file.
- Report conflicting copies that require manual review.
- Safely delete conflicting copies only when every detected conflict has a corresponding original.

## Structure

- `conflicts.py` contains conflicting-copy detection, reporting, and cleanup behavior.
- `__init__.py` exposes the feature to the Logistics feature registry.

## Conflicting Copy Safety

Conflicting-copy deletion is intentionally conservative.

Before deleting anything, Logistics analyzes all detected conflicting copies in the target directory.

Deletion is aborted when:

- A conflicting copy does not have a corresponding original file.
- A conflicting filename cannot be interpreted safely.

When either condition occurs, no conflicting copies are deleted.

## Initialization

This feature does not require startup initialization.

It is discovered by the Logistics feature registry but performs no work until a Dropbox maintenance action is used.
