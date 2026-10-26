# Mobile settings

## Categories and adaptive layout

Settings opens a category list: **App**, **Features**, **Read aloud**, **Markdown**, **Text**,
**EPUB**, **Books & Comics**, **LM Chat**, **Workspaces**, **Help**, and **About**.
Both platforms include **Appearance** for Seasonal snow; Android also offers
High contrast / E Ink there. On a phone, tap
one category to see its options and use Back to return to the list.
Categories and related options share rounded groups with inset dividers, like
system Settings. Category icons and trailing chevrons identify pages you can
open; immediate commands use the accent color. Descriptions and status text use
gray in light and dark mode. Switches and pickers retain their native controls.
Android High contrast / E Ink uses rounded outlined groups, black text, and a
solid selected-category highlight in the wide layout.
Category icons keep clearance from the group outline. On iOS, long category
titles leave a separate space for the trailing chevron.

With at least 640 points/dp of usable width, Settings shows categories on the
left and the selected category's options on the right. This applies to Android
and iOS tablets, wide app windows, and an unfolded iPhone Duo in landscape.
Each category loads only when you open it, then retains its controls for later
visits. The wide layout starts with an empty options pane until you select a
category; opening Settings does not load the default App page.
A partially folded Duo with a vertical seam aligns the two panes to that seam.
Labels, descriptions and action buttons wrap to the available pane width; long
switch labels leave room for the full switch. Each pane scrolls
independently. Rotating or resizing retains the selected category and its controls. A nested
page stays open during a resize; Back returns to its category in the new layout.
Preferences still save immediately, and each window keeps its own category
selection.

## Features

Open **Settings → Features** to turn Text Editor, Notebooks, Books & Comics,
PDF Reader, Image Tools, LM Chat, and rclone on or off. Names and the combined
Books & Comics switch match desktop; each switch controls its feature group.
All current features are on by default on iOS and Android, including when upgrading
an existing installation. **Enable all features** restores that selection.

Choices save immediately on this device and survive restarting the app. Turning
a feature off hides its launchers, creation types, recent documents and related
settings. Opening a file for a disabled feature offers an **Enable** action.
The Chat tab stays available with an enable screen when LM Chat is off.
Files, saved settings and conversations are kept. Enabling the feature brings
its documents back into the lists. Disabling rclone leaves ordinary
local browsing, document creation and editing available.

Close a feature's open documents before disabling it, including documents in
other app windows. A running chat or storage operation must finish first. The
switch stays on and explains the required action; it never discards unsaved work.
These switches select features in the installed app; they do not uninstall code
or change desktop feature preferences. Image Tools stays enabled by default
on Android too; Burst camera is available only on supported devices.

**Settings → Help → Mobile documentation** always opens the built-in Markdown
guide, even with every feature off. Its pages, links, search and history stay
available independently of Text Editor.

## Appearance and E Ink status

**Seasonal snow** is on by default and saves immediately on this device.
Decorative snow falls from December 15 through January 2, inclusive, each year,
using the local date. It lets touches pass through. System high contrast and
Android High contrast / E Ink suppress snow without changing the saved choice.

### Interface size on phones and tablets

Workspaces uses the same approximately 17-point/sp title size and 48-point/dp row targets on
phones and tablets. Source tabs and credential pickers use 16-point/sp text.
Native file lists also use 48-unit rows, with 17-point/sp primary text on Android
and the native iOS body font. Larger windows provide more room for content and
panes rather than reducing these sizes. These are logical units, not screen pixels;
Android's reported display density still determines their physical size.

If the entire interface looks small on BOOX, increase Logistics' per-app DPI in
BOOX's app optimization settings, then fully close and reopen Logistics. Vendor
labels and available controls vary by model and firmware. A “universal DPI” choice
does not guarantee the same physical scale as an iPhone. Start with a modest
increase (for example, about 15%), compare a few rows and buttons, then adjust to
comfort. Increasing DPI makes controls larger and leaves less room for content;
it can also change when the app switches between a rail and bottom navigation.
Logistics does not change the device's density or override BOOX optimization.

