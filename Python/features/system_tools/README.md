# System Tools Feature

For workflows, settings and troubleshooting, see the [user guide](user_docs/README.md).

Developer notes. See the [user guide](user_docs/README.md) for controls and setup,
and [UI architecture](../../../docs/developer/features.md) for shared contribution conventions.

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
