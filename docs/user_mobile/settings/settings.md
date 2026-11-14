# Mobile settings

## Categories and adaptive layout

Tap a category to open its options. Use **Back** to return to the list on a
phone. A wide window shows the list beside the selected category. On iPhone
Duo the panes can follow the fold. The current category stays open when the
window resizes. Preferences save as you change them.

## Features

Use **Settings → Features** to choose the available tools. All supported
features start enabled. Turning one off hides its launchers, related settings
and recent documents. Files, conversations and preferences stay on the device.
Close that feature's documents in every window and finish its active work before
disabling it. **Enable all features** restores the default selection. Built-in
Help stays available.

## Video

On iPhone and iPad, enable **Native AirPlay video** before opening a compatible
local video. See [watching on a TV](../../features/video/user_mobile/controls.md#watching-on-a-tv-with-iphone-or-ipad).

## Document restoration

Under **Settings → App**, **Close saved documents on restart** closes clean
documents and keeps recovery drafts. With **Restore last document** also
enabled, the last active document remains open.

## Screen privacy and platform limits

Protected sessions lock when interrupted or sent to the background. Android
uses its secure-window protection. iOS shields protected content during
app-switcher and background transitions and detected screen recording or
mirroring. iOS still allows screenshots of visible content. Ordinary local
files and readable exports stay readable after credentials lock.

## Appearance and E Ink status

Use **Settings → Appearance → Accent color** to preview Hue and Saturation.
Release the slider to save, or choose **Reset to Default Accent Color**.
**Seasonal snow** runs December 15 through January 2. System high contrast and
Android E Ink suppress it.

### Interface size on phones and tablets

Use Android's system **Display size** for the interface and **Font size** for
text. On BOOX, adjust the device's per-app DPI setting and reopen Logistics.
Document font size is separate under **Markdown**, **Text** or **EPUB**.

### Contrast

On Android, enable **Appearance → High contrast / E Ink** for black-on-white
controls, stronger outlines and reduced animation. It also applies to open
HTML views. Images and comic pages keep their colors. Turn it off to return to
the system appearance.

## Settings and build information

Use **Books & Comics → Comic & PDF magnifier zoom** or the magnifier's **−**
and **+**. Both save the same setting, from 150% to 300%, with 190% as default.
The category and setting reflect which readers are enabled.

### Trusted Wi-Fi session resume

Open **Privacy & Security → Skip session password on trusted Wi-Fi** and add
an exact network name in **Trusted Wi-Fi networks…**. **Add current network**
requires precise foreground location access. Use **Add network name** to type
the SSID instead.

Returning from sleep or another app on a listed network can skip the repeat
password prompt for an already-unlocked session-only package. An outstanding
prompt, manual lock or app restart still requires the password. Unavailable
network information keeps the prompt. Duplicate SSIDs are possible, so use
this setting only where that convenience is appropriate.

## Preferences and storage

Use **Reset → Clear cached documents** to review legacy imports. **Clear
redundant copies…** removes only verified duplicates and their import reading
records. It keeps originals, unsaved drafts, changed copies and copies whose
originals cannot be verified.

### File storage

Under **Workspaces → Local**, **On My Phone** or **On My Tablet** holds
ordinary files and incoming shares. **Rclone Copies** holds managed copies.

- **iPhone and iPad.** In Apple's Files app, open **On My iPhone/iPad →
  Logisticks**. Ordinary files sit in this folder and managed readable copies
  in **Rclone Copies**. Finder and Apple Devices expose the same files. Keep a
  separate backup because the shared root is excluded from device backup.
  Encrypted copies and credentials stay in private app storage. If migration
  reports a conflict, resolve it before reopening Logistics.
- **Android.** Open **Settings → Workspaces → File storage…** to review exact
  paths, change drives or remove old copies. Android 11 and newer can use
  shared-drive folders after granting the requested access. Android 7–10 use
  app-owned folders, which are removed by uninstall or app data reset.

| Action | What happens |
| --- | --- |
| **Copy and switch** | Verify a copy of all three collections before switching. Original files stay at the old location. Conflicts stop the copy. |
| **Use these files** | Reconnect an existing collection without copying or merging. Check that it is the copy you want, since this does not verify file contents. |
| **Start empty and switch** | Select empty collection folders. The old location and private app data stay in place. |
| **Delete files…** | Permanently remove the displayed collections at an inactive location. The active location is protected. |

Finish transfers and close provider readers before switching. Reopen Logistics
after a successful switch. If a selected card is missing, reinsert it or
restore permission. LocalCrypt still needs its matching credentials.

## Erase all app data

Use **Clear all saved positions…** or **Clear all recent files…** under **Reset**
for those individual lists. To reset the entire app, finish active work, close
other Logistics windows, export anything you need, and confirm **Erase all app
data…** by typing **ERASE**. This permanently deletes private app data,
credentials, drafts and app-owned storage. On iOS it also deletes the whole
**On My iPhone/iPad → Logisticks** folder.

Public Android shared-drive collections outside app-owned storage and files on
remote servers remain. Reset removes their saved mappings and credentials.
To reopen retained LocalCrypt files, keep the original credential ZIPs and
passwords. Android closes the app and clears permissions. On iOS, fully close
Logistics from the app switcher and reopen to complete **Erase on next launch…**.
If Keychain access blocks erasure, unlock the device and reopen.

## About

Open **Settings → About** or **Help → About** for the installed version and
source information. **Open-source licenses** supports search and works offline.

## Mobile documentation

Open **Settings → Help → Mobile documentation**. Tap a folder title to open its
landing page and its disclosure button to expand the list. On Android,
**Help → More → Android Developer Settings…** opens system developer options.

## Speech while locked

Use the speaker in a reader or Help to start read-aloud. Choose a voice in
**Settings → Read aloud → Read-aloud voice**. Load installed voices for offline
options. A missing saved voice falls back to the system offline voice.

Started Markdown and EPUB speech can continue under the lock-screen media
controls. Private readers display **Read aloud** there. Document passages stay
out of media metadata. **Privacy & Security** offers separate, default-off
settings for **Playlist speech while locked** and **Session-only speech while
locked**. Protected speech can finish prepared notes while locked. Unlock to
read the next protected note. Closing the document or replacing credentials
stops its playback.

### Delete playlists

Use **Reset → Delete a playlist**, choose it and confirm. **Clear locked
playlists** removes unreadable encrypted playlist records. Both keep source
notes.

## Audio playback

Use **Privacy & Security → Protected audio outputs** to manage approved
Bluetooth devices. See [audio playback](audio-playback.md).
