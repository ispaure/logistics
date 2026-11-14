# Connect and transfer remote folders

Use **Workspaces → Cloud → Rclone Remotes** to browse online folders. Use
**Local → Rclone Copies** to open downloaded folders. Copies can be readable
Local files or encrypted LocalCrypt files. **Locked** and **Unlocked** describe
whether the matching credentials are available.

## Set up credentials

1. Open **Settings → rclone → Credential packages** or choose **+ rclone** in
   Workspaces. Choose **Import credential ZIP…** and select your package.
   Import keeps the original. If a different package already uses the same
   name, rename the incoming ZIP.
2. Enter its password and choose **Unlock…**. Choose an access mode.
3. Return to **Workspaces → Cloud** or **Home Server**, and choose the credential
   and remote. Unlocking only loads credentials. Opening the remote is the
   first network check.

**Session-Only** unlocks the package in memory. The ZIP location and remote
names can be remembered for the next unlock. **Persistent credential storage**
writes a reusable rclone configuration, such as ~/.config/rclone/Personal.conf.
That file contains credentials outside the ZIP's password protection. Mobile
uses a separate device-protected vault. Detached FUSE mounts require saved
configurations.

Credential ZIPs can be up to 1 MiB. Each TXT entry must be encrypted with the
package password and start with the remote's rclone section header. A crypt
remote also needs its backing remote. **Refresh list** finds packages added
outside the app. Make a cloud-hosted ZIP available offline before importing it
without a network connection.

## Transfer files

From a selected workspace, choose **Pull** to download or **Push…** to upload.
Check the source, destination and listed changes. For a new session-only crypt
pull, **Encrypted Copy** keeps encrypted filenames and bytes on disk.
**Regular Local copy** produces readable files that remain accessible after
credentials lock. An existing copy keeps its saved location and storage type.

Follow progress and the final outcome in **Workspace actions**. A transfer can
retry after a recoverable error. **Cancel** stops further work and leaves changes
already written. Closing Logistics cancels integrated transfers and waits for
them to stop.

| Location | Default path |
| --- | --- |
| Local copy | ~/Server/Local/<folder> |
| Optional mount | ~/Server/NetworkMount/<config-id>/<remote> |

## Remove a loaded config

Open **Manage credentials…** for the selected package. **Forget Credentials**
removes its saved and session access and remembered remotes while keeping the
ZIP and local files. **Lock All Session Credentials** retires session access.
**Clear All Saved Configs** also affects saved configurations outside Logistics
in the configured rclone directory. Use it only to clear that whole directory's
rclone configs.

## More help

See [Using Logistics](../../../user/user.md) for navigation,
[Configuration](../../../user/configuration.md) for storage locations, and
[FUSE](../../fuse/user/user.md) for mounts.

## Choose a rclone download version

Use the platform configuration in **Settings → rclone** to choose the required
version. Before a command that needs a missing or mismatched executable,
Logistics offers a verified download for the configured platform. Cancelling
that download stops the command. See [rclone download versions](download-versions.md)
for the platform settings.

## Choose the sync scope

**Sync makes the destination match the selected source.** It can replace
existing files and delete destination files missing from the source.
Check the folder and direction in the review. A changed review requires fresh
confirmation. Use **Proceed without full review…** only when you accept the
risk of unseen replacements and deletions.

Manage exclusions and bandwidth before reviewing. A Push exclusion keeps
matching destination files. Start another review if you change the scope or
options. Empty source folders are retained where the destination supports
directories. The sync does not create a backup.

## Browse remote files directly

Choose **File Browser → File → Open Remote…**, or select the remote in
Workspaces. Search filters the current folder. Previews are read-only and stay
in memory. Text, Markdown and INI have a 1 MiB limit. PNG, JPEG and WebP have a
16 MiB limit. EPUB and CBZ/ZIP use bounded reads. Use an offline copy for an
unsupported format or a file above the limit.

A comic's ZIP password is separate from the remote password. Logistics checks
the nearest remoteConfig.ini with a LogisticsZIP section up to the remote root.
An empty section stops inheritance. Enter the archive password when prompted.

For an ordinary local copy, right-click a file or folder and choose **Download
locally…**. Select the destination folder and a new item name. An encrypted
remote asks you to confirm that the new copy will be readable after locking.
Use **Pull** for a managed copy. Opening a preview alone saves no local copy.

If authorization fails, renew the underlying account, replace the ZIP and
reopen the remote. Include the backing remote for a crypt connection.

## Android and iOS prototype

See [rclone mobile workflows](../user_mobile/workflows.md).

## Read and edit a LocalCrypt copy on desktop

Open an encrypted copy under **Workspaces → Local → Rclone Copies** and unlock
with the matching credential package. A private File Browser tab shows decoded
names. Open the file with a supported Logistics reader or editor. Save an edit
back to the copy and run a separate reviewed Push when you want it online.
Use the destination picker deliberately when saving elsewhere. A readable
export is an ordinary file.

### Push checks and generated junk

Review LocalCrypt Push before writing. It can list cleanup of generated
metadata files and the related remote deletions. Custom exclusions do not
authorize local cleanup. If corrupted ciphertext blocks Push, preserve the
file and resolve the problem before retrying.

### Session privacy

Private thumbnails, preview data and unlocked credentials stay in memory.
Locking or replacing credentials retires the open private views. Save or
discard private drafts before locking. Keeping an encrypted copy on disk
still requires the matching credentials to reopen it.

### Mobile folder navigation

See [Workspaces on mobile](../../../user_mobile/folder_hub/folder_hub.md).

### Android collection drive

See [File storage](../../../user_mobile/settings/settings.md#file-storage).

### Side-by-side mobile credential packages

See [Multiple credential packages](../user_mobile/connections.md#multiple-credential-packages-on-android-and-ios).

### Mobile Workspaces source tabs

See [mobile sources and copy handling](../../../user_mobile/folder_hub/folder_hub.md).

## LocalCrypt filename search

Open an unlocked LocalCrypt browser and use its filename search. The matching
names stay within the private session.

## Change a loaded credential ZIP password

In **Settings → Features → rclone**, select the loaded package and choose
**Change ZIP password…**. Resolve unsaved private edits, enter the new password
twice and supply the current password when requested. Logistics verifies the
new ZIP before replacing the old one and migrates matching protected history.
If history cannot migrate, its original encrypted records are kept and the
status tells you it still needs the previous password.
