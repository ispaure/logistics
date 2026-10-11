# System Tools Feature

For workflows, settings and troubleshooting, see the [user guide](user_docs/README.md).

Developer notes. See the [user guide](user_docs/README.md) for controls and setup,
and [UI architecture](../../../docs/developer/features.md) for shared contribution conventions.

Provides operating-system maintenance actions for Logistics.

## Responsibilities

- Launch Windows maintenance scripts bundled with Logistics.
- Run macOS lid-sleep configuration commands.

## Structure

- `actions.py` contains Windows and macOS maintenance actions.

## Windows Actions

- Repair Windows system files.
- Run the bundled NTFS repair script for the configured drive (default D:).

These actions are available only on Windows.

## macOS Actions

- Disable battery-powered lid sleep.
- Restore battery-powered lid sleep.

These actions launch `sudo pmset` in an authentication-capable terminal. The
first disable saves battery settings; restore uses those saved values. A launch
return value reports terminal startup, not successful system modification.

## Safety Notes

System Tools can modify operating-system configuration or launch repair scripts.

These actions should only be run deliberately on the intended platform.
