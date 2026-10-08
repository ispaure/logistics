# Run system maintenance actions

System Tools exposes platform-specific actions on **Debug**. These operations can
change system configuration; select only the action intended for your machine.

| Platform | Action | Effect |
| --- | --- | --- |
| Windows | Windows System Files Repair | Launches the supplied repair script |
| Windows | Repair NTFS on D:/ | Launches the configured repair for drive D: |
| macOS | Disable macOS Lid Sleep | Changes battery-powered lid-sleep settings |
| macOS | Enable macOS Lid Sleep | Restores the corresponding lid-sleep setting |

Other-platform actions are disabled. macOS power commands use `sudo` and may require
a password in their command flow. Check the repair script/drive target before
starting Windows maintenance. Inspect command output if an operation fails.
These actions do not provide Linux system repair or a general disk-selection tool.

## More help

Read [Using Logistics](../../../../USER_GUIDE.md) for navigation, resources and
feature controls. Use Back/Forward in this viewer to return to a previous guide.
