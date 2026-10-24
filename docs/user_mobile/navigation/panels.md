# Mobile panels

## Using the mobile panels

Android windows at least 600 dp wide use a compact, icon-only destination rail.
Home, Workspaces, Documents and Chat sit at the top; Settings sits at the bottom.
The outline icons follow the desktop rail, with 48 dp touch targets and accessible
destination names. Long-press an icon for its label. Narrower windows show labeled
bottom navigation. Android and iOS destination icons use the same artwork as
desktop Logistics. High contrast / E Ink adds a black divider down the full
content edge of the rail. Resizing preserves the selected destination.

Home offers **Open file…**, **New document**, five recent files and **See all in
Documents**. Documents lists every open session under **All open** and shows closed Recent entries as compact rows without
text-preview cards. Tap a filename to continue. The **×** button closes an open
session through the existing unsaved-change guard. Card overview is permanently
off and has no Settings switch. Other saved text and Markdown files appear under
**Saved documents**. **Search documents** filters open, recent and saved filenames.
Home's Recent entries share one rounded block, including **See all in Documents**.
Documents uses separate rounded blocks for populated **All open**, **Recent** and **Saved
documents** lists, with inset dividers between rows. Empty sections and unmatched
searches show plain informational text outside the blocks. Home also keeps its
empty Recent message outside the **See all in Documents** action block.
Status appears in one smaller grey line below each filename, such as
**Open · Unsaved · Recovered**, using the system font. Other warnings remain in
that summary. Close buttons stay inside open-document rows.
High contrast adds one black outline per block while preserving the same shape
and spacing as regular appearance.
Source icons and filenames have space inside their row boundaries. Android
High contrast / E Ink retains the same content insets and icon sizes as normal
appearance, including after switching modes. This also applies to shared browser,
reader and speech buttons.
Settings groups feature options under Text & Markdown, Books & Comics, LM Chat
and Workspaces; reader appearance stays in each open reader. Home provides the
Open/New actions; Documents provides **Open Books & Comics library**. Chat has
its own bottom navigation destination.

The library is a searchable list of configured library folders. Tap a folder to
browse its books and comics. Contents/bookmarks and appearance have separate tools, keeping the reading
area clear. An editor's **•••** menu contains less frequent document commands.
Markdown opened from local/provider files offers Preview/Edit without saving the
draft; leaving the view clears the rendered preview and keeps the draft in memory.
Closing or locking private content clears the preview as well as its editor text.

Workspaces starts with a scrollable list of folders. Names have no Local/Remote prefix.
Name-based groups (such as Server → Library → Comics) remain expandable. Workspaces
lists storage entry points and managed copies; browsing a remote does not add its
contents to this tree. Open an entry to browse actual subfolders in its file browser.
Tap a folder row to open its action page. **Browse Local**, **Browse LocalCrypt** or **Browse Remote** opens the file browser for that copy.
Managed copies offer **Pull…** and **Push…**. Folders with a loaded remote offer
Pull to create or associate a copy. Local folders also offer **Delete local
folder…**, with native confirmation; online files are kept. Deletion waits until
transfers finish. **Back** returns to the list. At widths of at
least 640 points/dp, the tree remains on the left and actions appear on the right,
in equal panes centered in the available content. Narrow windows use a separate
action screen. Mapping removal is not offered on this page.
**Settings → rclone / Remote connections…** loads credentials. **Transfers** and
**Refresh** stay above the scrolling list. Transfers opens progress and managed-copy
options; Refresh has its own circular-arrow icon and updates folder discovery.
Returning through the bottom Workspaces tab refreshes available folders and lock
indicators while preserving the selected source and credential filter.

An ordinary local folder can also **Push…** before its first Pull. **Push whole
folder…** infers the remote from the folder name: `Books` goes to `Books:` in the
matching credential package. **Push as subfolder…** lets you select a loaded
remote: local `Comics` beneath `Books` goes to `Books:Comics`. Existing mappings
retain their account and destination. Review and execution use the same exact
mapping; confirmation does not rename the local folder or resolve another target.
New copies use readable folder names without generated ID suffixes.

In **Transfers → Transfer settings…**, choose rename tracking, an optional positive
whole-number bandwidth limit in MB/s, and Push exclusions (one rclone pattern per
line). Defaults match desktop Push filters. Excluded destination files are kept;
Pull does not apply these exclusions. The review captures the options used by
execution, including when you proceed without the full review. Ordinary Local
transfers follow file links. Links inside LocalCrypt remain rejected.

