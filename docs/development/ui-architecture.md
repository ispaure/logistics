# Feature UI ownership

Application-wide guidance has moved to [developer documentation](development.md):

- [Architecture and startup](architecture.md)
- [Feature declarations and toggles](features.md)
- [Application extension points](extension-points.md)
- [Browser extensions](file-browser.md)

## Long-running workflows and safe closing

See [worker lifetime and cancellation](architecture.md#long-running-workflows-and-safe-closing).

## Desktop Workspaces details

### Seasonal snow

`services.seasonal.snow_enabled` owns the local-date season (December 15 through
January 2, inclusive) and high-contrast exclusion shared with mobile. `desktop.snow.SnowOverlay`
paints an input-transparent child of the main window. It observes Qt accessibility
contrast changes and polls the saved setting/date once per second; its drawing
timer stops for inactive or minimized windows. The Appearance panel saves
`configFile.ini`'s `[Appearance] seasonal_snow_bool` in the selected settings scope.
Focused desktop coverage is in `test_seasonal_snow.py`.

### Shared locked/unlocked folder artwork

Edit [`Python/services/folders/appearance.py`](../../Python/services/folders/appearance.py)
for both desktop and mobile: `FOLDER_PATHS['folder_locked']` and
`FOLDER_PATHS['folder_unlocked']` define the polylines on a 24-point grid,
`FOLDER_FILLS` defines the centered solid lock bodies and transparent keyholes
with even-odd contours, `FOLDER_STROKE_WIDTH` defines their stroke, and `LOCK_LIGHT`/`LOCK_DARK`
define the state colors. Shapes use round caps and joins. Both padlocks sit
inside the complete folder outline with Balanced, nearly square bodies and no
chains; the unlocked shackle swings
outward to the right. Regular folders use the same blue as unlocked folders.

Desktop's `Python/desktop/pages/workspace_icons.py` renders these paths with Qt;
mobile's `Python/mobile/control_icons.py` renders them with UIKit and
Android drawing APIs. Mobile's `palette.py` imports the shared colors and uses
black for both states in monochrome mode. Keep distinct shapes and accessible
state labels so color is not the only signal.

Passive mobile browser indicators also need bundled PNGs in
`Python/mobile/hub_icons.py`. These are generated copies, not a second
artwork source. After changing geometry, fills or stroke width, regenerate and check
them from the repository root (Pillow is needed only by this development tool):

```sh
.venv/bin/python mobile_build/generate_folder_icons.py
.venv/bin/python mobile_build/generate_folder_icons.py --check
```

Commit the updated embedded PNGs with the source change; mobile does not need
Pillow at runtime. State colors are applied by the native template-image
adapters, so color-only edits do not need PNG regeneration. The plain storage
padlocks (`storage_crypt`/`storage_unlocked`) and navigation/application icons
are separate artwork.

### Workspace layout

`desktop/pages/folders.py` hosts separate Info and Actions tabs below the source
list, with Actions selected initially. General workspace metadata is populated in
`info_scroll` for each selection, including selections whose actions need an
unlock. Feature widgets and action groups continue to populate `detail_scroll`;
credential checks, background detection and action targets keep their existing
contracts. Clearing the selection clears both tabs.

`workspace_panes.py` reserves initial horizontal proportions of 200:850 for the
left column and Files. Dividers remain resizable. The folder-list panel below the source/credential dropdown contains an
icon-only refresh button at its upper right, with a tooltip and accessible name.

## Desktop Folder Hub requests

`desktop/pages/folder_controller.py` owns source/detail request generations,
pending refresh state and worker preparation without Qt. `FoldersPage` composes
it and retains native widgets, credential-revocation checks, stale-result rejection
and cooperative close. Compatibility state attributes delegate to that controller.
Provider declarations are still resolved on the GUI thread; only provider I/O and
tool availability checks run in workers. Private folders never reach tools that
have not declared backend-aware support. Folder controller and source UI tests
cover the boundary.
