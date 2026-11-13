# Screen and panel ownership

Application-wide guidance has moved to [developer documentation](development.md):

- [Architecture and startup](architecture.md)
- [Feature declarations and toggles](features.md)
- [Application extension points](extension-points.md)
- [Browser extensions](file-browser.md)

## Find a screen by its visible name

| Screen or panel | Presentation owner | Composition and navigation |
| --- | --- | --- |
| Mobile Home | `Python/mobile/home.py:HomeScreen` | `hub_ui.HubUI` composes Home and Documents and retains session summaries, reopen and refresh coordination |
| Mobile Documents | `Python/mobile/documents_hub.py:DocumentsHub`; shared sections and rows in `hub_controls.py` | Same composed hub owner; routes and sessions retain their existing identities |
| Mobile Workspaces root and source tabs | `Python/mobile/workspaces_screen.py:WorkspacesScreen` | `folder_hub_ui.FolderHubUI` retains discovery, access and folder workflows |
| Mobile browser location heading | `Python/mobile/browser_location.py:FolderLocationHeader` | `browser_ui.FileBrowser` retains browsing and compatibility exports |
| Mobile New/Open/Save As destination form | `Python/mobile/document_destination_form.py:build_destination_form` | `editor_picker.EditorPicker` retains operation state, source policy, consent, cancellation and publication |
| Mobile Settings → Appearance | `Python/mobile/settings/appearance.py`; accent controls in `accent.py` beside it | `mobile.app.LogisticsMobile.show_settings()` → `settings.categories.settings_sections()` → `SettingsNavigation` |
| Mobile Settings → App | `Python/mobile/settings/app.py` | Same lazy category registry |
| Mobile Settings → Privacy & Security | `Python/mobile/settings/privacy_security.py`; audio and trusted Wi-Fi controls in sibling modules | Same registry; access policy remains with the [privacy owners](access-privacy.md) |
| Mobile Settings → Markdown, Text or EPUB | `Python/mobile/settings/text.py` | One parameterized font/reading panel, with feature-specific controls retained |
| Mobile Settings → Workspaces | `Python/mobile/settings/workspaces.py` | Storage and connection actions delegate to their existing owners |
| Mobile Settings → Help or About | `Python/mobile/settings/help.py`; installed-version content in `information.py` | Help/About share one module; their routes remain separate |
| Desktop Settings → Appearance & shared controls | `Python/desktop/settings/appearance.py:AppearanceSettingsPanel` | `desktop.pages.settings.SettingsPage._selected()` |
| Desktop Settings → Configuration | `Python/desktop/settings/configuration.py:ConfigurationPanel` | Same retained category host |
| Desktop Settings → Feature settings | `Python/desktop/settings/feature_settings.py:FeatureSettingsPanel` | Feature contributions supply lazy widgets and config files |
| Mobile workspace browser | `Python/mobile/files_ui.py`, `file_drawer.py`, `workspace_navigation.py` | [Workspace navigation](mobile-workspace-navigation.md) separates retained browsers from pane placement |
| Desktop Workspaces | `Python/desktop/pages/folders.py`, `folder_tree.py`, `workspace_panes.py` | Source requests and selection stay with the page/controller |
| Desktop rclone sync / Workspace actions | `Python/features/rclone/transfers/ui/progress.py:open_transfer_progress`; Push/Pull setup and review in sibling modules | `transfers/sync.py` selects execution mode; shared `process_host` presents in `desktop/folder_actions.py:FolderActionsPage` or a standalone window |
| Mobile Transfer / Transfer review | `Python/features/rclone/transfers/mobile/{ui,review_ui,surface,native_fallback}.py`; offline controls in `transfers/assets/surface.*` | `TransferController` retains feature state; `Python/mobile/transfer_status.py` mounts shell shortcuts |

Mobile `settings/categories.py` keeps small feature links and the ordered `Category`
declarations: title, factory, arguments, icon, camera requirement and required
feature IDs. `settings_sections()` applies those requirements before building
anything. `settings/navigation.py` reads the same metadata for icons and retains
each category on first access through `SettingsPages`; compact routes and wide
panes share those retained pages. Category titles are route identities, so changing
a display label requires checking selection restoration and callers.

