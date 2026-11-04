# Control Philips Hue lights

Open **Smart Home** on desktop to send commands to Philips Hue groups. The page
starts with Living Room, Bedroom and Kitchen controls; these are initial names,
not confirmation that those rooms exist or that the bridge is connected.

## Set up the bridge

Set `bridge_address_str` under `[PhilipsHue]` in Smart Home's **Configuration**
settings (`Python/features/smart_home/config.ini`). Use the address of your own
bridge. The older `bridge_address` key remains a fallback.

Use **Connect Bridge** to connect/register with that bridge. If authorization
fails, follow the bridge's pairing procedure and retry. Use **Find rooms** to
replace the initial controls with sorted group names returned by the bridge.
An empty result displays **No rooms found on this bridge.** Room discovery is
requested manually; the page does not continuously monitor lights or show their
current power, brightness or color.

## Send a light command

Each room has the following controls:

| Control | Command |
| --- | --- |
| OFF / ON | Change power without specifying brightness or color |
| 1% / 50% / 100% | Turn on and set Hue brightness to 0 / 127 / 254 |
| Red, Orange, Yellow, Green, Aqua, Blue, Purple, Magenta, White | Turn on and set a fixed hue/saturation preset |

Color commands leave brightness unchanged. White uses saturation zero; it is
not a color-temperature selector. Controls apply to the whole named group.
Names must match exactly, including case. Missing or duplicate names fail rather
than sending a command to a different room.

Bridge work runs in the background. Controls are disabled until the request
finishes, and failures appear beneath the controls. Check the address,
connectivity, authorization and room name after a failure. Closing the page
while a request is active waits for that work to finish; cancellation does not
undo a light command already sent.

## Tautulli automation

The scripts in `Python/features/smart_home/tautulli/` are separate entry points
for Tautulli Plex playback events. Logistics does not start an event listener.
Configure Tautulli to run them with the Logistics Python environment and
`Python/` on its import path. Review the fixed Living Room target before enabling
automation; discovery in the desktop page does not change these scripts.

| Script | Current action |
| --- | --- |
| `plex_play_living_room.py` | Turn on; brightness 20; hue 10000, saturation 150 |
| `plex_pause_living_room.py` | Turn on; brightness 20; hue 10000, saturation 150 |
| `plex_stop_living_room.py` | Turn on; brightness 254; hue 10000, saturation 150 |

Each script sends three successive commands. A failure can leave earlier changes
applied. Stop restores full brightness; it does not turn lights off or restore a
previous scene. These scripts require separate Tautulli setup and bridge access.

See [Using Logistics](../../../user/user.md) for general navigation and
[mobile availability](../user_mobile/user_mobile.md) for platform scope.
