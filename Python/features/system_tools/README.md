# System Tools Feature

Provides operating-system maintenance actions for Logistics.

## Responsibilities

- Launch Windows maintenance scripts bundled with Logistics.
- Run macOS lid-sleep configuration commands.
- Keep operating-system maintenance behavior out of the UI and global command layer.

## Structure

- `actions.py` contains Windows and macOS maintenance actions.
- `__init__.py` exposes the feature to the Logistics feature registry.

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

## Initialization

This feature does not require startup initialization.

It is discovered by the Logistics feature registry but performs no work until a System Tools action is used.