On other Android tablets, use the system **Display size** control if the whole
interface is small, or **Font size** for text. Android native text follows system
font scaling; fixed-height rows have not been validated at every accessibility
size. The document font controls below affect reading content separately from
navigation. The E Ink switch changes contrast, not interface scale.

### Contrast

Android normally follows the device's light/dark mode. This remains the default.
To opt in, open **Settings → Appearance → High contrast / E Ink**. The Android-only switch saves
immediately on this device and persists after restarting the app.

While enabled, the app uses black text on white and adds black outlines while
keeping the same layout, sizes and corner shapes as normal appearance.
Interactive Workspaces folder rows have a black rounded outline enclosing their icon, title and actions; group headings keep
their plain presentation. Android file-browser lists have a thin separator
between entries in normal and high-contrast modes, inset from the filename's
first letter to just beyond the three-dot action. High contrast adds one black
outline around the list, like a Settings group. Android folder rows omit the
disclosure arrow; tap the folder name to browse or the three dots for actions.
Colors follow the current appearance. Wide workspace/browser panes have a
16-unit gutter on Android and iOS; compact layouts use the full available width.
The selected destination (Home, Workspaces, Documents, Chat or
Settings) has a white icon inside a solid black rounded indicator on both the bottom bar
and the left navigation rail. The icon's transparent areas remain transparent, and unselected
icons and labels stay black on white. Rotating into a sidebar applies this
treatment immediately, without toggling the preference again.
Button elevation and navigation ripple effects are removed; HTML text views disable CSS animation and
transitions. Markdown previews, chat and EPUB text receive the same high-contrast
treatment, including already-open HTML views. Images and comic pixels are not
recolored, and no source files or reader theme preferences are changed.

The mode forces this app's light appearance even when Android uses dark mode.
Turn it off to restore the normal system-following app palette and the original
reader/HTML styling. Existing documents, drafts and transfers remain in place.

**Settings → Markdown**, **Text**, and **EPUB** provide separate font sizes (12–32).
Markdown and EPUB also offer **Justify text** to align paragraphs and lists to
both edges. Each switch defaults to off and saves independently on this device.
Changes reflow open rich readers and formatted Markdown without changing the file;
source editing, headings, code blocks and tables keep their existing alignment.
In an open EPUB or comic, **••• → Appearance…** offers reader typography, margins,
width, theme and comic layout. The high-contrast override takes precedence over
reader text colors while enabled; turning it off reveals the chosen theme again.

This is an app appearance mode designed to be useful on E Ink devices, including
BOOX. It does not select BOOX waveforms, force hardware refreshes, remove physical
ghosting or configure the stylus. Those vendor-specific controls are not part of
Logistics. Android emulator checks cover toggling, process restarts, live views
and restoring the normal palette; physical BOOX behavior remains unverified.

## Settings and build information

**Settings → Books & Comics → Comic & PDF magnifier zoom** controls the shared
hold-to-magnify bubble: 150%, 170%, 190%, 210%, 230%, or 250% (default 190%).
While holding a fullscreen comic or PDF with one finger, tap **−/+** just outside the bubble’s upper
left/right corners with another finger to change the same setting. Changes save
immediately, update open readers and app windows, and survive restarting.

**Settings → Books & Comics → Saved books & comics…** lists every retained
library import, including copies no longer open or in Recent. It shows the count,
combined archive/reading-record size and each import's size. Incomplete or unreadable
records appear under their internal identifier where possible. Local/LocalCrypt
folders and remote previews held only in RAM are separate from this inventory.
On iOS these imports live in private app storage and do not appear in Files.
The inventory identifies these as private reading copies. Older imports may lack
an original source path; their reader offers **Show cached copy in folder**.

