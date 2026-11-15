# Smart Home implementation

Smart Home connects configured desktop controls to Philips Hue and provides
separate Tautulli scripts. The Hue API validates the requested group and values
before sending a command; UI retirement must account for in-flight calls.

## Trace a Hue command

A preset such as **Smart Home → Kitchen → Red** reaches
`Python/features/smart_home/philips_hue/api.py`. Use the mock-bridge fixtures
when changing this path. They check group validation and combining power,
brightness and color into one call without controlling real lights:

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_smart_home.py
```

`configuration.py` prefers `[PhilipsHue] bridge_address_str` and falls back to `bridge_address` when absent. The API validates before connecting, requires one exact group name with a positive ID, and submits combined properties once. `ui/page.py` serializes commands off-thread and defers close until idle. In-flight bridge calls finish.

The three Tautulli scripts send separate power, brightness and color calls. Earlier changes can survive a later error. See [pairing and automation](../user/user.md) and [mobile availability](../user_mobile/user_mobile.md).
