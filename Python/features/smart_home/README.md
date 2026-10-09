# Smart Home

Developer notes. See the [user guide](user_docs/index.md) for controls and setup,
and [UI architecture](../UI_ARCHITECTURE.md) for shared contribution conventions.

Smart Home integration for Logistics.

This feature provides tools and integrations for interacting with smart home devices and services. Individual smart home platforms and automation sources are implemented as integrations within this feature rather than as separate top-level Logistics features.

## Integrations

### Philips Hue

`philips_hue/api.py` connects to the bridge, resolves groups by name and applies
on/off, brightness, hue/saturation and preset changes.

The Hue Bridge address is read from this feature's `config.ini`, under `[PhilipsHue]` / `bridge_address_str` (legacy `bridge_address` is still accepted).

### Tautulli

The `tautulli` integration contains standalone automation scripts intended to be executed by Tautulli in response to Plex playback events.

The current scripts control Philips Hue lights in the living room based on Plex playback state:

- `plex_play_living_room.py`
- `plex_pause_living_room.py`
- `plex_stop_living_room.py`

These scripts are external automation entry points, not event listeners started by Logistics. Configure Tautulli to run them with the Logistics Python environment and `Python/` on the import path.

## Extension points

Add device/service integrations as subpackages under Smart Home. `configuration.py`
owns feature settings, `ui_contributions.py` declares the page, and `ui/` presents
controls. Bridge settings belong to this feature's `config.ini`, not root application
configuration. Keep Tautulli scripts as independently executable entry points rather
than starting event listeners with the page.
