# Developing Dropbox folder tools

Logistics discovers folders managed by the desktop Dropbox client and reviews
conflicting copies before offering cleanup. See the [user guide](../user/user.md)
for setup and the [mobile guide](../user_mobile/user_mobile.md) for platform scope.

## Try a change to conflict cleanup

On desktop, follow **Workspaces → Local → Source → Dropbox**, select a folder,
and open **Conflicting Copies… → Review conflicting copies**. The workflow in
`Python/features/dropbox/ui_contributions.py:_open_conflicts` creates
`DropboxConflictsDialog`. Its Review and Delete buttons use
`review_conflicts` and `delete_reviewed_conflicts` in
`Python/features/dropbox/conflicts.py`.

For example, change `_require_reviewed_identity` to report which path
changed after review. Keep the identity and symlink checks for both files.
Use the existing synthetic
`note.txt` and `note (user conflicted copy 2026).txt` fixture to exercise your
change in a temporary directory. The test replaces the original or the copy
after hashing. Run from the repository root with the desktop environment set up:

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_dropbox.py
```

Expect five passing tests. Both files survive a replacement or edit after
review. An unchanged identical copy can be removed, and cancellation during
Apply lets the current item finish. The fixture uses local files and exercises
the cleanup logic directly. Account discovery, Qt interaction and Dropbox
recovery require separate checks.

## Discovery and workflow ownership

`__init__.py:register` exposes a desktop folder source, folder action and
workflow through `ui_contributions.py:get_contributions`. `detection.py`
reads the first existing Dropbox account settings file from
`%APPDATA%/Dropbox/info.json` or `%LOCALAPPDATA%/Dropbox/info.json` on Windows
and `~/.dropbox/info.json` on macOS and Linux. Existing account roots each
contribute a source with their immediate child directories. Local selections
resolved inside those roots receive the cleanup action. The feature has no
mobile registration or source manifest.

## Review and deletion safety

The analyzer recognizes the Dropbox conflicting-copy filename pattern. Review
skips symlink candidates, records `lstat` identities and compares SHA-256
hashes. Unique edits, missing originals and ambiguous names stay on disk.
`ui/dialogs.py:DropboxConflictsDialog` invalidates the review when the folder
or recursion changes and runs review and deletion in cancellable workers.

Deletion verifies both identities before hashing and again immediately before
unlinking the identical copy. An observed edit or replacement fails that item.
There is still a race between the final check and unlinking. Apply deletes
directly with no Trash or Undo. Re-review after changes and inspect failures
and remaining items before retrying. Dropbox owns propagation and recovery.
