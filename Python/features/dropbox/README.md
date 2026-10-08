# Dropbox Feature

For usage instructions, see the [user guide](user_docs/index.md). This README
covers development, implementation details and validation.


Provides Dropbox-specific maintenance tools for Logistics.

## Using this feature

Choose the detected **Dropbox** source on **Folders**, select a folder, then
open **Conflicting Copies…**. Dropbox is an optional source; it is not required
for Logistics resources or managed local folders.

See [shared setup and resource paths](../../../CONFIGURATION.md) and the
[Logistics feature index](../../../README.md#features) for application-wide setup.

## Responsibilities

- Detect Dropbox conflicting-copy files.
- Determine whether a conflicting copy still has its original file.
- Report conflicting copies that require manual review.
- Safely delete conflicting copies only when every detected conflict has a corresponding original.

## Structure

- `detection.py` locates Dropbox account roots and lists their folders.
- `ui_contributions.py` contributes folder sources and the cleanup workflow.
- `conflicts.py` contains conflicting-copy detection, reporting, and cleanup behavior.
- `__init__.py` exposes the feature to the Logistics feature registry.

## Conflicting Copy Safety

The Folders page offers one source per account discovered through Dropbox's platform-specific `info.json`, listing immediate child directories of each account root. Missing or unconfigured installations contribute no sources. Local folders inside detected roots receive a Conflicting Copies workflow.

Conflicting-copy deletion is intentionally conservative.

Before deleting anything, Logistics analyzes all detected conflicting copies in the target directory.

Deletion is aborted when:

- A conflicting copy does not have a corresponding original file.
- A conflicting filename cannot be interpreted safely.

When either condition occurs, no conflicting copies are deleted.

## Initialization

This feature does not require startup initialization.

It is discovered by the Logistics feature registry but performs no work until a Dropbox maintenance action is used.
