# Flight Simulator Feature

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

Developer notes. See the [user guide](../user/user.md) for controls and setup,
and [UI architecture](../../../../../docs/development/features.md) for shared contribution conventions.

Provides flight-simulator-related integration for Logistics.

## Responsibilities

- Detect flight simulator installation and preference paths.
- Apply X-Plane 12 graphics settings.
- Apply X-Plane 12 window-position presets.
- Allow flight simulator support to remain optional.

## Structure

- `detection.py` resolves X-Plane installation and preference paths.
- `actions.py` applies X-Plane settings and preset configurations.

The Flight Sim UI only presents controls and delegates behavior to this feature package.

## X-Plane 12

Settings accepts an explicit X-Plane 12 installation path. The default retains
the Steam installation on macOS.

X-Plane preferences are resolved under `Steam/steamapps/common/X-Plane 12/Output/Preferences` within the user's Application Support directory. Preset assets live under the Logistics General software directory. Preferences
are validated as a whole, saved atomically and kept beside recovery copies.
Combined presets restore the prior preferences if window publication fails.

## Notes

Flight Simulator is an optional Logistics feature.

Platform or simulator support can be expanded later without moving simulator-specific behavior back into the UI or Logistics core.
