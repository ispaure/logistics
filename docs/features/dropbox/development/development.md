# Dropbox Feature

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

Developer notes. See the [user guide](../user/user.md) for controls and setup,
and [UI architecture](../../../development/features.md) for shared contribution conventions.

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

## Platform and validation boundary

The feature contributes desktop folder sources and a Qt workflow; it has no
mobile adapter or mobile source manifest. See [mobile scope](../user_mobile/user_mobile.md).
Detection reads `%APPDATA%/Dropbox/info.json` or `%LOCALAPPDATA%/Dropbox/info.json`
on Windows, and `~/.dropbox/info.json` on macOS/Linux. It uses the first existing
candidate and retains only configured roots that exist as directories.

`ui/dialogs.py` owns review invalidation when the path or recursion changes.
`review_conflicts` skips symbolic-link candidates, captures lstat identities and
compares SHA-256 hashes. Apply rechecks both identities and hashes before unlinking
the copy. This is a best-effort filesystem recheck, not an atomic transaction
with Dropbox's sync client.

`Python/tests/integrations/test_dropbox.py` covers deletion of an identical copy,
preservation of unique content, and changes to either file after review. These
local-file fixtures do not verify a real Dropbox account, OS source discovery or
service-side recovery. The November 4 documentation audit read source/tests only;
it did not rerun tests or establish native acceptance.
