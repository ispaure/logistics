# Inspect paths and remove Python bytecode

In **File Browser**, right-click the folder to inspect. If File Tools is
missing, enable it in **Settings → Features**.

## Inspect unusual characters

Choose **List Weird Characters…**, decide whether to include subfolders, then
click **Scan files**. Review the matching paths and Unicode code points before
renaming anything.

## Remove bytecode

Choose **Bulk Delete PYC…**, set **Include subfolders**, then click **Scan PYC
files**. Review the paths and confirm **Delete reviewed files…**. A changed
folder or recursion setting needs a new scan. Changed, replaced and newly added
files are kept. Python source and file links stay in place.

System-folder protection follows **Python/maintenance.ini**. Cancel stops
between files. Completed deletions stay deleted and have no Undo.

## More help

See [Using Logistics](../../../user/user.md).

## Platform availability

See [mobile availability](../user_mobile/user_mobile.md).
