# Smart Home implementation

See the [desktop guide](../user/user.md) for setup and commands and
[mobile availability](../user_mobile/user_mobile.md) for platform scope.

## Ownership and registration

`Python/features/smart_home/__init__.py` declares the feature and delegates to
`ui_contributions.py`. Its `Feature` contributes Configuration settings and a
lazy desktop `PageContribution` with ID `smart_home`, order 30 and navigation icon
`smart_home`. `ui/page.py` owns the Qt page and fixed initial room names.
`configuration.py` reads effective settings for the feature's `config.ini`:
`[PhilipsHue] / bridge_address_str`, falling back to `bridge_address`.
The API strips whitespace and rejects an empty address before creating a bridge.

There is no mobile adapter or `mobile_sources.json` for this feature, and
`mobile_build/tools.py` excludes it from `SOURCE_OWNERS`. Desktop registration
must not be interpreted as Android/iOS support.

## Hue command boundary

`philips_hue/api.py` uses `phue.Bridge` with the configured address. Pairing is an
explicit `connect_bridge()` operation. `get_rooms()` returns sorted unique group
names whose IDs are positive decimal values; it does not filter groups by type.
Commands resolve an exact name to exactly one positive numeric group ID.
Duplicate or absent names raise `ValueError` without calling `set_group`.

`_group_properties()` validates the requested changes before bridge acquisition:

- State must be a Boolean.
- Brightness is an integer from 0 through 254.
- Hue and saturation must be supplied together, as integers in 0–65535 and 0–254.
- Color must name a preset in `COLOR_PRESETS`; a preset replaces supplied hue/saturation.
- At least one supported property must be requested.

The public combined command resolves the group and makes one `set_group` call.
Hue error entries in its response raise `RuntimeError`; network/library errors
propagate to the caller. Separate state/brightness/color helpers each make their
own call. This is command submission, without live state polling or rollback.

## Desktop lifetime

`SmartHomePage` uses `OperationProgress` for bridge calls. `_run()` ignores a new
request while busy and disables room, connect and discovery controls until
completion. `_finished()` restores them and replaces room controls only when a
successful result is a tuple. An empty tuple yields an explicit no-rooms message.
`prepare_close()` requests cancellation and returns false while busy; the task
checks cancellation before entering the callback. It cannot interrupt or reverse
a bridge operation already underway. Completion emits `idle`.

## External automation

The three `tautulli/plex_*_living_room.py` modules execute at import/run time and
each send state, brightness and color as separate operations to Living Room.
Play and pause use brightness 20, stop uses 254; all use hue 10000 and saturation
150 and turn power on. They do not inspect event arguments, retain a previous
scene, subscribe to Plex events or run a listener inside Logistics. Tautulli owns
invocation and the Python environment/import path.

## Validation scope

`Python/tests/integrations/test_smart_home.py` contains mocked bridge regression
contracts for missing-room safety, a combined single call, invalid-value rejection
before bridge access and Hue response errors. The implementation also rejects
ambiguous group names, but this file does not directly test that case.

`Python/tests/application/test_integration_workers.py` checks that Hue work runs
off the GUI thread, closing waits while busy, controls recover and errors display.
`Python/tests/application/test_ini_settings.py` covers feature configuration
location. These tests do not establish real bridge pairing, physical bulb state
or Tautulli event delivery.

This documentation audit used source/test inspection and static Markdown/link
checks only under the release quiet hold. No tests, Qt sessions, builds or device
runs were launched. Real Hue/network and Tautulli acceptance remains unverified
by this audit; mobile acceptance does not apply to the absent mobile feature.

Follow [feature conventions](../../../development/features.md) when extending
registration. Keep device/service integrations in this feature, configuration in
its owner, and presentation in `ui/`; document reusable shared APIs in commonUtils.
