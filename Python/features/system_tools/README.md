# System Tools Feature

Developer notes. See the [user guide](user_docs/index.md) for controls and setup,
and [UI architecture](../UI_ARCHITECTURE.md) for shared contribution conventions.

Provides operating-system maintenance actions for Logistics.

## Responsibilities

- Launch Windows maintenance scripts bundled with Logistics.
- Run macOS lid-sleep configuration commands.

## Structure

- `actions.py` contains Windows and macOS maintenance actions.

## Windows Actions

- Repair Windows system files.
- Run the bundled NTFS repair script for drive D:.

These actions are available only on Windows.

## macOS Actions

- Disable battery-powered lid sleep.
- Restore battery-powered lid sleep.

These actions are available only on macOS and use `sudo pmset`.

## Safety Notes

System Tools can modify operating-system configuration or launch repair scripts.

These actions should only be run deliberately on the intended platform.
