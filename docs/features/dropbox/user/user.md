# Browse Dropbox folders and clean conflicts

Dropbox is an optional local source; Logistics does not require it for software
or credentials. Account roots are detected from Dropbox's installed account settings.

## Browse

Choose **Workspaces → Local**, select **Dropbox** in the **Source** dropdown,
then select a folder. With multiple accounts, sources are labelled
**Dropbox [Account]**; each lists its root’s immediate child folders. Missing/unconfigured Dropbox installations contribute no
sources; install and configure Dropbox separately if you want this source.

## Review conflicting copies

1. Select a folder inside a detected Dropbox account.
2. Open **Conflicting Copies…**.
3. Choose **Review conflicting copies**. **Include subfolders** starts enabled;
   turn it off to inspect only the selected folder.
4. Check each reported original and result, then choose
   **Delete reviewed identical copies** and confirm if you want to remove them.

The review compares contents, not just filenames. **Delete reviewed identical
copies** removes only copies that match their originals byte for byte and have
not changed since review. Copies with unique edits, missing originals or ambiguous
names stay in place. Changing the folder or recursion option requires a new review.
Scanning and deletion run in the background. Cancellation leaves completed
changes in place; the result reports failures and unprocessed copies.

## More help

See [Using Logistics](../../../user/user.md) for navigation and settings.

Cleanup deletes reviewed copies directly; it does not move them to Trash and has
no Undo. The original matching file remains. Dropbox may propagate those deletions
to other devices according to its own settings; Logistics does not control or
verify that service-side recovery.

## Scope and troubleshooting

This feature reads folders already managed by the installed Dropbox client; it
does not sign in, download an account or control Dropbox synchronization. If no
source appears, check that the Dropbox client has configured an existing local
account folder. Multiple accounts are discovered from the client's settings.

Conflict detection recognizes filenames containing ` conflicted copy ` inside
parentheses. It is a naming-based maintenance tool, so other conflict naming
formats may not appear. A blank or preserved result does not establish that two
versions have been merged. Keep or reconcile unique edits manually.

See [mobile scope](../user_mobile/user_mobile.md) for Android and iOS alternatives.
