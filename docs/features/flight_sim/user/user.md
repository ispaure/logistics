# Apply X-Plane 12 presets

Enable **X-Plane Presets** in **Settings → Features**, then find the preset
actions in desktop **Debug**. See [mobile availability](../user_mobile/user_mobile.md).

## Prepare

Close X-Plane. Set **installation_path** in **Settings → X-Plane Presets →
Installation**. A blank path uses the historical macOS Steam location.
The existing **X-Plane.prf** and **X-Plane Window Positions.prf** need readable
files and a writable **Output/Preferences** directory.

Place the matching private preset in **Software/General/x-plane/**.

| Preset | File |
| --- | --- |
| M3 Max Standalone | X-Plane Window Positions [m3 max, standalone].prf |
| M3 Max Flight Desk [Internal ON] | X-Plane Window Positions [m3 max, flight desk, internal].prf |
| M3 Max Office | X-Plane Window Positions [m3 max, office].prf |

## Apply and recover

Choose the action for your display layout and confirm. It updates graphics
values and window positions. Missing files or duplicate graphics keys stop
the update. Check both results before removing backup copies ending in
**.previous-…**. To restore manually, close X-Plane and put the appropriate
copies back under their original filenames.

See [Using Logistics](../../../user/user.md).
