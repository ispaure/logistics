# Open and export Calibre libraries

Calibre controls appear on **Folder Hub** when the selected local folder contains an
immediate child library with `metadata.db`.

## Open a library

1. Select the local folder on **Folder Hub**.
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

The BOOX shortcut fills in `/Volumes/BOOX-SD/Calibre [EPUBs]/<library>` when that
device is mounted.
Other devices and platforms use the folder chooser. Work runs in the background;
cancellation stops between complete steps. Completed changes remain. Changed
sources or destinations stop the operation; review again before retrying.

## More help

See [Using Logistics](../../../../../docs/user/user.md) for navigation and settings.

## What the export preserves

The library remains the source; export does not edit it or perform format conversion.
The current dialog exports EPUBs, organized by author and metadata-derived book
name. Missing formats are reported; malformed metadata can fall back to a cleaned
folder name. Use [Books](../../../books/docs/user/user.md) to read or edit an EPUB
inside Logistics independently of Calibre.

Source and destination must not overlap or traverse links. Name collisions stop
the plan. Copies are staged and checked before publication, and obsolete exports
are removed only after copies succeed. This is not an all-or-nothing rollback:
interruption during publication/deletion can leave a partly updated mirror. Review
again to reconcile it; Logistics has no export Undo.
