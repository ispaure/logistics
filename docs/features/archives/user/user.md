# Archive manager

Enable **Archives** in Settings, then open **Documents → Archives** or an archive from File Browser.

## Explore an archive

Use **Open archive…** or drop an archive. Browse folders and use **Search all entries** to include descendants. Double-click a file or use **Preview file** for UTF-8 text up to 256 KiB or first-frame images up to 16 MiB and 25 megapixels.

## From the file browser

Double-click ZIP or TAR to open the manager. Use **Archives → Open archive manager…** for CBZ, whose default reader is Comics. The context menu also offers extraction and creation. **Archive Contents** shows ZIP and TAR headers, including encrypted entry names.

## Create and edit

Use **Create archive…** to add sources, choose a format and destination. Enable **Protect ZIP with an AES-256 password** to encrypt contents. Entry names stay visible.

Use **Edit ZIP → Add files… / Add folder…** to add at the root, or **Remove selected entries…** to remove whole selected subtrees. Editing replaces the verified archive and has no Undo or automatic backup. Keep a copy before editing. Mixed encrypted/plain ZIPs cannot be edited.

## Extract and check

**Extract all…** or **Extract selected…** stages files in a new folder. Existing destinations, unsafe paths, links and colliding names are refused. **Test integrity** checks ZIP CRCs or AES authentication and TAR readability.

| Format | Browse, extract and test | Create | Edit |
| --- | --- | --- | --- |
| ZIP, AES ZIP, CBZ | Yes | ZIP | Yes |
| TAR, TGZ, TXZ | Yes | Yes | |
| TBZ2 | Yes | | |
| 7z, RAR, split | | | |

## Keyboard shortcuts

**Ctrl+O** opens, **Ctrl+N** creates, **Ctrl+F** searches, **Alt+Up** moves up and **F5** reloads.

## Create an encrypted ZIP from the file browser

### Create a ZIP from a selection

Select files or folders, then choose **Archives → Create encrypted ZIP…**. Choose a new destination outside the source folders and use the configured password or enter and confirm one. Logistics verifies the ZIP before publishing it. Existing destinations are refused.

## Passwords

To reuse a password, add this section to the nearest applicable `remoteConfig.ini`.

```ini
[LogisticsZIP]
archive_password = your-password
```

An empty or missing key in the nearest section stops inheritance. The INI stores plain text passwords. Entered passwords stay in session memory. Different configured passwords require separate ZIPs. Recipients need WinZip AES support.

## Cancel or recover

Cancel to discard staged output. If creation fails, check the reported error, space and permissions before retrying. For in-place CBZ encryption, see [Comics](../../comics/user/user.md).

## More help

- [Using Logistics](../../../user/user.md)
- [Archives on mobile](../user_mobile/user_mobile.md)
