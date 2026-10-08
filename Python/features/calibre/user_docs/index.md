# Open and export Calibre libraries

Calibre controls appear on **Known Folders** when the selected local folder contains an
immediate child library with `metadata.db`.

## Open a library

1. Select the local folder on Folders.
2. Choose the library in its Calibre section.
3. Use the launch action. Calibre must be installed or available through the
   feature's platform-specific software resources.

On Linux, Logistics checks native Calibre and Flatpak. Windows uses the supplied
executable; macOS retains its bundled-archive installation fallback.

## Export books

Choose the available export action and use a dedicated device/export folder.
Exports form a complete one-way mirror: obsolete destination files, including
unrelated formats, are removed after changed books are copied successfully.
Do not keep unrelated files in that destination.

The BOOX workflow currently requires `/Volumes/BOOX-SD` to be mounted. Naming or
path collisions stop planning. Failed copy staging keeps the previous exports;
failures later in replacement/deletion can leave a partial update. Keep the device
connected until the operation finishes, then inspect the result before retrying.

## More help

Read [Using Logistics](../../../../USER_GUIDE.md) for navigation, resources and
feature controls. Use Back/Forward in this viewer to return to a previous guide.
