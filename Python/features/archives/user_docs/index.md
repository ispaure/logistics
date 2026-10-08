# Create encrypted ZIPs

Create a separate password-protected ZIP from selected files or folders. Your
original files stay in place.

## Create a ZIP

1. Open **Debug → Open File Browser…** and choose your source folder.
2. Select the files or folders to include. Right-click a selection and choose
   **Archives → Create encrypted ZIP…**.
3. Choose the output name and location, outside the selected folders.
4. Use the configured password, or enter and confirm a password when asked.
5. Start creation. The dialog checks the sources, writes the ZIP and verifies it
   before publishing the finished file.

| Selection | Suggested output | Contents |
| --- | --- | --- |
| One file | The file's name with `.zip` | The original file |
| One folder | The folder's name with `.zip` | The folder and its contents |
| Several items | `Selection.zip` | All selected items, with overlaps removed |

Existing output files are never overwritten. A selected CBZ is packaged as a file
inside the ZIP; its pages are not compressed or changed.

## Passwords

To reuse a password, put this in `remoteConfig.ini` beside a file or inside a
selected folder (or an ancestor):

```ini
[LogisticsZIP]
archive_password = your-password
```

The nearest section wins. An empty password in that section stops inheritance.
Keep real passwords private: the INI stores them as plain text. An entered password
is not saved automatically. Different configured passwords require separate ZIPs.
ZIP member names are visible without a password; reading file contents requires
an application that supports WinZip AES.

## Cancel or recover

**Cancel ZIP creation**, Escape or closing requests cancellation. The dialog waits
for the worker to stop, discards incomplete output and leaves sources intact.
A completed ZIP remains successful if cancellation arrives after publication.
If creation fails, read the dialog's explanation, check the output location,
permissions and available disk space, then retry.

For encrypting CBZ contents in place, use the [Comics guide](../../comics/user_docs/index.md).

## More help

Read [Using Logistics](../../../../USER_GUIDE.md) for navigation, resources and
feature controls. Use Back/Forward in this viewer to return to a previous guide.
