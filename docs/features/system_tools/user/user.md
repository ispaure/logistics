# Run system maintenance actions

Choose a platform action under **Debug**. These commands change system settings.

| Platform | Action | Effect |
| --- | --- | --- |
| Windows | **Windows System Files Repair** | Runs DISM, SFC and AppX re-registration. |
| Windows | **Repair configured NTFS drive** | Runs CHKDSK on the selected drive. Check its letter in **Settings → System Tools** first. |
| macOS | **Disable macOS Lid Sleep** | Saves and changes battery sleep settings. |
| macOS | **Enable macOS Lid Sleep** | Restores the saved settings. |

Accept Windows UAC or enter the macOS sudo password if requested. Read the
terminal output to confirm the command succeeded.

## More help

See [Using Logistics](../../../user/user.md).

## Platform availability

See [mobile availability](../user_mobile/user_mobile.md).

## Restoring saved Mac settings

The first disable saves the original battery settings. Later runs reuse that
backup. If none exists, choose sleep behavior in macOS System Settings.
