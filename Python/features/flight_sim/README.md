# Flight Simulator Feature

Provides flight-simulator-related integration for Logistics.

## Using this feature

The X-Plane presets are exposed on **Debug** while Flight Simulator is enabled.
Supply the private General software presets before applying them. These presets
do not use the public software download manifest.

See [shared setup and resource paths](../../../CONFIGURATION.md) and the
[Logistics feature index](../../../README.md#features) for application-wide setup.

## Responsibilities

- Detect flight simulator installation and preference paths.
- Apply X-Plane 12 graphics settings.
- Apply X-Plane 12 window-position presets.
- Keep flight-simulator-specific behavior isolated from Logistics core.
- Allow flight simulator support to remain optional.

## Structure

- `detection.py` resolves X-Plane installation and preference paths.
- `actions.py` applies X-Plane settings and preset configurations.
- `__init__.py` exposes the feature to the Logistics feature registry.

The Flight Sim UI only presents controls and delegates behavior to this feature package.

## Initialization

This feature does not require startup initialization.

It is discovered and loaded by the Logistics feature registry, but performs no work until flight simulator functionality is used.

## X-Plane 12

The current implementation targets the Steam installation of X-Plane 12 on macOS.

X-Plane preferences are resolved under `Steam/steamapps/common/X-Plane 12/Output/Preferences` within the user's Application Support directory. Preset files are stored under the Logistics General software directory and copied into the active X-Plane preferences when selected.

## Notes

Flight Simulator is an optional Logistics feature.

Platform or simulator support can be expanded later without moving simulator-specific behavior back into the UI or Logistics core.
