# Smart Home

Smart Home integration for Logistics.

This feature provides tools and integrations for interacting with smart home devices and services. Individual smart home platforms and automation sources are implemented as integrations within this feature rather than as separate top-level Logistics features.

## Integrations

### Philips Hue

Philips Hue support is provided through the `philips_hue` integration.

Current functionality includes:

- Connecting to a configured Philips Hue Bridge.
- Resolving Hue groups by name.
- Turning light groups on and off.
- Setting group brightness.
- Setting group hue and saturation.
- Applying predefined color presets.

The Hue Bridge address is read from this feature's `config.ini`, under `[PhilipsHue]` / `bridge_address`.

### Tautulli

The `tautulli` integration contains standalone automation scripts intended to be executed by Tautulli in response to Plex playback events.

The current scripts control Philips Hue lights in the living room based on Plex playback state:

- `plex_play_living_room.py`
- `plex_pause_living_room.py`
- `plex_stop_living_room.py`

These scripts are external automation entry points, not event listeners started by Logistics. Configure Tautulli to run them with the Logistics Python environment and `Python/` on the import path.

## Structure

```text
smart_home/
├── __init__.py
├── README.md
├── config.ini
├── configuration.py
├── ui_contributions.py
├── ui/
├── philips_hue/
│   ├── __init__.py
│   └── api.py
└── tautulli/
    ├── __init__.py
    ├── plex_pause_living_room.py
    ├── plex_play_living_room.py
    └── plex_stop_living_room.py
```

Additional smart home integrations can be added under this feature as needed.

## Configuration

Smart Home owns its Philips Hue bridge configuration in:

`features/smart_home/config.ini`

The root Logistics configuration does not contain Smart Home-specific network
addresses.
