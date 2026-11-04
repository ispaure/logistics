# System Tools Feature

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

Developer notes. See the [user guide](../user/user.md) for controls and setup,
and [UI architecture](../../../development/features.md) for shared contribution conventions.

Provides operating-system maintenance actions for Logistics.

## Responsibilities

- Run embedded Windows maintenance commands in a separate administrator console.
- Run macOS lid-sleep configuration commands.

## Structure

- `actions.py` contains Windows and macOS maintenance actions.

## Windows Actions

- Repair Windows system files with DISM ScanHealth/RestoreHealth, SFC, and AppX re-registration.
- Run CHKDSK `/f /r` for the configured drive (default D:).

These actions are available only on Windows. The existing commonUtils PowerShell
wrapper starts a separate elevated PowerShell console through `Start-Process`
with `-Verb RunAs`. The command payload is UTF-16LE base64 for `-EncodedCommand`;
`-NoExit` keeps results and interactive CHKDSK prompts visible. Drive input must
match one drive letter and colon. Startup waits for UAC/console creation, not for
repair completion. A denied or failed launch returns False. No batch files or
temporary scripts are used.

## macOS Actions

- Disable battery-powered lid sleep.
- Restore battery-powered lid sleep.

These actions launch `sudo pmset` in an authentication-capable terminal. The
first disable saves battery settings; restore uses those saved values. A launch
return value reports terminal startup, not successful system modification.

## Safety Notes

System Tools can modify operating-system configuration or run disk repairs.

These actions should only be run deliberately on the intended platform.

## Registration, settings and saved state

`ui_contributions.py` declares destructive Debug actions and a Configuration
settings contribution for `config.ini`. OS checks disable irrelevant actions;
`actions.py` also rejects calls on the wrong platform. Windows drive settings
are trimmed and uppercased before validation; arbitrary paths and command text
are rejected before launching.

On macOS, the first disable reads battery `sleep` from `pmset -g custom` and
system-wide `SleepDisabled` from `pmset -g`. Both values must be available.
`battery-power.json`, beside the feature preferences file, is written atomically
before launching the terminal. Existing backups are reused, and restore leaves
the backup in place. Thus restore means the first recorded values, not the most
recent state before each disable. A missing backup or invalid nonnegative integer
values blocks restore; a desktop Mac without battery settings blocks capture.
The backup records intended recovery values, not proof that sudo succeeded.

## Platform and validation scope

These are Windows/macOS desktop actions. Linux has no enabled repair actions;
Android/iOS have no System Tools mobile catalogue entry or UI. See
[mobile availability](../user_mobile/user_mobile.md).

`Python/tests/application/test_system_tools.py` checks command payload order,
encoded elevated launch, normalized/invalid drives, launch failure, wrong-OS
rejection, battery capture and restore commands using mocks. It does not prove
successful operating-system repair or power behavior. This documentation audit
reviewed source/tests and ran static checks only; no repair, terminal, device or
GUI action was launched under the release quiet hold.
