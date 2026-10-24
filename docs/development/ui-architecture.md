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
.venv/bin/python mobile_build/build_support/generate_folder_icons.py
.venv/bin/python mobile_build/build_support/generate_folder_icons.py --check
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

## Desktop performance assessment (October 24, 2026)

The first measured bottleneck was applying a saved accent color. A local macOS
Qt 6.12 offscreen fixture used the shared appearance settings editor and five
text browsers, each with 100 repeated prose/inline-code/fenced-code groups.
Three successive color saves were profiled with `cProfile`; settings paths were
temporary and no personal configuration was edited.

The median edit/save/apply/event-drain cycle fell from approximately **1.18 s to
0.13 s** after the shared theme/font changes. Theme/font application alone fell
from approximately **1.05 s to 0.0013 s**. The dominant original cost was
`QApplication.setStyleSheet`, which repolished existing widgets on every accent
change. These are fixture measurements, not an end-to-end timing of a running
Logistics session; document readers and contributed pages can add work.
The implementation and font-role contracts belong in commonUtils' own styling
guide. Raw profiling output remains outside the wiki.

The follow-up pass retains settings controls after successful saves and checks
effective LM message appearance before reimporting Markdown. The same appearance
fixture now measures roughly **1–3 ms for Save**, and **3–6 ms for the whole
save/apply/event-drain cycle**. Existing fields, previews, selected tab, focus,
text selection and scroll survive Save. Explicit Reload still rebuilds the form;
conflict baselines and inheritance indicators refresh after each successful save.

A separate offscreen LM fixture used 100 message browsers, each with ten repeated
prose/inline-code/fenced-code groups. A theme transition followed by a styling
notification previously imported 200 documents. It now imports 100, with median
time decreasing from **1.29 s to 0.58 s** across three transitions. Reading/code
font changes still render; unrelated font-role notifications skip message imports.
Books likewise skips chapter imports for unrelated shared preferences while
retaining reading-font changes and shared tint changes for slate/dark readers.

Startup was profiled with temporary personal settings, first with shipped defaults,
then with Git, IDE and LM enabled. Feature initialization took about 0.06 s;
main-window construction took 0.49 s / 0.67 s respectively. In the latter fixture,
File Browser construction took 0.14 s, Git 0.13 s, Settings 0.065 s, LM 0.028 s,
Workspaces 0.013 s and IDE 0.004 s. First show plus five event drains added 0.11 s.
This isolated fixture has no real projects, accounts or conversation history, and
imports before the measured interval are excluded. It does not estimate full cold
startup or a user's populated session.

Lazy page construction remains a separate follow-up: measure a populated session
and memory first, then preserve feature toggles, direct IDE/file opening, close
guards and background task ownership. The current lifecycle is retained; the
measurements above identify File Browser and Git as the first constructors to
investigate.

Validation for the appearance change covers shared theme/styling, rendered pixels,
Markdown presentation, browser polish and status-line fonts, plus Logistics'
landing, LM, Books and Git appearance tests. Follow-up tests cover retained settings
controls, repeated saves, both scopes, inheritance resets, external edits, duplicate
LM signals, code/reading font changes and selective Books rendering. Offscreen checks do not certify native
Windows/Linux rendering or the latency of an already-open desktop session.
