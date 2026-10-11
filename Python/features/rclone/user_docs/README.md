# Connect and transfer remote folders

Load private credential packages, then push or pull folders using the chosen
remote config. FUSE is optional and only needed for mounting.

## Set up credentials

1. Place your credential ZIP packages in the checkout's `RemoteCredentials/`
   directory (or the configured credentials resource directory).
2. Open **Settings → rclone → Credential packages** and load a package, entering its password when asked.
3. Return to **Folder Hub** and select the rclone source and credential.
4. Select a remote. If a local folder has exactly the same name, it is associated
   with that entry.

Each package creates its own config, such as `~/.config/rclone/Personal.conf`.
Credential ZIPs contain TXT entries with a remote section header as their first
line and the remote's rclone settings below it. Packages must be supplied separately;
Logistics does not create account credentials for you.

The **INI files** tab holds feature configuration, including software download
settings. Switching tabs retains unsaved INI edits and credential-panel state.
Use **User Guide** to return to these instructions.

## Transfer files

Use the selected folder's **Push…** or **Pull** action. Review the direction and
available options before starting: the operation changes files at its destination.
If several credentials define the same remote name, choose the intended credential;
its label does not change the local sync path. Mount paths are separated by config.

GUI Push/Pull opens a retained **Folder Actions** job with live transfer statistics,
command output, operation state and retry attempt. Results stay available after completion.
Success requires a normal exit with code zero; failures show the exit code and
recent output. rclone retains its own retry policy, and a successful retry reports
which attempt succeeded. **Cancel** stops the process; completed destination changes
remain. Closing Logistics cancels active integrated transfers and waits for them
to stop. A started job is not yet a successful transfer; check its final result.

| Location | Default path |
| --- | --- |
| Local copy | `~/Server/Local/<folder>` |
| Optional mount | `~/Server/NetworkMount/<config-id>/<remote>` |

Before an rclone command, a missing or mismatched executable offers a verified
download. Declining, cancelling or a download failure stops that command.
Windows/macOS/Linux x86_64 and ARM64 builds are pinned. Downloads do not start just
because you browse folders. Transfers have their own execution model; the download
Cancel button does not cancel a later transfer.

## Remove a loaded config

Removing a loaded credential deletes its generated config, leaving the ZIP package
available to load again. **Clear All .conf Files** removes every config directly in
the rclone config directory, including configs created outside Logistics.

For mounted browsing, see [FUSE](../../fuse/user_docs/README.md). For local software
and credential paths, see [application setup](../../../../CONFIGURATION.md).

## More help

See [Using Logistics](../../../../USER_GUIDE.md) for navigation and settings.


Marc’s existing Dropbox credential folder (`Software/GIT/logistics/RemoteCredentials`)
is also discovered automatically when present. Hover a package to see its location.

## Choose a rclone download version

In **Settings → rclone**, the configuration tabs list supported platforms. Each
contains the version, download URL, ZIP member, local destination and verification
hashes. If you change releases, update these values together. One hash verifies
the ZIP; the other verifies its executable. Saving does not download anything or
replace a running tool. See [download settings](../../../../CONFIGURATION.md#rclone-download-versions)
for the field details.

Sync progress opens in **Folder Actions** on the left rail. Each job has its own
tab with transfer statistics and logs; completed and failed jobs remain available
until you close them. A red badge marks results you haven't viewed. Completion
and errors also use system notifications when the platform supports them.
Closing a running job cancels it and waits for its process to stop.

## Choose the sync scope

Push and Pull use **sync**, not an additive copy. Files missing from the source can
be deleted at the destination; changed files can be replaced. Logistics provides
no undo for these transfers. Keep independent backups of destination-only files.

| Choice | Source → destination | Consequence |
| --- | --- | --- |
| Entire local folder | Managed local folder → remote root | Remote contents become a mirror of the local folder |
| Specific folder | Chosen folder → `remote:<folder-name>` | Only that destination subtree is synchronized; siblings are outside its scope |
| Pull | Remote root → managed local folder | Local destination-only files can be removed; the app asks for confirmation |

**Track renames**, offered for entire-folder Push, asks rclone to detect renames
instead of transferring matching content again. Specific-folder Push offers a
positive bandwidth limit in MB/s; blank means unlimited. Review the displayed
source and destination before pressing **PUSH**. The dialog shows target paths,
not a complete file-by-file deletion preview.

Sync follows source file links (`--copy-links`), so linked content can be included.
Two credentials with the same remote name share the managed local sync folder;
confirm the account before pushing or pulling that folder.
