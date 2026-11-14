# Flight Simulator Feature

## Try a preference error change

In desktop **Debug → X-Plane Presets**, open and cancel the **X-Plane 12: M3 Max Standalone** confirmation. In `Python/features/flight_sim/actions.py:_updated_preferences`, include `path.name` in the missing/duplicate key error. Update `test_missing_key_does_not_change_file` to expect `prefs`. Run from the repo root.

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_flight_sim.py
```

Expect the filename in the error, identical original bytes and no recovery copy. The fixture needs no simulator.

## Preference publication

`detection.py` resolves `[XPlane] installation_path` or the Steam default. The three macOS M3 Max presets need both preference files and the [private window presets](../user/user.md#prepare). `actions.py` holds the fixed graphics values.

Close X-Plane before applying. Validate both inputs and unique keys before writing. Preserve BOM, line endings and unrelated settings. Publish graphics then window positions with checked atomic writes and unique `.previous-…` copies. If the second write fails, restore graphics only if its bytes still match the update. Report both failures and the recovery path when rollback fails. See [manual recovery](../user/user.md#apply-and-recover) and [mobile availability](../user_mobile/user_mobile.md).
