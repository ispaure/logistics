# Flight Simulator Feature

Developer notes. See the [user guide](user_docs/index.md) for controls and setup,
and [UI architecture](../UI_ARCHITECTURE.md) for shared contribution conventions.

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

The current implementation targets the Steam installation of X-Plane 12 on macOS.

X-Plane preferences are resolved under `Steam/steamapps/common/X-Plane 12/Output/Preferences` within the user's Application Support directory. Preset files are stored under the Logistics General software directory and copied into the active X-Plane preferences when selected.

## Notes

Flight Simulator is an optional Logistics feature.

Platform or simulator support can be expanded later without moving simulator-specific behavior back into the UI or Logistics core.