**Close** in All open keeps the saved file and its progress. To reclaim
space, use **Delete local copy…**, or **Delete all local copies…** to clear the
listed saved books and comics with one confirmation. These actions
close the affected readers and remove their imported archives, reading progress,
bookmarks and Recent entries; the original source or cloud file is unchanged. Finish reader
or import operations and close other app windows before deleting a copy.

On iPhone and iPad, choosing a dropdown option closes its picker immediately.

Settings switches use one compact row with the label and on/off switch.
Explanations appear as muted, wrapping comments immediately below the option's
rounded group, visible without opening a dialog. This applies across all settings
categories, including
**Restore last document**, **Close saved documents on restart** and,
on Android and iOS, **Show Legacy**. Preferences save automatically when changed.
**Show Legacy** applies immediately for the current session only and resets to off
when the app starts. Reloading preferences keeps the current session choice.

The **About** category in Settings shows muted build information: the app version,
short source revision and commit time when available, plus the platform and
packaged source snapshot. Local modified builds are identified. This information
is available offline; the About heading keeps its normal appearance.

## Preferences and storage

The launcher icon includes light and dark artwork. On supported iOS versions it
also includes a monochrome variant for tinted icons; Android 13+ launchers can use
the monochrome artwork for themed icons. The system or launcher controls this
appearance, separately from the app's system-following surfaces and reader themes.

### Local / LocalCrypt location