LocalCrypt Push removes only independent generated files named `.DS_Store`,
`Thumbs.db`, `ehthumbs.db` or `ehthumbs_vista.db`, case-insensitively, including
encrypted names. Review shows **Cleanup** for local removals and **Delete** for
resulting remote removals, without changing files. Plain generated files with an
exact raw allowlisted name can be removed directly; encrypted generated files
must authenticate before removal. Corrupted ciphertext blocks Push and is
preserved. Custom exclusions never authorize local cleanup.

Folder rows use one line with an icon/name and a navigation chevron. Tap a file to open it directly. File browser rows
have no **•••** button. Opening a folder does not flash a selection
checkmark. Sort and List/Tiles remain in the Sort controls.
Dividers separate file-browser items; the last item has no divider below it.

Push and Pull scan their comparison without changing destination files. Both ask
for native **OK / Cancel** confirmation before writing. **Proceed without full
review…** is available while scanning or checking a completed review: it stops the
comparison and asks you to confirm with an explicit warning that more replacements
and deletions may occur. Required credential, destination and LocalCrypt integrity
checks still run. Comparison failure or cancellation never starts a transfer by
itself. Cancelling the review keeps destination files unchanged and does not publish
a new-copy mapping. The popup identifies the
source and destination and warns about replacements/deletions. Changing the
connection or mapping while the popup is open invalidates that operation.
A compact transfer strip remains available while writing or reading. The rclone
Sync behaviour and destructive scope are described in the Workspaces section above.

Native colours follow the system appearance, and phone lists use vertical scrolling.
iPhones request the tab-bar presentation; iPads retain the adaptive sidebar. These
local UI changes need a freshly built app; the previously released main.07 does
not contain them. Screen-reader and physical touch/keyboard validation remain
separate from the automated checks.

Local file folders remain browsable during a pull: open Workspaces, choose a readable local folder,
and enter folders or go Up while the transfer continues. Remote engine operations
remain serialized. The transfer status strip opens details and can be dismissed
after completion without closing your current document.

While a pull runs, tapping a local text or Markdown file opens its editor and
keeps edits in that document session. Tapping a local CBZ/ZIP comic or EPUB opens
the library reader; paging and returning to an open text draft keep the pull
running. Opening and browsing use separate local work without replacing the
transfer cancellation handle. LocalCrypt operations that need the cloud engine
remain serialized.

Home’s **Workspaces** opens the same folder list each time. Choosing
**All files → Browse Local** refreshes the local root and clears an old
search filter. Local browsing does not wait for a credential restore or an
unrelated cloud request.

### Light and dark appearance

The app follows your device's light/dark appearance. Mobile uses the Logistics Slate
palette throughout its workspaces: soft off-white/off-black backgrounds, slightly
raised card surfaces, subtle grey outlines and blue accents. Home, document
cards, file tiles, editors, Markdown previews and chat share those colours. Editor text, document-name
fields, labels, selectors, hints and input outlines remain readable in either
mode. Markdown and EPUB pages use matching text/background colours; a reader's
explicit Light/Dark setting still applies only to its pages. Changing Android's
appearance keeps the current app activity and document drafts intact.

Android file rows use flat, normal-case titles with the same size/actions layout
as iOS. Buttons adapt to phone width so row menus and Save/Find/Preview remain
visible; Back and Sort retain their full captions.

Comic reading controls now share the same layout for Local and LocalCrypt:
tap to reveal controls, use Previous/Next or swipe at fit size, and use Fit to
return to the centered page. LocalCrypt bookmarks remain in memory until close;
ordinary library bookmarks retain their saved behavior.

Contents and appearance screens have their own Back step to reading. The main
reader uses a **Back arrow** to close its session and return to the same
folder or originating screen. Android Back does the same, including fullscreen,
after dismissing any open search or chapter panel. Unsaved edits prompt before
closing. Each provider document
owns its request and cancellation; cancelling that document does not cancel a
separate pull. Wait for its operation to finish before closing it.


On iOS, hamburger controls open after you release inside the button, allowing a
scroll that starts on the control to be cancelled by dragging away. Workspace
menus use the native navigation bar's own touch target.

Android overflow menus have slightly rounded corners. **High contrast / E Ink**
adds a black outline around their white background. Folder headers center the
current folder name above a smaller storage description and indicators, with
48 dp parent-folder, search and action buttons beside it.

## Panel layout

Home hides its redundant top navigation title while retaining its bottom tab.
Documents and Workspaces use their existing navigation titles without a second
large heading. Settings starts directly with its grouped controls. Both Home and
the bottom navigation use the desktop Workspaces stack-of-three glyph.
On iOS, Chat measures floating-tab overlap to keep the composer and Send control
above the navigation bar, including while the keyboard is open and drafts grow.


On iPhone, all five bottom-tab labels use their complete names immediately after
launch. Opening each tab is not needed to make its name fit; the startup layout
preserves the selected destination and does not open other workspaces.

