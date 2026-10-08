# Inspect paths and remove Python bytecode

These standalone tools work on a folder selected in Debug.

## Inspect unusual characters

Choose **Debug → List Weird Characters…**, select a folder and the recursion option,
then run the scan. It reports paths containing the configured Unicode characters.
The operation is read-only. Visually identical characters may have different Unicode
representations; review the exact reported path before renaming files yourself.

## Remove bytecode

Choose **Debug → Bulk Delete PYC…**, select the target folder and whether to include
subfolders, then run cleanup. It deletes matching `.pyc` files, which Python can
normally regenerate. It does not delete Python source files. Choose the target
carefully; cleanup has no undo command.

## More help

Read [Using Logistics](../../../../USER_GUIDE.md) for navigation, resources and
feature controls. Use Back/Forward in this viewer to return to a previous guide.
