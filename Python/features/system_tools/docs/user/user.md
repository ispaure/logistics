# Run system maintenance actions

System Tools exposes platform-specific actions on **Debug**. These operations can
change system configuration; select only the action intended for your machine.

| Platform | Action | Effect |
| --- | --- | --- |
| Windows | Windows System Files Repair | Runs DISM ScanHealth/RestoreHealth, SFC, and AppX re-registration |
| Windows | Repair configured NTFS drive | Runs `chkdsk` on the configured drive (default `D:`) |
| macOS | Disable macOS Lid Sleep | Changes battery-powered lid-sleep settings |
| macOS | Enable macOS Lid Sleep | Restores the saved battery sleep settings |

Other-platform actions are disabled. Windows repairs open a separate administrator
PowerShell console and request Windows approval (UAC). Commands are included in
Logistics; no repair batch files are required. The console stays open after the
commands finish. Check the drive target before starting Windows maintenance and
answer any CHKDSK prompts in that console.

macOS power commands open a terminal for `sudo` authentication. Disabling saves
the original battery settings; enabling restores that saved state. A launched
terminal does not mean the repair succeeded: inspect its command output.
These actions do not provide Linux system repair or a general disk-selection tool.

## More help

See [Using Logistics](../../../../../docs/user/user.md) for navigation and settings.

Choose the Windows NTFS drive in **Settings → System Tools**.
Use a drive letter such as `D:`. The terminal shows the selected drive before running
`chkdsk`; inspect its output to confirm completion.

On Mac laptops, the disable action changes battery idle sleep and the system-wide
sleep-disable flag. Restore uses the saved values for both. Desktop Macs without
battery settings cannot use this action.