## Credential groups, open documents and privacy

Workspaces's Credential selector includes All and the names of imported credential
ZIPs (for example, Personal). All combines known local and remote folder trees.
Session-only imports retain their original password-protected ZIP under device
encryption in private app storage, along with its remote associations. Future
sessions can unlock that ZIP using its password without selecting it again.
Decoded credentials and ZIP passwords stay in memory and Settings autosave never
saves them. Unencrypted ZIPs must be selected again next time. **Forget saved
credentials** removes retained ZIPs and their device key. Previously saved
credentials remain saved until explicitly forgotten.

Documents lists open files below its compact New/Open toolbar. The menu opens immediately using cached shortcuts, then refreshes
available folders in the background. Chat opens on its first tab selection.
On iPhone, plain text actions retain at least a 44-point-wide hit area around
their text or icon, bounded by their own controls. Bordered rows and icon controls
retain their full visible touch targets.

Session-only provider document names and paths stay in memory while unlocked;
password-protected credential packages can also retain encrypted open/recent
references. They disappear from Home and Documents when credentials lock and
can be restored after unlocking. These caches contain no document contents or
unsaved edits. Saved-credential cloud references and ordinary local/imported
files use app-private history. Recent keeps up to ten references. Pulling an
unencrypted managed Local copy makes that copy an ordinary local file, which can
appear in local history independently of the original remote's lock state.


All open lists each opened document using its filename as the resume link, with
a direct × close control beside it. Recent uses compact rows without document
text previews. Use the blue **Clear** button beside **Recent** in Documents to
remove recent links, including encrypted history for currently unlocked
credentials. Open documents and saved files are preserved. Cloud links reopen
through the named remote’s current credentials. This layout is always used; there is no card-overview setting.
On iPhone, tab selection waits for UIKit to finish changing its selected screen
before laying out Documents or Chat, so their content and menus appear on the
first tap.


Chat uses neutral surfaces: a flat conversation drawer, rounded current-thread
highlights, a bottom New chat pill and a rounded message field. Dark mode uses
black and charcoal; light mode uses white and soft grey. On iPhone its conversations menu lives in the
native top-left navigation bar, matching the Documents menu position.


Home's Open file action browses all file formats in Local/available LocalCrypt
folders. Comic ZIP/CBZ archives and EPUBs remain visible alongside text files;
opening them uses their reader, while text and Markdown use the editor. The
format-specific Open actions inside Documents retain their category filters.


Workspaces shows active transfer progress directly below its navigation title,
above Credential. Transfers, Refresh and Add share appear on a single row;
Add share opens the SMB / Mac share connection form. The transfer banner also
shows completion and opens the existing transfer details screen.

On iPhone and Android, open books, comics and documents show a compact transfer
control in the top title bar instead of a banner beneath the document title.
It shows the percentage of known work, or a transfer indicator while totals are
unknown; tap it to open Transfer details. Fullscreen reading hides it with the
other controls. Successful completion clears after five seconds; stopped
transfers remain visible until dismissed from a main-screen banner.


On Android, the app-name title bar is hidden so page content starts higher.
Wide screens place Home at the top of the left navigation rail. Home's
Your workspace heading has only a small top inset. On iOS, Home retains its
native Home navigation title. The header has no About Logistics Mobile
overflow menu; build information is available in Settings → About.


Long file-browser names are shortened visually in the middle when needed, keeping
the beginning and filename ending (including its extension) visible. The complete
name remains available to accessibility, file information and all file actions;
this display setting does not rename or change the file path.


On iPhone, changing file-browser locations now refreshes the native picker before
selecting the new location. Opening a LocalCrypt comic uses that encrypted folder
instead of accidentally falling back to Local files. If a private file cannot be
opened, the reason appears in the file browser instead of only in Connections.


LocalCrypt INI files can now open in the memory-only text editor and save back
to encrypted storage. They use the same 1 MiB limit, encoding/line-ending
preservation and conflict checks as private text/Markdown files. Opening them
never adds their names or content to ordinary history or recovery storage.


LocalCrypt comics use the nearest ancestor `remoteConfig.ini` when an inner
archive requires its configured `[LogisticsZIP] archive_password`. The lookup
reads through encrypted storage and stops at that storage root. An empty nearest
LogisticsZIP section stops inheritance; a manually supplied value takes priority.
Resolved values stay in memory for the reader session and are cleared on close.

On Android and iOS, folders whose names start with `Legacy-` are hidden in Workspaces,
file browsers and library shortcuts by default, including Local, Remote and
LocalCrypt folders. Settings → Workspaces → **Show Legacy** changes visibility
for the current session only and resets to off when the app starts.
**Reload preferences** keeps the current session choice. Files with that
prefix remain visible when their parent folders are visible.

