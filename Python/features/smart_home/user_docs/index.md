# Control Philips Hue lights

The **Smart Home** page controls configured Hue groups and color presets.

## Set up the bridge

Set `bridge_address` in `[PhilipsHue]` in
`Python/features/smart_home/config.ini`. The configured group names and presets
must match your Hue setup: the page currently uses Living Room, Bedroom and
Kitchen. Use **Connect Bridge** to connect/register, following any bridge pairing
instructions. Use **Find rooms** to replace the initial room buttons with the bridge’s current rooms.

## Use lights

Open Smart Home and choose the controls for your group: on/off, brightness or a
preset. These actions change the real lights. Commands run in the background and errors appear beneath the controls. Missing rooms do not receive a command. If a command fails, check the bridge
address, connectivity, authorization and group names.

## Tautulli automation

The living-room play/pause/stop scripts are separate entry points for Tautulli's
Plex playback events. Logistics does not start an event listener. Configure Tautulli
to run those scripts with the Logistics Python environment and `Python/` on its
import path. Adapt the group names to your room before enabling automation.

## More help

See [Using Logistics](../../../../USER_GUIDE.md) for navigation and settings.