Desktop `SettingsPage` owns the sidebar, selected scope, retained panels and close
checks. Its historical `CommonUtilsPanel` name remains an alias of
`AppearanceSettingsPanel`; new implementation work belongs in the named panel.
The platforms keep their own widgets and navigation. Shared form and editor
mechanisms remain in commonUtils.

## Add or change a Settings panel

1. Put a substantial mobile panel beside the existing visibly named modules in
   `Python/mobile/settings/`; reuse `forms.py` for rows and page construction.
   Keep tiny launch links in `categories.py` and reuse parameterized controls
   where the behavior is the same.
2. Add the mobile factory to `SettingsCategories` and its ordered `Category`
   declaration. Declare the icon and feature/camera gates there. Preserve lazy
   construction and per-window retained state in `SettingsNavigation`.
3. Keep preference defaults and validation in `mobile/preference_schema.py`,
   persistence/migrations in `mobile/preferences.py`, and access policy with its
   service owner. Add new modules to the owning `mobile_sources.json`.
4. Check mobile settings navigation, controls and checkpoint behavior with
   `python3 dev.py test mobile 'test_settings*.py'`; check the payload with
   `python3 dev.py test desktop test_mobile_packaging.py`. Native layouts,
   focus and gestures still require native validation.

For a desktop application category, add its panel under `desktop/settings/` and
connect it in `SettingsPage`. Feature settings use a `SettingsContribution`
instead; follow [extension points](extension-points.md#feature-settings). Preserve
scope changes and `can_close()` behavior. Start with
`python3 dev.py test desktop test_settings_page.py`.

## Long-running workflows and safe closing

See [worker lifetime and cancellation](architecture.md#long-running-workflows-and-safe-closing).

## Appearance and shared control edit points

| Change | Owner |
| --- | --- |
| Desktop light/dark palette, standard buttons and progress styling | commonUtils `ui/appearance/theme.py`; font families, role sizes and saved defaults in `styling.py`, `font_families.py` and `typography.py` |
| Logistics native semantic colors and embedded CSS variables | `Python/services/appearance_palette.py`; native palette selection in `Python/mobile/palette.py` |
| Native color application, system appearance and E Ink exceptions | `Python/mobile/appearance.py`, using commonUtils `ui/native/appearance.py` |
| Mobile control text sizes and touch targets | `Python/mobile/ui_metrics.py`; preference defaults in `preference_schema.py` and reader sizing in `font_scaling.py` |
| Native form fitting and settings rows | commonUtils `ui/native/forms.py`; Logistics settings composition in `Python/mobile/settings/forms.py` |
| Transfer WebView typography, spacing, responsive controls and status colors | `Python/features/rclone/transfers/assets/surface.css`; `mobile/surface.py` supplies palette CSS and font/E Ink state |

Shared API contracts belong in the [commonUtils appearance guide](../../Python/commonUtils/docs/development/reference/ui/appearance/appearance.md).
The mobile font-unit adapter applies to explicit Toga widget fonts; WebView CSS,
direct native font APIs and system default sizes keep their own units. Qt uses
its existing palette and font-role bindings. Native scrolling and scrollbars
remain toolkit-owned; transfer web scrolling is feature CSS.

Transfer action/status colors in `surface.css` and terminal-state overrides in
commonUtils `ui/tasks/process_progress.py` are separate defaults today. Changing
those colors or adopting a shared semantic role is a separate appearance change,
with light/dark, scaled-text and E Ink validation as applicable. Moving ownership
does not establish that the different controls should have identical styling.

## Desktop Workspaces details

### Desktop hover initialization

Desktop startup uses commonUtils' `initialize_q_app()`, including its macOS
window-entry and missing-move recovery. Main-window display also queues one macOS
activation after the first event-loop turn. This covers Home cards, File Browser and other Qt windows
through the shared event path. Hover colors remain owned by the theme and widget
styles. See commonUtils' desktop UI setup guide for the recovery contract and
`test_pointer_entry.py` for the synthetic missing-entry regression.

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
