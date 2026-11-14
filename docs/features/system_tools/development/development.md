# System Tools development

System Tools contributes Windows repair and macOS power commands to the desktop
**Debug** page. See the [user guide](../user/user.md) for operator workflows.

## Try a clearer repair message

On Windows desktop, find **Repair configured NTFS drive** under **System Tools**
on the **Debug** page. Its drive comes from the INI editor in the
**System Tools** feature settings. The Debug button opens a confirmation for a
real repair. Exercise the command-building change below with the mocked test.

Follow `Python/features/system_tools/ui_contributions.py:get_contributions`
to the button's callback, `run_repair_ntfs_on_d` in
`Python/features/system_tools/actions.py`. For example, change the PowerShell
message from `Repairing E:` to `Running CHKDSK on E:` by editing the string
that interpolates the normalized drive. Update the corresponding
`Write-Host` assertion in `test_ntfs_repair_uses_normalized_configured_drive`.

Run this from the repository root using the
[desktop environment](../../../development/getting-started.md). The test
supplies a simulated Windows platform and mocks the launcher, so it also runs
on macOS and Linux.

```sh
python3 dev.py test desktop --exact-file Python/tests/application/test_system_tools.py
```

Expect the decoded payload for the input ` e: ` to print
`Running CHKDSK on E:` and pass `E: /f /r` to CHKDSK. Invalid drive strings
must still raise before launch.

## Registration, settings and saved state

`Python/features/system_tools/__init__.py:register` loads the settings and
Debug contributions from `ui_contributions.py`. `DebugPage` in
`Python/desktop/pages/debug.py` renders the buttons. The shared
`desktop.actions.execute_action` confirms destructive actions before invoking
the callback. Contribution enablement follows the OS and the callbacks check
the OS again. Linux has no enabled repair actions. See
[mobile availability](../user_mobile/user_mobile.md) for Android and iOS.

The feature settings expose `Python/features/system_tools/config.ini`. Windows reads
`[Windows] ntfs_drive`, defaulting to `D:`, strips surrounding whitespace,
uppercases it and accepts one ASCII drive letter followed by a colon.

On macOS, the first disable reads battery `sleep` from `pmset -g custom`
and system-wide `SleepDisabled` from `pmset -g`. Both values are required.
`disable_macos_lid_sleep` writes `battery-power.json` atomically beside the
feature preferences before launching the terminal. Later disables reuse the
first backup, and restores leave it in place. The backup records the values
that restore will apply. Restore requires a backup with both values stored
as nonnegative integers. When no backup exists, choose sleep behavior in
macOS System Settings. Capture requires a Mac that reports battery settings.

## Command launch and validation

The Windows system-files action runs DISM ScanHealth, DISM RestoreHealth, SFC
and AppX re-registration in that order. The NTFS action runs CHKDSK
`/f /r` on the configured drive. Both use the commonUtils PowerShell wrapper
and `Start-Process -Verb RunAs`. The launcher passes the UTF-16LE base64 payload
to `-EncodedCommand` and keeps the console open with `-NoExit` for output and
interactive prompts. Commands ship in the Python module. A denied or failed
console startup returns `False`.

The macOS actions open an authentication-capable terminal with `sudo pmset`.
On both platforms, a successful launch reports startup. Inspect the terminal's
output to verify repair or configuration changes. The focused tests cover
command payloads, platform guards, launch failure and backup handling with
mocks. Actual repair and power behavior require platform validation.
