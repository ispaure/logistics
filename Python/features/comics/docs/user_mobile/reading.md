# Comics mobile workflows

## Mobile development builds

The independent native app has private EPUB and PNG/JPEG CBZ/ZIP reading,
chapter/page progress and bookmarks. It has a smaller format/UI scope than this
desktop guide. See the [mobile guide](../../../../../docs/user_mobile/user_mobile.md)
for imports, limits and current validation status.

## Native mobile library

To inspect retained imports, open **Settings → Books & Comics → Saved books &
comics…**. The page shows the file count, total archive/reading-record size and
per-import sizes, including closed imports. **Delete local copy…** removes the
import and its reading records after confirmation, leaving its original source
unchanged. Closing a comic in Open documents only closes the reader. Imported
copies are private app data on iOS and do not appear in Files.

On iOS and Android, **Books & Comics** lists library folders configured by
`remoteConfig.ini` in Local and unlocked LocalCrypt copies, using the same
`[LogisticsComics] libraries` names as desktop. Tap a library folder to browse its
contents. Imported books/comics appear in their own section beneath configured library folders.

**Books & Comics → Import…** accepts standalone
password-protected AES/ZipCrypto CBZ/ZIP comics. Unlock with the comic’s ZIP password;
rclone credentials are unnecessary. See the [mobile reading guide](../../../books/docs/user_mobile/library.md#books-and-comics)
for password retries and supported page formats. There is no separate comic
relock action; configured INI archive passwords continue to unlock folder reads.
Rclone crypt credential locking is a separate connection operation.

Mobile Local and LocalCrypt comics use the same fit/zoom/swipe and reading-mode
controls, with Previous/Next available when controls are visible. Comics do not
show a chapter/browser hamburger button. Use **Reader actions → Comic pages…**
to jump to a page, or **Show in folder** to browse the comic’s source when available. LocalCrypt
readers expose page navigation without bookmark controls. Readers opened from Files return to the
same folder through Back, including after visiting reader tools.

Mobile imports, provider-backed readers and ordinary browser covers ignore macOS
resource-fork image entries and use the same natural page order. Unsupported
image formats fail explicitly instead of silently disappearing from the comic.

Choose **Appearance → Comic page layout** in an imported reader, or **Appearance…**
in a provider reader, for Single, Automatic or Two pages. Portrait page
pairs respect manga visual order; landscape and ComicInfo DoublePage pages remain
single. Automatic is the default and follows the reading area orientation.
Two pages pairs adjacent portrait or square pages; a final unpaired page appears
alone. While sharing a comic to an external display, both the phone and TV
temporarily use two pages, including on a portrait phone, and show a page wider
than tall whole on its own. Disconnecting restores the saved layout and wide-page
setting immediately; sharing never saves these overrides. ComicInfo `Manga=YesAndRightToLeft` places the
earlier page on the right; left-to-right comics place it on the left.
Comic appearance shows page layout and the portrait wide-page switch. EPUB font, spacing, text width, margins
and theme controls do not appear in comics, and applying comic layout leaves
those preferences unchanged. Comic menus omit read-aloud, chapter search and
bookmarks; **Comic pages…** in an imported reader opens the page selector.
Imported, Local, LocalCrypt and remote comics use the same menu names and order,
page selector and appearance form. Read-only remote previews omit metadata
editing. Previous/Next comic use `|≪` / `≫|` buttons above the image when controls
are visible, separate from the page arrows and slider below. File buttons disable
when unavailable and hide in fullscreen. Switching comics preserves the controls'
visibility. Neither file switching nor All documents appears in the overflow menu.
**Close comic** closes the reader without deleting a saved copy.
**… → Info…** shows only the opened comic's path: the saved file path for an
import, `remote:path` for a remote preview, or the logical LocalCrypt location
for a folder-backed encrypted file. Imported copies show their current stored
path; their original import location is not reconstructed.
**Appearance → Split wide pages in portrait** is on by default, including
when an older preferences file has no value for this setting. Except while sharing
to an external display, a landscape source image in a taller-than-wide reading
area is displayed as two overlapping views when this setting is enabled.
Next/swipe moves from the first half to the second, then to the next source page;
Previous reverses this order and enters a preceding wide page at its second half.
Left-to-right comics start on the left; right-to-left manga starts on the right.
Both halves include the central 8% of the original image so centre details remain
visible. The page status adds **1/2** or **2/2**; page counts and the scrubber still
refer to original archive pages. Imported comics remember the half when reopened;
provider readers retain it within their session. Pinch zoom and panning work on
the displayed half, with swipes turning only at fit size. Landscape and square
reading areas show the complete wide image. Turn the switch off to view complete
wide pages in portrait as well. The setting is separate from Single/Automatic/Two
pages and applies to imported, Local, LocalCrypt and remote comics.

Paired pages touch with no added gutter on phones, iPad landscape, TV output and
an unfolded Duo. An active reserved hinge region remains clear while folding.
At the beginning, a swipe before the first page briefly shows an arrow for the
reading direction (reversed for manga). If a previous volume is available, the
hint also offers it: repeat the boundary swipe within 2.5 seconds to open it.
At the end, the first forward boundary swipe offers the next volume; repeat
within 2.5 seconds to open it. Without an adjacent volume the hint says so and
keeps the current comic open. Folder-backed readers choose naturally ordered
CBZ/ZIP files in the current folder; imports use the imported library's order.
Hints appear on the internal screen only and clear on navigation or privacy cover.

Previous/Next and swipes advance past the displayed spread, or through each half
of a split wide page. Imported and provider
readers share small chevrons, a slim slider with a round thumb, and a compact
page-count badge in one footer row when reading controls are visible;
drag and release it to jump directly to a page. Manga places Next on the left and
Previous on the right, with slider progress running from right to left.
Automatic layouts reevaluate when the viewport changes. Single and Two-page
views also refit to the available width after rotation. Resizing waits while a
spread is zoomed; fitting it allows the pending layout update.

In fullscreen comics on iOS and Android, hold a thumb on the page for about
400 ms to show a magnifying bubble. The bubble enlarges the page beneath
its center and grows larger on tablet screens. The bubble sits close
to the thumb with a slight overlap. Keep holding and drag to move
the bubble. Near a screen edge, keep dragging toward the edge to inspect the
outermost pixels even after the bubble stops moving. Release to dismiss. The page stays still while the bubble is open.
Keep holding the page and tap **−** at the bottom left or **+** at the bottom right
with another finger. The compact buttons sit slightly outside the bubble’s corners,
with no zoom percentage over the page. Zoom changes through **150%, 170%, 190%, 210%,
230%, 250%**; the default is **190%**. Changes save immediately and are shared
with PDF readers, other open readers, and the next app launch. The same value
is available in **Settings → Books & Comics → Comic & PDF magnifier zoom**.
A second finger away from the buttons cancels the bubble for ordinary page pinch zoom. The bubble is disabled
when reading controls are visible and is cleared on page changes or leaving the
reader. It works on single pages and spreads, including Local/LocalCrypt comics.

Two-page spreads use one continuous zoom/pan surface. Pinch to zoom both pages
together, then drag across the join to inspect either page. Page proportions and
manga order are preserved. **Fit comic page** returns the whole spread to fit size.
Swipes turn pages only at fit size; while zoomed, dragging pans the spread.
Rotating while zoomed retains the current spread until you fit it. A failed page
decode or spread composition keeps the displayed spread and its zoom. Private
spreads stay in memory and are cleared on suspend/close; returning starts fitted.
After unlocking a session-only reader, a page released during background memory
cleanup reloads at the current page with fullscreen preserved. If reloading fails,
reading controls return with the error so you can navigate or close the comic.

Imported reader menus include First/Last page and Previous/Next comic. The page
selector also supports direct jumps. Neighboring imported comics use natural
filename order. Provider Previous/Next comic works within the current managed
folder; standalone encrypted-copy UUID storage has no sibling-folder route.

Ordinary imported comics now have **Edit metadata…**. In the catalogue, select
imported comic rows and choose **Edit selected comics metadata…** for a batch.
Only checked fields are written; checking an empty field explicitly clears it.
Mixed fields are kept unless checked. All selections are validated before writing.
Successful files stay saved if another file fails. **Cancel after current comic**
finishes the current verified save and leaves remaining items untouched. Failures
and unprocessed files are counted, and form values remain available for retry.

Metadata updates preserve page bytes and the external import source. Standalone
password-protected imports remain readable, but metadata rewriting needs a native
archive writer and is not enabled. Provider-backed encrypted metadata editing
retains its existing ciphertext transaction. Mobile compression, CBR conversion,
organization and provider-wide catalogue indexing remain outstanding. Imported
catalogue suggestions and recursive LocalCrypt batches are described below.


### Mobile collection search and folder batches

The imported catalogue searches filenames and indexed metadata, including title,
author, tags, series and publisher. Indexing runs in the background and the status
shows how many imports have been checked. Every ordinary import is eligible; the
former first-200 limit has been removed. Metadata fields contribute their first
4,096 characters. The catalogue shows 50 results at a time; use **Previous results**
and **Next results** to browse, or search across the entire indexed collection.
Selections remain checked when changing pages or searching.

The disposable index is stored locally, reuses unchanged archive revisions across
launches and updates after metadata saves. **Refresh** retries unreadable entries,
updates changed imports and removes deleted imports. Interrupted scans retain
completed work and continue on the next refresh. Filename search remains available
while metadata is loading. Protected imports do not contribute metadata or
suggestions, even if their archive password was remembered elsewhere. Private
provider documents never enter this ordinary-import index.

Imported single-comic and batch metadata forms offer existing author/tag/publisher
and other supported suggestions. Choosing a suggestion is an explicit edit; opening
a form does not change mixed values or select fields for publication. List-field
suggestions append without duplicates. Only checked batch fields are written.

In **Files → Actions**, choose **Edit comics in this folder…** for an ordinary local
folder. The selected folder (or current folder when no folder is selected) includes
nested CBZ/ZIP comics. Review the form and check fields before **Apply selected
fields**. Scans are bounded to 200 comics, 10,000 entries and 16 folder levels.
All selected files and patches are checked before the first write; changed or
unsupported archives stop preflight. After writing starts, files publish
independently. **Cancel after current comic** leaves completed saves in place and
remaining files untouched. Errors before publication keep the original contents;
already published saves are not rolled back. Reopen the batch if a saved revision
cannot be refreshed. Repeated Apply
is blocked while a batch is running. Page/resource bytes remain unchanged.

The same action works in an unlocked **LocalCrypt** managed folder. It reads one
archive at a time and retains only metadata snapshots, bounded to 8 MiB in total.
Saves use verified ciphertext staging; page/resource bytes remain unchanged, and
the cloud original is not changed until a separate Push. Inner password-protected
archives use the folder's configured archive password when available. A wrong or
missing password stops batch preparation before any file is written.

Private batch forms have no recovery file. Leaving the form, backgrounding the app,
memory cleanup or replacing/locking credentials closes the batch and clears fields
and suggestions. Reopen the folder to continue. Closing also cancels pending work
before publication; an already published save remains saved. Other windows must be
closed before opening a private batch. Private suggestions are drawn only from the
current batch and are never added to the ordinary imported index.

Encrypted standalone imports still require a native archive writer. Private remote
trees must first have a managed LocalCrypt copy; this action does not recursively
rewrite a live remote tree. Unapplied forms are memory-only.

On iPhone Duo, opening a comic keeps its current page as the right-hand page
when a vertical interior division is available. Closing returns to that same
anchor page. Advancing inside updates the anchor; a layout change alone never
advances it. Manga retains its reading order while keeping the anchor physically
on the right. This applies to imported and Local/LocalCrypt/remote comics.

Partially folding leaves the system-reported fold and its interaction margins
clear between pages. A single page, including wide artwork, fits within the
right-hand region. With a horizontal fold, a single page fits above the fold
while the page controls remain below it. Flat interior layouts retain the right-hand anchor and follow
the page-layout preference. A wide page's selected half survives a layout round
trip back to a narrow viewport. Ordinary zoomed resizing waits until fit size;
a change of fold region can reflow immediately so the page is not left across
the fold.

### iOS edge-to-edge reading

With controls visible, comics use a canvas without an added outer margin. Page
arrows, the slider and page count share one bottom row. On iPad, the title uses
the available navigation-bar width and only shortens when the filename does not
fit between the controls. Pages keep their original proportions when fitted.

When iOS places controls along the side, a decorative extension of the current
page artwork can fill the space behind them. The fitted page and its controls
remain unobstructed. The extension is disabled with Reduce Transparency and
removed when the private reader is concealed or suspended.

Fullscreen comics hide the system status indicators as well as app navigation.
The image canvas uses the full window, including the former status-indicator strip.
On a partially folded Duo, pages fit on either side of the system-reserved fold.
Their available space accounts for asymmetric safe areas and the fold margins. Source aspect ratios and built-in page borders remain unchanged.
Tap the page to restore controls and normal safe areas. Android retains its immersive
system-bar behavior. Ordinary and private comics share this presentation.

## Reading on a TV

Connect AirPlay Screen Mirroring on iPhone or iPad, then open a comic. The TV
shows the current page or spread fitted against black, without reader controls.
Turn pages on the phone or tablet; TV output follows the same two-page spread
or complete wide page, with no added gap between paired pages. A small **Casting to TV** badge stays visible on the
internal screen even in fullscreen reading, above the home indicator. It clears
when you leave the comic, disconnect the display, or privacy protection blocks
output. The phone may remain in
portrait while the TV uses its own landscape display dimensions. Leaving the comic or
backgrounding the app clears the dedicated external picture. After updating from
a version that only mirrored the app, stop Screen Mirroring and reconnect once
so iOS can create the dedicated display session.

Android system casting mirrors the fullscreen reader. If Android exposes the
connected TV as a presentation display, Logistics instead shows a dedicated
picture-only viewer there. Start casting through Android's system controls;
Logistics does not provide a Google Cast device picker or receiver integration.

TV output stays black whenever session-only credentials or retained protected
views create an existing screen-privacy gate, even for a local comic and even
after unlocking. Saved credentials alone do not enable that protection. Close
protected views and clear session-only credentials to release it.

## Returning after sleep

If Android releases reader memory while the device sleeps, the visible imported
comic or EPUB reloads at its saved page or passage when you return. Reading mode
or visible controls are preserved. Closed documents and readers on other screens
stay closed or inactive. Password-protected documents retain their usual unlock
requirements; session-only content is revealed only after its session password.
