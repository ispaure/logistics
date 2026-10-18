# Mobile settings

## Android appearance and E Ink status

Android normally follows the device's light/dark mode. This remains the default.
To opt in, open **Settings → High contrast / E Ink**. The Android-only switch saves
immediately on this device and persists after restarting the app.

While enabled, the app uses black text on white, black outlines and simpler
square controls. Navigation keeps a visible selected state. Button elevation and
navigation ripple effects are removed; HTML text views disable CSS animation and
transitions. Markdown previews, chat and EPUB text receive the same high-contrast
treatment, including already-open HTML views. Images and comic pixels are not
recolored, and no source files or reader theme preferences are changed.

The mode forces this app's light appearance even when Android uses dark mode.
Turn it off to restore the normal system-following app palette and the original
reader/HTML styling. Existing documents, drafts and transfers remain in place.

**Settings → Text & Markdown** also provides editor/preview font size (12–32).
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
While holding a fullscreen comic or PDF, tap the bubble’s top-left **−** or
top-right **+** with another finger to change the same setting. Changes save
immediately, update open readers and app windows, and survive restarting.

**Settings → Books & Comics → Saved books & comics…** lists every retained
library import, including copies no longer open or in Recent. It shows the count,
combined archive/reading-record size and each import's size. Incomplete or unreadable
records appear under their internal identifier where possible. Local/LocalCrypt
folders and remote previews held only in RAM are separate from this inventory.
On iOS these imports live in private app storage and do not appear in Files.
Older import records do not identify their original source; the inventory says
so rather than guessing whether a copy originally came from cloud storage.

**Close** in Open documents keeps the saved file and its progress. To reclaim
space, use **Delete local copy…**, or **Delete all local copies…** to clear the
listed saved books and comics with one confirmation. These actions
close the affected readers and remove their imported archives, reading progress,
bookmarks and Recent entries; the original source or cloud file is unchanged. Finish reader
or import operations and close other app windows before deleting a copy.

On iPhone and iPad, choosing a dropdown option closes its picker immediately.

Settings switches use one compact row: label, **ⓘ** help, then the on/off switch.
Tap **ⓘ** for an explanation without changing the setting. This includes
**Document card overview**, **Restore last document**, **Close saved documents on restart** and,
on Android and iOS, **Show Legacy**. Preferences save automatically when changed.
**Show Legacy** applies immediately for the current session only and resets to off
when the app starts. Reloading preferences keeps the current session choice.

**About** at the bottom of Settings shows muted build information: the app version,
short source revision and commit time when available, plus the platform and
packaged source snapshot. Local modified builds are identified. This information
is available offline; the About heading keeps its normal appearance.

## Preferences and storage

The launcher icon includes light and dark artwork. On supported iOS versions it
also includes a monochrome variant for tinted icons; Android 13+ launchers can use
the monochrome artwork for themed icons. The system or launcher controls this
appearance, separately from the app's system-following surfaces and reader themes.

### Local / LocalCrypt location

On iPhone and iPad, **Local lives in `Logisticks/Local`** in Apple's
Files app under **On My iPhone/iPad**. Launch the app once to create the `Local`
folder, even before pulling any remotes. The app recreates it on later launches
if it was removed. In Finder, choose your device → **Files → Logisticks**;
on Windows use Apple Devices or iTunes File Sharing, then open `Local`.
Pulled ordinary remotes and files added inside `Local` appear in Folder Hub.
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

On Android, open **Settings → Folder Hub → Local / LocalCrypt location…**.
One drive setting controls both collections. Select the SD card to use:

```text
<SD card>/Logistics/Local
<SD card>/Logistics/LocalCrypt
```

Tap **Allow SD card / shared storage access…**, enable Android's **All files
access** for Logistics, and return to the app. Then choose **Copy collections
and use this drive…**. Close open readers and provider documents first and wait
for transfers to finish. Logistics copies existing managed Local and LocalCrypt
folders, checks file contents, and saves the new location only after verification.
Different files already in the destination stop the switch without overwriting;
when there are no existing source files, collections on the selected drive may
be adopted. The app closes after a successful switch; reopen it.

The original copies remain as a recovery backup and continue to occupy space.
Only the selected location is used afterward. Switching back refuses to replace a
backup whose files differ from the current collection. Interrupted migration can
leave copied destination folders, but the original selection remains active until
both collections pass verification. Repeating the switch reuses matching copies.

Credentials, transfer mappings, preferences, imported standalone books, text
imports and recovery drafts remain in internal app storage. Local is readable
storage; other apps with access to the card can read it. LocalCrypt preserves
its encrypted filenames and bytes and still requires the matching credentials.
The public collections survive app uninstall, but private credentials and
transfer associations do not. Reinserting the card alone cannot recover those.

If the card is missing or permission is revoked, local collection operations
stop; Logistics does not silently download into internal storage. Reinsert the
same card or restore permission. iOS keeps its existing private storage location.

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
migration and general app-data backup/reset behavior remain separate work.

## Speech while locked

In **Settings → Mobile documentation**, tap the speaker beside Back, Forward
and Up, then Play to read the current page or selected text aloud. Changing
documentation pages stops playback. The same voice, speed and desktop-style
15-second skip controls are available in Markdown files and EPUB readers.

Started Markdown and EPUB read-aloud can continue with the screen locked. iOS
shows Now Playing controls on the lock screen and in Control Center; Android
shows media controls in the lock screen and notification shade. Use Play/Pause
and the backward/forward 15-second controls. Skips remain approximate, using
word count and playback speed. Stop or close the document to remove its controls.
Only a generic **Read aloud** title is shown, without document or credential names.

**Session-only speech while locked** defaults to off. With it off, speech from
session-only credentials stops and its queued text clears when the app locks or
goes into the background. Turn the setting on to permit already-started speech
and system controls while locked; the choice is remembered on this device.
Credentials still lock normally, and this setting does not permit new file reads
or restore speech after an app restart. Clearing/replacing credentials or closing
the document stops playback even with the setting enabled.
