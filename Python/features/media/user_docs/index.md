# Rename MKA chapters from a CSV

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
3. Run the rename and review the result.

Every MKA must have a matching valid row and a nonempty title. Existing destination
names stop the plan. All planned names are validated before renaming starts; the
action modifies filenames, not audio contents. Keep a copy if you need the original
names. If validation fails, correct the CSV or filenames and retry.

## More help

Read [Using Logistics](../../../../USER_GUIDE.md) for navigation, resources and
feature controls. Use Back/Forward in this viewer to return to a previous guide.
