# System Tools development

System Tools adapts selected maintenance commands to the desktop host.
The integration owns input validation, platform checks and launch construction;
the operating system performs the requested repair or power-setting change.

## Trace a repair command safely

**Repair configured NTFS drive** reaches
`Python/features/system_tools/actions.py:run_repair_ntfs_on_d`. Use the mocked
launcher fixtures to inspect normalized drive arguments and rejected input
without running CHKDSK or other maintenance commands:

```sh
python3 dev.py test desktop --exact-file Python/tests/application/test_system_tools.py
```

The Debug host confirms destructive actions and callbacks recheck the OS. `[Windows] ntfs_drive` defaults to `D:`. Repairs launch elevated PowerShell. **Repair system files** runs DISM ScanHealth, DISM RestoreHealth, SFC and AppX re-registration in order.

On macOS, atomically save battery sleep and system `SleepDisabled` to `battery-power.json` before invoking `sudo pmset`. Keep the first backup. Restore requires both original values as nonnegative integers and retains the backup. Without it, use macOS System Settings. Check terminal output for operation results. See [operator workflows](../user/user.md) and [mobile availability](../user_mobile/user_mobile.md).
