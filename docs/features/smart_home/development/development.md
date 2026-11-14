# Smart Home implementation

Smart Home sends Philips Hue group commands from desktop Logistics and provides
standalone scripts for Tautulli playback events.

## Try a color preset change

1. Enable **Smart Home** in desktop **Settings → Features** if needed. Open
   **Smart Home** and locate **Kitchen → Red**. The page starts with a Kitchen
   control before any discovery. Leave the button unpressed for this exercise
   and send the command through the mocked bridge in the test.
2. In `Python/features/smart_home/ui/page.py`, follow
   `SmartHomePage._create_room_group()` to `_set_room()`. The Red button sends
   `State=True` and `Color='Red'` for the named group. In
   `Python/features/smart_home/philips_hue/api.py`, try changing
   `COLOR_PRESETS['Red']` from `(0, 254)` to `(0, 230)`.
3. In `Python/tests/integrations/test_smart_home.py`, change the expected
   `sat` value in `test_combined_properties_use_one_validated_group` to
   `230`. That fixture also supplies brightness explicitly to exercise the
   combined API. The desktop Red button sends power and color only.

Run from the repository root with the desktop environment set up:

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_smart_home.py
```

Expect four passing tests, including exactly one call for mock group 1 with
`{'on': True, 'bri': 254, 'hue': 0, 'sat': 230}`. Restore the original preset
and assertion after the exercise unless you intend to change the shipped color.

## Ownership and registration

`Python/features/smart_home/__init__.py` delegates to `ui_contributions.py`,
which contributes **Configuration** settings and a desktop page created on
demand. `configuration.py` reads effective `[PhilipsHue]` settings from
`config.ini`. It prefers `bridge_address_str` and falls back to the older
`bridge_address` key when the new key is absent. The API strips whitespace and
rejects a blank address before creating a `phue.Bridge`. See the
[desktop guide](../user/user.md#set-up-the-bridge) for setup and pairing.

The mobile packaging allowlist in `mobile_build/tools.py` omits this feature.
See [mobile availability](../user_mobile/user_mobile.md) and
[feature conventions](../../../development/features.md).

## Hue command boundary

**Connect Bridge** calls `connect_bridge()` explicitly. **Find rooms** calls
`get_rooms()` for sorted unique names of groups with positive decimal IDs,
regardless of Hue group type. Commands require an exact name matching one group
with a positive numeric ID. Missing or ambiguous names raise `ValueError`
before `set_group()`. If discovery lists a name that a command rejects,
check for duplicate group names on the bridge.

`_group_properties()` validates the request before acquiring the bridge.
State is Boolean. Brightness is an integer from 0 to 254. Hue (0 to 65535)
and saturation (0 to 254) must be supplied together as integers. A valid named
color overrides numeric hue and saturation once those inputs pass validation.
Supply at least one supported property.

The combined command sends one `set_group()` call. A Hue error entry becomes
a `RuntimeError`. Network and library errors propagate to the UI, which displays
them below the controls. Check the address, connectivity, authorization and
exact group name before retrying. The page submits commands without live state
polling or rollback.

## Desktop lifetime

`SmartHomePage._run()` uses `OperationProgress` to run bridge calls off the GUI
thread. It ignores new requests while busy and disables the room, connect and
discovery controls until `_finished()` restores them. A successful tuple result
replaces the room controls. An empty tuple displays **No rooms found on this
bridge.**

If the page is closing while busy, `prepare_close()` requests cancellation and
returns false. The worker checks cancellation before calling the bridge.
A request already in progress runs to completion, then the page emits `idle`.

## External automation

The three `tautulli/plex_*_living_room.py` scripts execute at import or run
time. Each sends three successive calls to turn on Living Room, set brightness
(20 for play/pause, 254 for stop), and set hue 10000 and saturation 150. A
later failure can leave the earlier calls applied. Tautulli owns event routing
and supplies the Python environment with `Python/` on the import path. See
[Tautulli setup](../user/user.md#tautulli-automation).

## Validation scope

The mocked bridge tests cover missing-room refusal, single-call submission,
invalid-value refusal before bridge access and reported Hue errors.
`Python/tests/application/test_integration_workers.py` covers the Qt worker,
close deferral, error display and control recovery.
`Python/tests/application/test_ini_settings.py` covers both address keys.
Pairing, physical bulb state and event delivery through Tautulli require
separate live checks.
