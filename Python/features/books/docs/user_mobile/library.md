# Books and comics on mobile

## Books and comics

**Books & Comics** lists configured library folders from Local and unlocked
LocalCrypt copies. Detection uses each collection's `remoteConfig.ini`, matching
desktop: `[LogisticsComics] libraries = Comics,Mangas` names immediate child
folders, in that order. Existing ComicRack/YACReaderLibrary configurations also
identify a collection. Missing folders and unconfigured individual files are not
listed. Tap a folder to browse it and open a book or comic; **Refresh** discovers
configuration changes and newly pulled copies. LocalCrypt names stay in memory
and disappear when credentials are locked or forgotten.

Use **Import…** for a standalone EPUB or comic. EPUB and
CBZ/ZIP imports create private copies; the selected source is never
changed. Imports open directly and remain available through document sessions.
The Books and Comics library shows configured library folders only; it has no
separate imported-items section, selection switches or imported-results paging.
There is no folder search field; the available configured folders appear directly.
Previous/Next and horizontal swipes turn EPUB pages without vertical scrolling.
The hamburger opens nested chapters; fullscreen hides navigation and reading
controls. Comic images fit the native image area. The EPUB view follows
system light/dark appearance and uses the configured font size.

Standalone password-protected CBZ/ZIP comics support AES and legacy ZipCrypto
on iOS and Android, without rclone or a credential package. Import one through
Workspaces, then enter its ZIP password and choose **Unlock comic**, or press Enter.
A wrong password clears the field and keeps the prompt ready for another attempt.
**Cancel** keeps the imported encrypted copy. The password stays only with the
active reader; closing the reader clears the password, decoded-page cache and
displayed pages. Opening after closing or restarting asks again. There is no
separate relock command. Local/LocalCrypt folder readers continue to use the
configured INI archive password when available. The library keeps the
original encrypted archive bytes and never writes an extracted/decrypted archive.
ZIP member names remain visible, as they do in ordinary password-protected ZIPs.

Progress remembers the EPUB chapter and text anchor, or the current comic page. EPUB **Bookmark** / **Unbookmark** and its
bookmark selector return to saved passages. Comics have page navigation without
bookmark controls. Comic pages use
natural filename order. Right-to-left manga metadata is identified; single-page
Previous/Next controls still refer to reading-order positions.
Comic layout defaults to **auto**: two portrait pages when the reading area is
wider than tall, otherwise one. Right-to-left metadata places the earlier page on
the right and reverses swipe direction. Existing Single/Double choices can be
changed under **Appearance → Comic page layout**.
Comic appearance contains only page layout. Font family/size, line spacing, text
width, text margins and text themes belong to EPUB appearance. Comic menus omit
read-aloud, chapter search and contents/bookmarks; imported comics offer **Comic
pages…** for direct page selection. The same format split applies to LocalCrypt
and remote previews. Applying comic layout does not change EPUB preferences.
All comic readers use the same menu order, **Comic pages…** selector and
**Close comic** command. Read-only previews omit metadata editing. With reading
controls visible, **Previous comic** (`|≪`) and **Next comic** (`≫|`) are icon
buttons above the image; page arrows and the page slider remain below it. These
file buttons hide in fullscreen and remain disabled when unavailable. Switching
comics with them preserves whether reading controls are visible. First/last page
jumps use the page slider or **Comic pages…** selector. The overflow menu omits
file switching and **All documents**; use the existing navigation to leave reading.
**… → Info…** shows the opened comic's path. Saved imports show their current
local copy, remote previews show `remote:path`, and LocalCrypt folder readers
show their logical LocalCrypt path. The dialog contains no credentials.
In the comic reader, horizontal swipes turn pages in both normal and fullscreen
views, including swipes from the screen edge. They do not navigate Back. Zoomed
pages use dragging to pan; fit the page to resume swipe paging. Use the visible
Back control to leave the reader.
Comics fill the available reading width immediately on opening and resize with
the reader. The image keeps its aspect ratio, so some pages can have natural
letterboxing. With controls visible, books and comics use the same hamburger
position as Documents; on iOS it is in the navigation bar. Bottom controls,
reading status and progress indicators stay above the destination bar.

Ordinary CBZ/ZIP comics stream into the private library without a fixed archive
or total decompressed-size cap. Reading seeks archive headers and fetches only the
chosen page. Both EPUB and comic archives are limited to 5,000 entries; EPUB
imports retain the 256 MiB archive/expanded-total and 8 MiB per-member limits.
Native comic images must be PNG/JPEG/WebP,
no larger than 8 MiB or 16 megapixels, with each dimension at most 8,192 pixels.
Static lossy, lossless and transparent WebP pages render directly at their original
resolution; archives are preserved. Animated WebP is not supported. Comics with
other page formats are rejected rather than silently skipping pages.
EPUB chapters and rendered HTML are limited to 2 MiB. Small PNG/JPEG/WebP illustrations
(up to 256 KiB each, 1 MiB total) are embedded; unsupported/large illustrations
show an omission label. Raw scripts, forms, embedded objects, source styles and
external resources are removed. Chapter links are inert; use the chapter selector.
DRM, standalone encrypted EPUBs, CBR/RAR and fixed-layout SVG books are not supported.

Imports hash bytes during their streamed copy. The checksum is verified on
opening after a restart; reopening an unchanged file in the same session reuses
a bounded revision-keyed verification cache. Changed files invalidate it, and
individual page reads reject concurrent changes. Re-import a changed private copy as a new entry. Malformed
library records are preserved and reported. Progress/bookmark writes reject stale
records rather than overwriting another change.

### Reader navigation and imported metadata

Imported EPUBs now provide nested contents/internal links, current-chapter search,
page-turn navigation, fullscreen and passage-based resume/bookmarks. Android and iOS provider
EPUBs share rich rendering, nested contents, internal links, highlighted search and
appearance controls through a private browser view. Their positions and bookmarks
remain session-only; other backends retain bounded native text passages. See the [Books guide](reading.md#native-mobile-reading)
for pagination and persistence differences.

Comic readers offer single/automatic/two-page layouts, manga-aware spreads and
spread-aware turns. Imported comics also have first/last and neighboring-comic
commands; folder-backed provider comics can open neighboring comics from their
reader menu. See the [Comics guide](../../../comics/docs/user_mobile/reading.md#native-mobile-library).

The Books & Comics catalogue now includes imported copies. Reader menus edit
metadata on ordinary imported EPUBs/comics; selecting comic rows opens explicit-field
batch editing. These writes change the imported copy, preserve page/resources and
leave the external source untouched. Existing provider metadata saves keep their
own encrypted-publication policy. A recovery journal completes an imported
archive/checksum-record publication interrupted after the archive was saved.
