# Smart Home implementation

## Try a color preset change

Find **Smart Home → Kitchen → Red** on desktop. Exercise the command with a mock bridge. In `Python/features/smart_home/philips_hue/api.py`, change `COLOR_PRESETS['Red']` from `(0, 254)` to `(0, 230)`. Update `test_combined_properties_use_one_validated_group` and run from the repo root.

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_smart_home.py
```

Expect one call for mock group 1 with `on=True, bri=254, hue=0, sat=230`. The fixture adds brightness to the button's power and color. Restore the preset and assertion after experimenting.

`configuration.py` prefers `[PhilipsHue] bridge_address_str` and falls back to `bridge_address` when absent. The API validates before connecting, requires one exact group name with a positive ID, and submits combined properties once. `ui/page.py` serializes commands off-thread and defers close until idle. In-flight bridge calls finish.

The three Tautulli scripts send separate power, brightness and color calls. Earlier changes can survive a later error. See [pairing and automation](../user/user.md) and [mobile availability](../user_mobile/user_mobile.md).
