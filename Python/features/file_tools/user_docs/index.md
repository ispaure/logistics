# Inspect paths and remove Python bytecode

Open **Debug → Open File Browser…**, then right-click a folder. The **File Tools**
actions open dedicated windows for the selected folders. Enable File Tools in
**Settings → Features** if these actions are missing. These tools no longer appear as Debug
maintenance actions.

## Inspect unusual characters

Choose **List Weird Characters…**, set **Include subfolders**, and click **Scan
files**. The window stays open with matching paths, configured characters and
Unicode code points. Results are also shown when no files match. The scan is
read-only. Visually identical characters may have different Unicode representations;
review the reported code points before renaming files yourself.

## Remove bytecode

Choose **Bulk Delete PYC…**, set **Include subfolders**, and click **Scan PYC
files**. Review the listed paths, count, and byte total; the scan changes no files.
Click **Delete reviewed files…** and explicitly confirm those files. Changing the
folder or recursion setting requires a new scan. Files added after preview are
excluded, and changed/replaced files are reported and preserved. The window
stays open with each deleted file, any failures, and files left unprocessed after
cancellation. Python can normally regenerate `.pyc` files. Python source files and
file links are preserved; linked subfolders are not traversed.

Both tools run in the background. Closing a busy window requests cancellation;
wait for it to finish, then close the results window. Cancelling cleanup stops
between files. Completed deletions remain and have no undo command.

## More help

Read [Using Logistics](../../../../USER_GUIDE.md) for navigation, resources and
feature controls. Use Back/Forward in this viewer to return to a previous guide.

PYC cleanup also enforces the system-folder protection in `Python/maintenance.ini`.