The same **Show Legacy** switch also hides credential/ZIP choices whose
names start with `Legacy` (case-insensitive, no dash required), including retained
ZIP unlock choices. Turning it on reveals these choices immediately. Hiding a
selected credential returns the Workspaces selector to **All**; stored credentials
and their ZIPs are retained.

### LocalCrypt session and screen privacy

See [LocalCrypt on mobile](../../features/rclone/user_mobile/localcrypt.md#localcrypt-session-and-screen-privacy).

### Locked credentials and Workspaces

See [Remote connections on mobile](../../features/rclone/user_mobile/connections.md#locked-credentials-and-workspaces).

### Reader navigation and imported metadata

See [Books and comics on mobile](../../features/books/user_mobile/library.md#reader-navigation-and-imported-metadata).

### Mobile EPUB speech and expanded appearance

See [Books mobile workflows](../../features/books/user_mobile/reading.md#mobile-epub-speech-and-expanded-appearance).

## Focused browsing and setup

In the Local/LocalCrypt file browser, **Parent folder** moves up the folder tree;
the native Back action leaves the current screen. The Open file browser displays
the current folder breadcrumb beside Parent folder. Duplicate browser Back
controls are omitted; Sort and view controls remain secondary to search and files.

Chat shows **Set up chat** until a server and model are configured. Send is
disabled until configuration is available; opening setup does not connect to a
server or discard an unsent draft. User messages retain bubbles; assistant
messages use an open layout. The conversation menu, streaming Stop action and
history remain available.

An empty Books & Comics library offers **Import a book or comic…** and
**Open Workspaces**. An empty search offers **Clear search**. Library search has
its own row so Refresh and Import do not crowd the search field.

On iOS, ordinary screens reserve the measured overlap of the floating tab bar,
including keyboard changes. Chat and immersive readers retain their own chrome
ownership. The local presentation uses larger touch targets and names document
close/action controls for accessibility.

### Compact mobile control icons

Reader Previous/Next page controls use left/right chevrons. Manga reverses their
positions and directions: Next points left and Previous points right. Comic
controls include a page slider between the arrows; drag and release to jump to a
page. The slider follows the comic's reading direction. File-browser history
uses a back chevron; **Parent folder** uses an up arrow, so moving up a directory
remains distinct from leaving a screen. Browser result paging and editor Find
Previous/Next match controls also use chevrons. Reading Contents uses a list icon,
Appearance uses a text-size icon, and editor Find uses a magnifying glass.
Overflow menus use an ellipsis and document close controls use a cross.

These controls have 48-point touch targets and descriptive VoiceOver/TalkBack
names, including the affected filename on row menus and close buttons. Save,
transfer, deletion confirmations, and named return destinations keep text labels.
The icons follow system appearance, including Android's high-contrast setting.

### Current iOS and Android differences

Both platforms share the main file, editor, EPUB/comic, chat, and transfer
workflows. Navigation bars, pickers, menus and installed speech voices use each
platform's native presentation. iPad supports additional app windows; Android
currently keeps one app workspace/window. Android alone offers **High contrast /
E Ink**. Both platforms offer **Show Legacy** to control the visibility of
folders beginning with `legacy-` and credential package names beginning with
`legacy`. This choice lasts only for the current session.

Android protects sensitive windows with its secure-window flag. iOS hides content
for inactive app snapshots and detected recording/mirroring, but cannot prevent
still screenshots. See the developer [parity review](../../development/mobile-ui-refresh.md#control-icons-and-iosandroid-parity-review-2026-10-15)
for the implementation boundaries and verification scope.

### Android fullscreen comics and developer settings

Fullscreen comics reclaim the tablet navigation rail's width and the space from
hidden bars. The page stays centered and keeps its proportions; any remaining
balanced border comes from fitting the page's aspect ratio to the screen.

Comic reading mode hides both Logistics navigation and Android's status/navigation
bars. Tap the comic to restore reading controls; navigating away restores system
bars. An edge swipe can temporarily reveal Android's system bars. Image fitting
still preserves page aspect ratio, so a page need not cover every pixel.

Android **Settings → Developer settings…** opens the system developer options
directly, including Wireless debugging, once developer mode is enabled. This
avoids a separate settings-launcher app. It does not keep wireless debugging
enabled if the tablet's firmware disables it during sleep or a Wi-Fi change.

Android theme and orientation changes keep the privacy listener attached and
refresh the current protection state without recreating document owners.

### Multiple credential packages on Android and iOS

See [Remote connections on mobile](../../features/rclone/user_mobile/connections.md#multiple-credential-packages-on-android-and-ios).
