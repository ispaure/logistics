# Connect and transfer remote folders

Load private credential packages, then push or pull folders using the chosen
remote config. FUSE is optional and only needed for mounting.

## Set up credentials

1. Place your credential ZIP packages in the checkout's `RemoteCredentials/`
   directory (or the configured credentials resource directory).
2. Open **Settings → rclone → Credential packages** and load a package, entering its password when asked.
3. Return to **Known Folders** and select the rclone source and credential.
4. Select a remote. If a local folder has exactly the same name, it is associated
   with that entry.

Each package creates its own config, such as `~/.config/rclone/Personal.conf`.
Credential ZIPs contain TXT entries with a remote section header as their first
line and the remote's rclone settings below it. Packages must be supplied separately;
Logistics does not create account credentials for you.

The **INI files** tab holds feature configuration, including software download
settings. Switching tabs retains unsaved INI edits and credential-panel state.
The **User Guide** button remains in the upper-right corner of the feature page.

## Transfer files

Use the selected folder's **Push…** or **Pull** action. Review the direction and
available options before starting: the operation changes files at its destination.
If several credentials define the same remote name, choose the intended credential;
its label does not change the local or mount path.

GUI Push/Pull opens an integrated progress window with live transfer stats, command
output, operation state, and retry attempt. The window stays open after completion.
Success requires a normal exit with code zero; failures show the exit code and
recent output. rclone retains its own retry policy, and a successful retry reports
which attempt succeeded. **Cancel** stops the process; completed destination changes
remain. Closing Logistics cancels active integrated transfers and waits for them
to stop. Explicit synchronous/query callers retain their existing execution API.

| Location | Default path |
| --- | --- |
| Local copy | `~/Server/Local/<folder>` |
| Optional mount | `~/Server/NetworkMount/<remote>` |

Before an rclone command, a missing or mismatched executable offers a verified
download. Declining, cancelling or a download failure stops that command.
Windows/macOS/Linux x86_64 and ARM64 builds are pinned. Downloads do not start just
because you browse folders. Transfers have their own execution model; the download
Cancel button does not cancel a later transfer.

## Remove a loaded config

Removing a loaded credential deletes its generated config, leaving the ZIP package
available to load again. **Clear All .conf Files** removes every config directly in
the rclone config directory, including configs created outside Logistics.

For mounted browsing, see [FUSE](../../fuse/user_docs/index.md). For local software
and credential paths, see [application setup](../../../../USER_GUIDE.md#resources-and-settings).

## More help

Read [Using Logistics](../../../../USER_GUIDE.md) for navigation, resources and
feature controls. Use Back/Forward in this viewer to return to a previous guide.

Marc’s existing Dropbox credential folder (`Software/GIT/logistics/RemoteCredentials`)
is also discovered automatically when present. Hover a package to see its location.

## Choose a rclone download version

In **Settings → rclone**, the configuration tabs list supported platforms. Each
contains the version, download URL, ZIP member, local destination and verification
hashes. If you change releases, update these values together. One hash verifies
the ZIP; the other verifies its executable. Saving does not download anything or
replace a running tool. See [download settings](../../../../CONFIGURATION.md#rclone-download-versions)
for the field details.
