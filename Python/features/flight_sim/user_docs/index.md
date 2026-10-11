# Apply X-Plane 12 presets

Flight Simulator exposes X-Plane preset actions on **Debug**. The current workflow
uses presets for specific display setups. Set `installation_path` under **Settings → Flight Simulator** for your X-Plane folder; blank retains the historical Steam path on macOS.

## Before applying a preset

Supply the expected preset files beneath `Software/General/`. They are private
resources and are not downloaded by the public software manifest. Existing preferences are saved beside the originals as `.previous-…` recovery copies.

## Apply

Choose the Debug preset matching your intended machine/display layout. It updates X-Plane’s `Output/Preferences` folder after checking that every required setting exists. Close X-Plane before applying a preset.
Missing presets or an unsupported installation can fail; these actions are not a
general cross-platform simulator configuration tool. Verify the result in X-Plane
and restore the `.previous-…` files if necessary. Delete those copies only after checking the preset.

## More help

See [Using Logistics](../../../../USER_GUIDE.md) for navigation and settings.
