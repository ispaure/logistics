# Browse Dropbox folders and clean conflicts

Dropbox is an optional local source; Logistics does not require it for software
or credentials. Account roots are detected from Dropbox's installed account settings.

## Browse

Choose the **Dropbox** source on **Known Folders** and select a folder. Multiple accounts
are listed separately. Missing/unconfigured Dropbox installations contribute no
sources; install and configure Dropbox separately if you want this source.

## Review conflicting copies

1. Select a folder inside a detected Dropbox account.
2. Open **Conflicting Copies…**.
3. Analyze the reported files before choosing cleanup.

Cleanup deletes detected conflicting copies only when every conflict has a
corresponding original and its name can be interpreted safely. If any conflict
fails those checks, the whole deletion is aborted. This check does not merge the
contents of conflicting and original files; keep any edits you need before cleanup.

## More help

Read [Using Logistics](../../../../USER_GUIDE.md) for navigation, resources and
feature controls. Use Back/Forward in this viewer to return to a previous guide.
