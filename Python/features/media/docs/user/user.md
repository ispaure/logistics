# Rename MKA chapters from a CSV

Enable **Media Tools** under **Settings → Features** to use these tools.

Rename chapter audio files in one folder using their chapter titles from a CSV.

## Prepare the folder

Keep exactly one CSV alongside top-level files named like `Chapter_01.mka`.
The CSV has chapter number in the first column and chapter name in the second:

```text
1,Introduction
2,The journey
```

## Rename

1. Choose **Debug → Rename MKA from CSV…**.
2. Select the chapter folder.
3. Choose **Review names** and check the current/new name table.
4. Choose **Apply reviewed names** and read the result.

Every MKA must have a matching valid row and a nonempty title. Existing destination
names stop the plan. All planned names are validated before renaming starts; the
action modifies filenames, not audio contents. Keep a copy if you need the original
names. If validation fails, correct the CSV or filenames and retry.

## More help

See [Using Logistics](../../../../../docs/user/user.md) for navigation and settings.

The rename engine attempts rollback after cancellation or a handled error. If
another process blocks recovery, the result shows staged and original paths;
keep staged files and recover them from those reported locations. The dialog
has no retained Undo action after success. See [Bulk Rename](../../../../ui_new/bulk_rename/docs/user/user.md)
for general filename transformations instead of CSV chapter naming.
