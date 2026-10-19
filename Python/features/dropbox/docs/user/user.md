# Browse Dropbox folders and clean conflicts

Dropbox is an optional local source; Logistics does not require it for software
or credentials. Account roots are detected from Dropbox's installed account settings.

## Browse

Choose the **Dropbox** source on **Workspaces** and select a folder. Multiple accounts
are listed separately. Missing/unconfigured Dropbox installations contribute no
sources; install and configure Dropbox separately if you want this source.

## Review conflicting copies

1. Select a folder inside a detected Dropbox account.
2. Open **Conflicting Copies…**.
3. Analyze the reported files before choosing cleanup.

The review compares contents, not just filenames. **Delete reviewed identical
copies** removes only copies that match their originals byte for byte and have
not changed since review. Copies with unique edits, missing originals or ambiguous
names stay in place. Changing the folder or recursion option requires a new review.
Scanning and deletion run in the background. Cancellation leaves completed
changes in place; the result reports failures and unprocessed copies.

## More help

See [Using Logistics](../../../../../docs/user/user.md) for navigation and settings.

Cleanup deletes reviewed copies directly; it does not move them to Trash and has
no Undo. The original matching file remains. Dropbox may propagate those deletions
to other devices according to its own settings; Logistics does not control or
verify that service-side recovery.
