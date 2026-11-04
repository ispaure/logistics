# Apply X-Plane 12 presets

Enable **X-Plane Presets** under **Settings → Features**. Its three actions appear
on the desktop **Debug** page, grouped under **X-Plane Presets**; the feature does
not add a simulator tab. Android and iOS have [no preset workflow](../user_mobile/user_mobile.md).

## Prepare

Close X-Plane before changing its preferences. Set `[XPlane] installation_path`
in **Settings → X-Plane Presets → Installation** to your X-Plane 12 folder.
A blank setting uses the historical Steam path under the user's Application
Support directory on macOS. This is a fixed fallback, not an installation scan.
An explicit path changes the target folder; it does not establish support for
other simulators or verify that a preset suits another machine.

Both existing files must be readable and their directory writable:

- `Output/Preferences/X-Plane.prf`
- `Output/Preferences/X-Plane Window Positions.prf`

Supply the matching window preset under your Logistics General software directory,
`Software/General/x-plane/`. These private resources are not downloaded by the
public software manifest.

| Debug action | Required preset filename |
| --- | --- |
| X-Plane 12: M3 Max Standalone | `X-Plane Window Positions [m3 max, standalone].prf` |
| X-Plane 12: M3 Max Flight Desk [Internal ON] | `X-Plane Window Positions [m3 max, flight desk, internal].prf` |
| X-Plane 12: M3 Max Office | `X-Plane Window Positions [m3 max, office].prf` |

## Apply and recover

Choose the action matching your machine/display layout and accept the Debug
confirmation. Each action changes seven graphics values as well as replacing
window positions. Missing or duplicated graphics keys stop the update; Logistics
does not insert guessed keys. Missing files also prevent completion.

Before publishing each changed file, Logistics saves that file's original bytes
beside it as `<filename>.previous-<unique suffix>`. If window publication fails
after graphics publication, Logistics restores the graphics original only when
that file still matches its own update, preserving an intervening external edit.
The two files are not published as one transaction.

Check the result in X-Plane. To recover manually, close X-Plane and restore the
appropriate recovery copies to their original filenames. There is no in-app
restore action. Keep the copies until you have checked both graphics and window
positions; repeated runs create additional copies.

See [Using Logistics](../../../user/user.md) for navigation and settings.
