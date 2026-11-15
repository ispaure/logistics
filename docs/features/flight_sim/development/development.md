# Flight Simulator Feature

This desktop integration applies the supplied X-Plane preference presets.
Its core responsibility is to validate and publish the requested preference
changes without losing the original configuration when validation fails.

## Trace preference validation

The X-Plane preset actions on **Debug** use
`Python/features/flight_sim/actions.py:_updated_preferences` to prepare
updated preference bytes. Each required key must occur once before the
update can proceed. Tests use synthetic preference files to verify that a
missing key preserves the original file and that a failed second write
restores the graphics settings.

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_flight_sim.py
```

## Preference publication

`detection.py` resolves `[XPlane] installation_path` or the Steam default. The three macOS M3 Max presets need both preference files and the [private window presets](../user/user.md#prepare). `actions.py` holds the fixed graphics values.

Close X-Plane before applying. Validate both inputs and unique keys before writing. Preserve BOM, line endings and unrelated settings. Publish graphics then window positions with checked atomic writes and unique `.previous-…` copies. If the second write fails, restore graphics only if its bytes still match the update. Report both failures and the recovery path when rollback fails. See [manual recovery](../user/user.md#apply-and-recover) and [mobile availability](../user_mobile/user_mobile.md).
