# Rclone mobile workflows

## Android and iOS prototype

In **Workspaces**, choose a mapped folder’s **••• → Pull** to refresh its
on-device copy or **Push** to update the remote. Both use rclone Sync.
Destination files and empty folders can be replaced or deleted without a backup.
One transfer runs at a time. Existing local copies stay available for browsing.

Tap the sync progress ring on a main tab to reopen details. **Scan → Transfer →
Verify** shows the phase. The endpoint strip shows **From** and **To** paths.
Percentages use known bytes or file counts. Removal counts describe attempts.
Completion appears after verification. **Continue browsing** keeps the job
active. **Stop transfer** asks before cancellation. Completed changes remain
after a failure or stop. See [mobile sync](../../../user_mobile/folder_hub/folder_hub.md#workspaces-and-local--localcrypt-sync).

### Review file changes

Check **New files**, **Updated files**, **Delete from destination** and any
**Local cleanup**. Use search and pages to inspect paths. Choose **Push N
changes** or **Pull N changes** and confirm. A changed comparison needs another
confirmation. **Skip preview and start** begins sync without waiting for the
comparison to finish. Back cancels review before sync starts.

### Mobile folder navigation

Use **••• → Download locally…** on a remote file or folder. Choose **On My Phone / On My Tablet**, an available local copy or an unlocked
LocalCrypt location. Choose the destination folder and name, then **Download here**. Confirm when choosing a
decrypted destination. Existing names are refused. The action downloads only
that selection and creates no recurring mapping. LocalCrypt writes encrypted
names and bytes. Use transfer details to follow or cancel the download.

### Android collection drive

Choose **Settings → Workspaces → File storage…** for both Local and LocalCrypt.
Android 11+ needs All files access for public SD-card storage. Android 7–10 uses
app-owned folders, which Android removes on uninstall or clearing app data.
Migration verifies the new copy and retains the source as a backup. If the
selected drive is missing, collection operations stop. See [mobile storage](../../../user_mobile/settings/settings.md#file-storage).

### Unlock from Home

**Unlock** beside **Your workspace** lets you choose a retained ZIP and enter
its password for this session. **Show Legacy** controls Legacy entries.

### Side-by-side mobile credential packages

Set storage independently per ZIP. See [multiple packages](connections.md#multiple-credential-packages-on-android-and-ios)
and the [mobile package guide](../../../user_mobile/navigation/panels.md#multiple-credential-packages-on-android-and-ios).
Forgetting a package preserves its downloaded files. A replacement ZIP can
have a different name or password. Reopening LocalCrypt requires the original
cipher, while Push/Pull also require the original destination account.

### Mobile Workspaces source tabs

Find online folders under **Cloud → Rclone Remotes**, and managed offline copies
under **Local → Rclone Copies**. Select **All** or a credential package.
Direct SMB shares appear under **Home Server**. SMB imported from a ZIP appears
under its package in Cloud. **Encrypted Copy** identifies LocalCrypt storage.
**Locked** and **Unlocked** describe current access.
