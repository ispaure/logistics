# Open and export Calibre libraries

Calibre controls appear on **Folder Hub** when the selected local folder contains an
immediate child library with `metadata.db`.

## Open a library

1. Select the local folder on Folders.
2. Choose the library in its Calibre section.
3. Use the launch action. Calibre must be installed or available through the
   feature's platform-specific software resources.

On Linux, Logistics checks native Calibre and Flatpak. Windows uses the supplied
executable; macOS retains its bundled-archive installation fallback.

## Export books

Choose **Export books…**, select a dedicated folder and click **Review export**.
The table lists every copy, update, retained file and deletion. Check it before
choosing **Apply reviewed export**. The destination is a complete EPUB mirror;
unrelated files there can be listed for deletion. Keep them in another folder.

The BOOX shortcut fills in `/Volumes/BOOX-SD` when that device is mounted.
Other devices and platforms use the folder chooser. Work runs in the background;
cancellation stops between complete steps. Completed changes remain. Changed
sources or destinations stop the operation; review again before retrying.

## More help

See [Using Logistics](../../../../USER_GUIDE.md) for navigation and settings.
