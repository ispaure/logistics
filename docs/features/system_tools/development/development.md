# System Tools development

## Try a clearer repair message

Find **Repair configured NTFS drive** on the Windows desktop **Debug** page. Use the mocked launcher for this change. In `Python/features/system_tools/actions.py:run_repair_ntfs_on_d`, change `Repairing {drive}` to `Running CHKDSK on {drive}` in the PowerShell message. Update the `Write-Host` assertion and run from the repo root.

```sh
python3 dev.py test desktop --exact-file Python/tests/application/test_system_tools.py
```

Expect input ` e: ` to print `Running CHKDSK on E:` and invoke CHKDSK with `E: /f /r`. Invalid drive strings fail before launch.

The Debug host confirms destructive actions and callbacks recheck the OS. `[Windows] ntfs_drive` defaults to `D:`. Repairs launch elevated PowerShell. **Repair system files** runs DISM ScanHealth, DISM RestoreHealth, SFC and AppX re-registration in order.

On macOS, atomically save battery sleep and system `SleepDisabled` to `battery-power.json` before invoking `sudo pmset`. Keep the first backup. Restore requires both original values as nonnegative integers and retains the backup. Without it, use macOS System Settings. Check terminal output for operation results. See [operator workflows](../user/user.md) and [mobile availability](../user_mobile/user_mobile.md).