Files shared from other apps appear in **Received Files** in Workspaces and
**Browse All Files**. On iOS, Files shows **Logisticks/Received Files** beside
**Local**. Android keeps Received Files alongside the selected Local and LocalCrypt
collections. Legacy Inbox contents are copied without overwriting existing files;
see [receiving files](../documents/workflows.md#receive-files-from-another-app).

On iPhone and iPad, **Local lives in `Logisticks/Local`** in Apple's
Files app under **On My iPhone/iPad**. Launch the app once to create the `Local`
folder, even before pulling any remotes. The app recreates it on later launches
if it was removed. In Finder, choose your device → **Files → Logisticks**;
on Windows use Apple Devices or iTunes File Sharing, then open `Local`.
Pulled ordinary remotes and files added inside `Local` appear in Workspaces.
Adding a folder does not create a remote mapping. Computer file sharing can also
copy out or delete these files. Files already beside `Local` are left in place;
this layout change does not move existing shared files.

The existing upgrade preparation keeps private application data separate.
Credentials, settings, saved editor/library documents and both kinds of encrypted
offline storage are relocated into private Application Support storage. LocalCrypt
stays in its current private location, encrypted and not exposed through file sharing.
The existing private-data migration uses moves
within the app container, retains file contents, and resumes after interruption.
Conflicting destination names stop migration without overwriting either copy;
resolve the conflict and reopen the app to retry.

Logistics excludes the shared root from iCloud and computer device backups and
reapplies that exclusion on launch. Keep another copy of important Local files;
these files do not sync through iCloud Drive. File sharing becomes enabled when
the update is installed, so the previous storage layout can be visible to a
trusted computer until the updated app has been opened and migration completes.

On Android, open **Settings → Workspaces → Local / LocalCrypt location…**.
One setting controls Local, LocalCrypt and Received Files. Selecting a drive in the list only
inspects it; it does not switch storage. The page shows the current location,
whether the selected location is in use, and the exact Local, LocalCrypt and Received Files
paths and whether they are empty or contain files.

On Android 11 and newer, the shared-drive folders are `<drive>/Logistics/Local`,
`<drive>/Logistics/LocalCrypt` and `<drive>/Logistics/Received Files`. Internal copies use the app's private
`LocalFiles`, `LocalCryptFolders` and `Received Files`. Enable **All files access** using
**Allow SD card / shared storage access…** before accessing shared drives.

On Android 7–10 (including Android 9 on a Galaxy S8+), drive choices use
Logistics' app-owned device-storage or SD-card directory. No storage permission
is required. On an SD card the collections are normally under
`<card>/Android/data/io.github.ispaure.logisticsmobile/files/Logistics/Local`
with `LocalCrypt` and `Received Files` beside it; the page shows the exact paths. These versions cannot
use arbitrary SD-card folders through this setting. Android deletes the app-owned
folders when you uninstall Logistics or clear its app data, including through
the app's Reset action. Keep a separate backup before doing so.

| Action | Result | Files kept |
| --- | --- | --- |
| **Copy current files here, then use them…** | Copies and verifies all three folders, then selects the destination. Different destination files stop the operation; nothing is merged or overwritten. | Original files remain at the previous location. Matching copied files can be reused after an interrupted copy. |
| **Use existing files here — no copy…** | Selects the collection folders already at this location. This is what the old “Recover” button meant. It does not restore newer changes, merge folders or copy the current collection. | Current files stay at their old location. The selected files may be an older backup. Original credentials are still needed for LocalCrypt. |
| **Start empty here — keep old files…** | Creates/selects empty collection folders without copying. Refuses a location containing files. Works even if the previously selected card is unavailable. | Current files stay at their old location. Private documents, credentials and metadata remain. |
| **Erase collection files at this location…** | Permanently deletes only the displayed Local, LocalCrypt and Received Files folders, their contents, interrupted `.storage-copy-*` folders and the location marker. Does not select another location. | Unrelated folders, private documents, credentials, settings and metadata remain. Disabled/refused for the collection currently in use. |

For retained shared-drive folders on Android 11 and newer, after reinstalling or
resetting the app, select the SD card and choose **Use
existing files here — no copy…** to reconnect retained collections. This checks
the collection folder paths and saves the location without scanning subfolders,
reading file contents or calculating checksums. It is not an integrity check;
an unreadable file can still report an error when opened later.

“Inactive” previously meant **not currently selected by Logistics**, not empty,
obsolete or safe to delete. Example: after copying internal collections to an SD
card, the internal copy is retained but no longer selected. To return to that
copy without the SD card, choose **App internal storage → Use existing files
here — no copy…**. Later SD-card changes will not be present in the older copy.
To remove that older copy permanently, first verify that the correct SD-card
collection is in use, then select internal storage and erase its collection
folders. Never erase your only remaining copy.

Finish transfers and close provider readers before switching. Every switch
requires confirmation and closes the Android app on success; reopen it to use
the new location. The erase action stays in the current app. All four actions
preserve private credentials and app metadata; **Settings → Reset** is separate.

Credentials, transfer mappings, preferences, imported standalone books, text
imports and recovery drafts remain in internal app storage. Local is readable
storage; other apps with access to the card can read it. LocalCrypt preserves
its encrypted filenames and bytes and still requires the matching credentials.
Only public shared-drive collections outside app-owned storage survive app uninstall; private credentials and
transfer associations do not. Reinserting the card alone cannot recover those.

If the card is missing or permission is revoked, local collection operations
stop; Logistics does not silently download into internal storage. Reinsert the
same card or restore permission. iOS uses its file-sharing Local folder; drive selection is Android-only.

Developers can update Logistics on a paired iPhone over Wi-Fi using the
[local deployment workflow](../../development/mobile-launchers.md#build-and-deploy-to-a-paired-iphone-over-wi-fi).
Its launcher builds, installs in place and opens the app while retaining its
bundle and signing identity. Keep the iPhone unlocked on the same Wi-Fi as the
Mac. Do not uninstall Logistics to fix deployment errors: uninstalling removes
its private documents and preferences.

INI is a usable format on both mobile platforms. Bundled defaults must remain
read-only, while personal overrides belong in the app's private persistent data
directory. The shared settings API accepts explicit default/override paths and
rejects automatic desktop settings paths on mobile. This host uses immutable
in-code defaults and an app-private `preferences.ini`. **Settings** controls the
editor/preview font size and whether the last selected document is restored.
Reads do not create the INI; saving does. Invalid files are preserved and defaults
are used; saving refuses to overwrite them. Reload after repairing or moving such
a file. Concurrent external edits also require reload. Home remains the launch
screen; restoring a document makes it ready under Documents.

Desktop preferences cannot simply be copied wholesale: filesystem paths,
external executable locations and desktop-only options need validation or
platform-specific replacements. Document-provider access is a permission-bearing
platform handle rather than an ordinary path stored in an INI. Preferences
migration and general app-data backup remain separate work.

## Erase all app data

Open **Settings → Reset → Erase all app data…**. Read the scope, export anything
you need, type **ERASE**, then confirm. Finish transfers/generation and close
other Logistics windows first. This is irreversible.

This deletes private documents and unsaved drafts, imported books, chat,
credentials and their device keys, settings/configuration, transfer mappings,
reading progress, metadata, thumbnails and caches. On Android it also deletes
internal Local and LocalCrypt files and app-owned SD-card storage (used on
Android 7–10). On iOS it deletes **all files under On My
iPhone/iPad → Logisticks**, including Local and files added using Files.

Public SD/shared-drive `Logistics` folders outside app-owned storage and files on cloud/SMB servers are kept.
Their app-side mappings and saved credentials are removed. To use retained
LocalCrypt data again, you need the original credential ZIPs and passwords;
resetting the app cannot recreate encryption credentials. To erase SD contents,
use the separately scoped collection erase action before resetting the app.

Android uses the system's Clear app data operation, closes the app, and clears
runtime permissions/provider grants. Reopen it and grant access again as needed.
On iOS the button says **Erase on next launch…**: after confirmation the app
locks on a reset notice. Fully close it in the app switcher and reopen it.
The notice explains that erasure is still pending and gives the close/reopen
steps. Returning to the Home Screen alone does not complete the reset, and
the erase control remains disabled once the request is scheduled.
Erasure runs before migration, document restoration or services load. A durable
request retries interrupted erasure on the next launch; a Keychain error stops
before deleting credential records. Unlock the device and reopen to retry.

## Mobile documentation

In the documentation sidebar, a folder with a same-named Markdown landing page
uses a combined folder/document icon. Tap its title to open that page; use the
separate disclosure button to expand or collapse its children. Ordinary folders
and standalone pages retain their folder and document icons.

## Speech while locked

In **Settings → Help → Mobile documentation**, tap the speaker beside Back, Forward
and Up, then Play to read the current page or selected text aloud. Changing
documentation pages stops playback. Playback controls float above the page
without changing its layout. Speed and 15-second skip controls are available in
Markdown files and EPUB readers.

Choose the voice in **Settings → Read aloud → Read-aloud voice**. Tap **Load
installed voices** to list offline voices, then select one; the choice saves on
this device. **System default** uses the system offline voice. If a saved voice
is no longer available, playback falls back to the system offline voice. Voice
selection is not shown when opening playback controls in a document.

Started Markdown and EPUB read-aloud can continue with the screen locked. iOS
shows Now Playing controls on the lock screen and in Control Center; Android
shows media controls in the lock screen and notification shade. Use Play/Pause
and the backward/forward 15-second controls. Skips remain approximate, using
word count and playback speed. Stop or close the document to remove its controls.
Ordinary documents may show their filename; private readers use **Read aloud**.
Document passages never appear in lock-screen or notification metadata. The subtitle
shows the timer when enabled, otherwise the app name.

**Session-only speech while locked** defaults to off. With it off, speech from
session-only credentials stops and its queued text clears when the app locks or
goes into the background. Turn the setting on to permit already-started speech
and system controls while locked; the choice is remembered on this device.
Credentials still lock normally, and this setting does not permit new file reads
or restore speech after an app restart. Clearing/replacing credentials or closing
the document stops playback even with the setting enabled.
