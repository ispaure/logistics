# Open and export Calibre libraries

## Open a library

On **Workspaces**, select the local parent folder of a library containing `metadata.db`. Select the library, then choose **Open Library Folder** or **Launch Calibre**.

## Export books

Choose **Export books…**, select a dedicated folder and click **Review export**. Inspect every proposed deletion before **Apply reviewed export**. The destination is an EPUB mirror and unrelated files can be deleted. The BOOX shortcut uses `/Volumes/BOOX-SD/Calibre [EPUBs]/<library>` when mounted.

## More help

- [Using Logistics](../../../user/user.md)
- [Read EPUBs in Books](../../books/user/user.md)
- [Calibre on mobile](../user_mobile/user_mobile.md)

## What the export preserves

EPUBs are copied by author and book title. The source library stays intact. Copies are verified before obsolete exports are removed. Interruption can leave a partial mirror. Review again to reconcile it. There is no Undo.

## If controls or launching are unavailable

Detection checks only immediate child folders. Windows uses configured `Calibre2/calibre.exe`. macOS checks `/Applications/calibre.app` and the configured `calibre.app.zip`. Linux checks native Calibre and Flatpak. Resolve path overlap, directory links or filename collisions before reviewing an export again.
