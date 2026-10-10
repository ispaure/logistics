# Archive manager

Use **Archives** in the left rail, after the sync action icon and above Git.
It belongs to the existing Archives feature; enable that feature in Settings if
its icon is absent. The sync icon appears when folder actions exist.

## Explore an archive

Choose **Open archive…**, paste a path and press Enter, or drop an archive onto
the workspace. Browse the folder tree or double-click a folder in the contents
list. **Search all entries** searches the entire archive, including subfolders.
The table shows sizes, packed sizes, compression savings, dates and encryption.
Click column headers to sort; sizes sort numerically.

Select a file to see its details. **Preview file** (or double-click a file) displays images or reads
UTF-8 text without extracting or launching it. Text previews are limited to 256 KiB. Image previews show the first frame, bounded
to 16 MiB and 25 megapixels, and generate a thumbnail up to 1000 pixels.
Binary files can be extracted and opened in another application.

## Create and edit

**Create archive…** opens a source basket: add files and folders, choose a format
and destination, then create. Dropping ordinary files or folders opens the same
basket. ZIP compression offers Store, Fast, Balanced and Maximum. Enable
**Protect ZIP with an AES-256 password** for private file contents; entry names
remain visible. This workspace asks you to choose and confirm the new password.
The existing **Create encrypted ZIP…** browser action still uses configured
passwords as described below.

**Edit ZIP → Add files… / Add folder…** adds entries at the archive root.
**Remove selected entries…** removes files or whole folder subtrees after a
confirmation. Editing rebuilds and verifies the ZIP before saving. Added names
cannot silently replace existing entries. Mixed encrypted/plain ZIPs cannot be
edited; their existing protection policy is preserved. TAR archives are browsable
and extractable; edit controls are available for ZIP and CBZ.

## Extract and check

**Extract all…** or **Extract selected…** asks for a parent location and a new
folder name. Selected folders include their descendants. Extraction preserves
paths, empty directories, file timestamps and Unix executable bits. The manager
stages the complete selection before publishing it; it never overwrites an
existing destination folder. It rejects unsafe paths, symbolic links, special
TAR entries and colliding names.

**Test integrity** reads every entry. ZIP checks CRCs or AES authentication;
TAR is checked for readable payloads and valid paths, but has no per-entry checksum.
Encrypted ZIPs use the existing configured/session password service and ask for
a password when necessary. Entered passwords are not written to configuration.

Long jobs run in the background with progress and cancellation. Cancelling
creation, extraction or editing discards staged output. Closing Logistics asks
workers to stop and waits for them to finish before destroying the page.

| Format | Browse / extract / test | Create | Add / remove |
| --- | --- | --- | --- |
| ZIP, AES ZIP, CBZ | Yes | ZIP, including AES | Yes |
| TAR, TAR.gz / TGZ, TAR.xz / TXZ | Yes | Yes | No |
| TAR.bz2 / TBZ2 | Yes | No | No |
| 7z, RAR, split archives | Not currently supported | No | No |

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| Ctrl+O | Open archive |
| Ctrl+N | Create archive |
| Ctrl+F | Search |
| Alt+Up | Parent folder |
| F5 | Reload archive |

## Create an encrypted ZIP from the file browser

Create a separate password-protected ZIP from selected files or folders. Your
original files stay in place.

### Create a ZIP from a selection

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
