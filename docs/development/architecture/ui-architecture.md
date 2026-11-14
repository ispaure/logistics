# Screen and panel ownership

Application-wide guidance has moved to [developer documentation](../development.md):

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
| Mobile Settings → Markdown, Text or EPUB | `Python/mobile/settings/text.py` for Markdown and Text, `settings/epub.py` for EPUB | The EPUB reader opens the same EPUB form through `show_from_reader()` |
| Mobile Settings → Workspaces | `Python/mobile/settings/workspaces.py` | Storage and connection actions delegate to their existing owners |
| Mobile rclone connections → Credential Packages, Import credential ZIP and Unlock credential ZIP | `Python/features/rclone/mobile/credential_panels.py` builds the controls | `cloud_ui.py` presents the Settings routes. [Mobile credential import](../../features/rclone/development/credentials.md#mobile-credential-import) traces picker admission, workflow state and route retirement. |
| Mobile Settings → Help or About | `Python/mobile/settings/help.py`; installed-version content in `information.py` | Help/About share one module; their routes remain separate |
| Desktop Settings → Appearance & shared controls | `Python/desktop/settings/appearance.py:AppearanceSettingsPanel` | `desktop.pages.settings.SettingsPage._selected()` |
| Desktop Settings → Configuration | `Python/desktop/settings/configuration.py:ConfigurationPanel` | Same retained category host |
| Desktop Settings → Feature settings | `Python/desktop/settings/feature_settings.py:FeatureSettingsPanel` | Feature contributions supply lazy widgets and config files |
| Desktop Settings → rclone → Credential packages | `Python/features/rclone/ui/credential_panels.py` lays out the package list, selected details, loaded remotes and management controls | The personal credentials contribution opens `ui/page.py:RclonePage`, which owns discovery, unlock and close handling |
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

## Desktop and mobile ownership map

Start with the visible label or the action that opens the view. Paths in the
table are relative to `Python/`. Test names refer to the desktop suite in
`Python/tests/` and the mobile suite in `mobile_build/tests/`, unless stated
otherwise. Proposed moves describe review scope and leave route IDs and
registration with their current owners.

| Visible entry | Registration or launch → current presentation | Target and focused checks |
| --- | --- | --- |
| Desktop Home, File Browser, Workspaces, Documents, Workspace actions, Settings and Debug | `desktop/main_window.py` (`CORE_TABS` and launch methods) → `landing.py`, `file_browser.py`, `pages/folders.py`, `documents.py`, `folder_actions.py`, `pages/settings.py` and `pages/debug.py`; `navigation/catalog.py` projects launch targets to Home and the rail | Keep the destination views in the desktop shell and feature actions with their features. Check `test_document_launchers.py`, `test_folder_sources_ui.py` and `test_settings_page.py`. |
| Desktop Git, IDE, LM Chat, Notes Library, Blender, Aviation Tools, Links and Smart Home | Each feature's `register()` contributes a page to `MainWindow._populate_tabs()`; start with `features/<id>/ui/page.py` (IDs `git`, `ide`, `lm`, `notes_library`, `blender`, `aviation_tools`, `links`, `smart_home`) | Keep feature workspaces and panels under their feature's `ui/`. Split by visible panel where a workspace mixes distinct views. Check `test_feature_registry.py` and the feature's owner suite from `dev.py owners`. |
| Desktop Git → File status, History or Search | `features/git/ui/layout.py` assembles named views from `changes.py`, `history.py` and `search.py` beside it. The repository moves one `preview.py` widget between the three views | Keep panel layouts with their views and preview handoff with the repository. Check the Git owner suite with `dev.py test-owner git`. |
| Desktop Aviation Tools → Aircraft / Airports | The registered `features/aviation_tools/ui/page.py:AviationToolsPage` opens the retained window. `ui/dataset_browser.py:DatasetBrowser` owns the selector and read-only tables | Check `test_aviation_tools.py` for popup retention, legacy import compatibility and bundled dataset loading. |
| Desktop Settings → Blender → Presets → Addons, Installed files or Blue Hole | Blender's personal settings contribution opens `features/blender/settings.py:BlenderSettings`. Its Presets tab uses `ui/page.py:BlenderPage` in settings mode and builds these controls through `ui/addon_panels.py` | Keep preset panel presentation with Blender and save, launch and worker ownership with the page. Check `test_blender_page.py` and `test_blender_settings.py`. |
| Desktop Settings → Features, Reader history, Workspaces, File indexing, Open-source licenses and Feature settings | `desktop/pages/settings.py:_selected()` → `desktop/pages/features.py`, then `desktop/settings/{reader_history,workspaces,indexing,licenses,feature_settings}.py`; feature rows use `SettingsContribution` | Keep shell settings with the desktop host and contributed forms in feature `ui/`. Check `test_settings_page.py` and `test_feature_registry.py`. |
| Desktop Bulk Rename and folder/selection actions | `MainWindow._show_bulk_rename()` → `desktop/bulk_rename/`; `pages/folders.py` and `browser_menus.py` project registered folder tools and browser extensions into the shell | Keep Bulk Rename with its existing owner. Keep contributed dialogs and task views with their features, as with rclone Transfer. Check `test_folder_sources_ui.py` and the contributing feature's owner suite. |
| Desktop Open Documents, reader and editor launcher windows | `desktop/navigation/catalog.py:document_launchers()` → core Markdown via `services/documents/ui/markdown.py` and contributed Text, EPUB, Comics, PDF, Images, Video, Archives and Notebook launchers via feature registration; `desktop/documents.py` hosts attached views | Keep chooser and attachment behavior in the shell and format-specific chrome in the feature's `ui/`. Review common document adapters and the editor/notebook boundary with the document owners. Check `test_document_launchers.py` and `test_document_hosting.py`. |
| Mobile Home, Workspaces, Documents and Settings | `mobile/navigation.py:DESTINATION_ITEMS` → `mobile/app.py` destination callbacks and the shell views in the table above | Keep navigation, compact and wide pane placement, and shared document actions in the mobile shell. Check `test_navigation.py`, `test_workspace_navigation.py` and `test_hub_documents.py`. |
| Mobile Chat, Conversations, Model & server settings | Chat destination in `mobile/navigation.py` → `LogisticsMobile.show_chat()` via `ChatController`; Settings → LM Chat calls the same configuration route. Under `features/lm/mobile/`, `chat_settings.py` owns the native settings panel, `ui.py` owns the conversation view, `presentation.py` generates the transcript WebView, and `laptop.py` projects the retained views into the folded layout | Keep the distinct Chat settings and conversation owners. Check `test_chat_ui.py`, `test_on_device.py` and `test_settings_navigation.py`. |
| Mobile Settings → Features, Camera, Read aloud, Books & Comics (or PDF), LM Chat and Reset | `mobile/settings/categories.py:settings_sections()` builds shell categories and delegates to `feature_settings.py`, `features/images/mobile/burst_camera.py`, `settings/speech.py`, `magnifier.py`, `settings/reader_cover.py`, the Chat settings route and reset/saved files actions | Keep cross-feature preferences with the shell and feature-specific controls with their features. Review the registry's inline views for named modules as they grow. Check `test_settings_navigation.py`, `test_settings_ui.py` and `test_burst_camera.py`. |
| Mobile Books & Comics → Refresh, Import… or a configured folder | `mobile/reader_sessions.py:ReaderWorkspace.show_library()` → `Readers.show_catalog()` → `features/books/mobile/library/catalog_panel.py`; sibling `catalog.py` coordinates discovery and inventory | Keep catalogue controls with Books and route and reader lifetimes with the host. Check `test_library_catalog.py`, `test_library_inventory.py` and `test_reader_sessions.py`. |
| Mobile Notes Library, File storage, rclone connections, LocalCrypt and Transfer | `mobile/documents_hub.py` links Notes Library. Settings → Workspaces opens `mobile/storage_ui.py` and `features/rclone/mobile/cloud_ui.py`. LocalCrypt uses `features/rclone/localcrypt/mobile/ui.py`; Transfer is mapped above. Host adapters live in `mobile/composition/presentation.py` | Keep feature content and setup with its feature. Review credential and workspace panels with their owners. Check `test_hub_documents.py`, `test_connection_settings.py`, `test_localcrypt_ui.py` and `test_native_transfer_service.py`. |
| Mobile reading, playback and editing from Documents or Workspaces | `mobile/provider_opening.py` and `mobile/session_workflows/` dispatch into shared reader hosting and feature adapters in Books, Comics, PDF, Images, Video, Text Editor and Notebooks; Markdown preview uses `mobile/preview.py`, and the notebook canvas uses `features/notebooks/mobile/surface.py` | Keep common reader chrome in the shell and format-specific views with their features. Review editor and notebook moves after corpus validation. Check `test_reader_formats.py`, `test_reader_navigation.py` and `test_document_destinations.py` (desktop suite). |
| Mobile Burst camera, Saved files and Mobile documentation | Home → `features/images/mobile/burst_camera.py`; Settings → Reset or Help → `mobile/saved_files_ui.py` and `mobile/documentation_ui.py` | Keep capture feature-owned and the cross-feature utility screens with the shell. Check `test_burst_camera.py`, `test_settings_ui.py` and `test_mobile_packaging.py` (desktop suite). |

Use `ui/` for desktop feature views and `mobile/` for mobile feature views.
Add a `panels/` package only when grouping several distinct panels helps
navigation. Existing workflow groups such as rclone `transfers/` retain their
platform subdivisions. Review rehoming with the shipping owner when a move
affects discovery, package payloads or native build inputs.

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
| Transfer WebView typography, spacing, responsive controls and status colors | [Mobile transfer appearance](../../features/rclone/development/transfers.md#mobile-transfer-appearance) maps the CSS defaults and the palette, font and E Ink inputs from `mobile/surface.py`. |

Shared API contracts belong in the [commonUtils appearance guide](../../../Python/commonUtils/docs/development/reference/ui/appearance/appearance.md).
The mobile font-unit adapter applies to explicit Toga widget fonts; WebView CSS,
direct native font APIs and system default sizes keep their own units. Qt uses
its existing palette and font-role bindings. Native scrolling and scrollbars
remain toolkit-owned; transfer web scrolling is feature CSS.

### Trace a shared control

| Visible control | Application call site | Shared edit point |
| --- | --- | --- |
| Desktop progress and cancellation in Blender and rclone credential Settings | `features/blender/ui/page.py` and `features/rclone/ui/page.py` each construct `OperationProgress` and connect their own completion callback | commonUtils `ui/tasks/operation_progress.py` owns the progress widget, cancellation and worker lifetime |
| Mobile recycled rows in Chat’s Conversations and the Books & Comics catalogue | Both use `summary_list()` through the shell presentation adapters. `mobile/recycled_file_list.py` supplies the Logistics row appearance and icons | commonUtils `ui/native/recycled_list.py` and its platform adapters own row recycling and selection |

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

Edit [`Python/services/folders/appearance.py`](../../../Python/services/folders/appearance.py)
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

## Desktop appearance and startup checks

Settings Save retains the form, focus and scroll while updating inheritance and
conflict baselines. Explicit Reload rebuilds the form. LM compares effective
message appearance before reimporting Markdown. Books compares effective chapter
appearance, including reading fonts and the shared accent used by Slate.

To check an appearance change, use temporary settings and synthetic content.
Measure Save, theme application and event processing separately. Verify retained
form state and compare actual message or chapter imports after a relevant change
and after a repeat or unrelated notification. From the repository root:

```sh
python3 dev.py test shared test_layered_settings_editor.py
python3 dev.py test desktop test_lm_appearance.py
python3 dev.py test desktop test_books_reader.py
```

For startup profiling, record imports, feature initialization, main-window
construction and first show separately. Compare default and populated sessions
with the same instrumentation. Before changing lazy page construction, measure
startup and memory and check feature toggles, direct IDE/file opening, close
guards and background task ownership. Use platform checks for native rendering.
