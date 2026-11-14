# Screen and panel ownership

## Find a screen by its visible name

Start with the label in the table. If it appears in more than one place, find
its registration or host first, then follow the factory to the widget, window
or renderer. Source paths below are relative to `Python/`. Test names can be
passed to `python3 dev.py test desktop`, `mobile` or `shared` as indicated.

Keep cross-feature navigation, window lifetime and registration projection in
`desktop/` and `mobile/`. Keep feature panels, controllers and assets with
their feature, using `features/<owner>/ui/` for Qt and
`features/<owner>/mobile/` for native mobile. Add a subfolder when a workflow
has several pieces to find together (for example, transfer review and progress).
The host supplies capabilities such as artwork, provider access and navigation
through the adapter. Portable services own behavior and data. Reusable controls
belong under the appropriate toolkit in commonUtils.

### Desktop

`desktop/main_window.py:CORE_TABS` mounts the core pages.
`desktop/navigation/catalog.py:LaunchCatalog` projects enabled
`PageContribution` declarations into `desktop/landing.py` and
`desktop/sidebar.py:DestinationRail`. For a contributed label, search for its
declaration in the feature and follow the lazy factory. The same page can be
shown in a standalone window; the chooser and rail are shell presentation.

| Visible label or entry point | Current owner and next edit point | Desktop check |
| --- | --- | --- |
| Home, File Browser | `desktop/{landing,sidebar,file_browser}.py`; core entries in `LaunchCatalog.CORE` | `test_main_window_navigation.py`, `test_file_browser_window.py` |
| Workspaces → Sources, Info, Actions; Bulk Rename | `desktop/pages/folders.py`, `desktop/pages/workspace_panes.py` and `desktop/folder_controller.py` mount provider and action contributions; `desktop/folder_actions.py` owns the workflow host and `desktop/bulk_rename/` owns the rename UI | `test_folder_sources_ui.py`, `test_main_window_navigation.py` |
| New / Open Document, Read & edit, Open Documents | `desktop/landing.py:DocumentChooser` and the rail use `catalog.py:document_launchers` (built-in Markdown and registered `DocumentLauncherContribution` entries). `desktop/documents.py` owns retained docks; the selected feature owns the document and its controls | `test_document_launchers.py`, `test_document_hosting.py` |
| Settings → Features, Appearance & shared controls, Configuration, Feature settings, Reader history, Workspaces, File indexing, Open-source licenses | `desktop/pages/settings.py:SettingsPage` → `desktop/settings/{appearance,configuration,feature_settings}.py`. `desktop/pages/features.py` owns Features; settings sibling modules own the other built-in panels. A registered `SettingsContribution` owns its feature widget and scope | `test_settings_page.py` |
| Logistics → Tool Settings; Help / Guides | `desktop/header_menus.py` routes to `SettingsPage.show_feature` or `services/documentation.py:open_guide` | `test_settings_page.py`, `test_documentation_viewer.py` |
| IDE, Links, Smart Home | `features/{ide,links,smart_home}/ui/page.py`; IDE registers in `__init__.py`, Links and Smart Home in `ui_contributions.py` | `test_ide.py`, `test_smart_home.py`, `test_main_window_navigation.py` |
| Git; Git preferences | `features/git/__init__.py:register` → `ui/page.py:GitPage` or `ui/application_settings.py:GitPreferencesPanel` | `test_git_ui_actions.py`, `test_git_preferences.py` |
| Blender → Settings → Presets | `features/blender/settings.py:BlenderSettings` mounts `ui/page.py:BlenderPage` in settings mode; `ui/addon_panels.py` presents preset add-ons and `addons/ui/page.py` owns the Addon Library | `test_blender_page.py`, `test_blender_settings.py` |
| Aviation Tools → Aircraft / Airports | `features/aviation_tools/__init__.py:register` → `ui/page.py:AviationToolsPage.open_tool` → `ui/dataset_browser.py:DatasetBrowser` | `test_aviation_tools.py` |
| Workspaces → Cloud → Pull; transfer progress and credential packages | rclone contributes actions and views. Follow the [transfer path](../../features/rclone/development/transfers.md#find-desktop-transfer-controls) to `features/rclone/transfers/ui/progress.py`; package controls live in `features/rclone/ui/credential_panels.py` | `test_transfer_adapters.py` |
| Markdown, Notebook (.rmdoc), Notes Library | Markdown enters via `services/documents/ui/markdown.py` and commonUtils `ui/markdown/window.py`. Notebook enters via `services/documents/ui/notebooks.py` → `features/notebooks/ui/workspace.py:CanvasPage` (Qt WebEngine and feature `assets/`). Notes Library uses `features/notes_library/ui/{page,document,dataview}.py` (Qt and isolated script worker) | `test_document_launchers.py`, `test_notes_library_desktop.py` |
| EPUB Reader, Comic Reader, PDF Reader, Video Player | `features/{books,comics,pdf}/ui/reader.py` (comics opens through `ui/reader_opening.py`) and `features/video/ui/player.py`. Desktop EPUB uses Qt rich text | `test_books_reader.py`, `test_comic_reader.py`, `test_pdf_reader.py` |
| Text Editor, Image Viewer, Archives; LM Chat | Openers are in `features/{text_editor,images,archives}/`; LM Chat registers in `features/lm/__init__.py` and uses `ui/{page,conversation_view}.py` (Qt rich text) | `test_document_launchers.py`, `test_lm_appearance.py` |

### Mobile

`mobile/navigation.py:DESTINATION_ITEMS` maps visible tab names to IDs
(`Workspaces` is `files`). `mobile/app.py:select_destination` dispatches
through `mobile/{routes,workspace_navigation}.py`. Native shell layout,
retained stacks and Back behavior belong to the host. Mobile Settings has
its own lazy category declarations in `mobile/settings/categories.py`.

| Visible label or entry point | Current owner and next edit point | Mobile check |
| --- | --- | --- |
| Home, Documents | `mobile/{home,documents_hub,hub_controls}.py`; `hub_ui.py` retains sessions and reopen | `test_navigation.py`, `test_document_navigation.py` |
| Workspaces, browser heading, drawer | `mobile/{workspaces_screen,browser_location,file_drawer}.py`; `folder_hub_ui.py` owns discovery and workflows | `test_workspace_navigation.py`, `test_files_ui.py` |
| Home → New Document, Open Document; editor Save As | `mobile/home.py` offers New and Open; `document_choices.py` selects formats and `files_ui.py` handles browser opens. `document_destination_form.py` and `editor_picker.py` own the New/Open/Save As form and state | `test_document_navigation.py`, `test_storage_reader_opening.py` |
| Settings → Appearance, App, Privacy & Security, Workspaces, Help; Text, Markdown, EPUB | `mobile/settings/{appearance,app,privacy_security,workspaces,help,text,epub}.py`. Accent, audio and trusted Wi-Fi have sibling modules; EPUB Reader reuses its Settings form | `test_settings_navigation.py`, `test_settings_ui.py` |
| Settings → Features, Camera, Read aloud | `mobile/settings/categories.py:SettingsCategories` mounts feature toggles from `mobile/feature_settings.py`, camera controls from `features/images/mobile/burst_camera.py`, and the voice setting | `test_settings_ui.py` |
| Settings → Books & Comics (or PDF), Video, LM Chat, Reset, About | `SettingsCategories` assembles magnifier and `reader_cover.py` options, routes to `video.py` and Chat settings, mounts history and playlist reset controls, and delegates About to `help.py` | `test_settings_ui.py`, `test_settings_navigation.py` |
| Settings → Help → Mobile documentation; Saved files | `mobile/documentation_ui.py` (built on commonUtils `ui/native/markdown.py:MarkdownWikiView`), `mobile/saved_files_ui.py` | `test_documentation_ui.py`, `test_saved_files.py` |
| Cloud credential packages and unlock; Workspaces → Transfers | `features/rclone/mobile/{cloud_ui,credential_panels}.py`; `mobile/transfer_status.py` mounts the shortcut to `features/rclone/transfers/mobile/{ui,review_ui,surface,native_fallback}.py`. `transfers/assets/surface.{html,css,js}` supplies the offline WebView | `test_credential_packages.py`, `test_mirror_ui.py`, `test_transfer_feedback.py` |
| Chat → Model & server settings, Conversations | `features/lm/mobile/ui.py:ChatUI` → `chat_settings.py:ChatSettingsPanel`; `presentation.py` owns the embedded transcript, `laptop.py` the server connection UI | `test_chat_ui.py`, `test_chat_dom.py` |
| Documents → Libraries → Notes; Markdown | `mobile/documents_hub.py` → `mobile/notes_discovery.py` → `features/notes_library/mobile/{notes_library,library_panels,library_opening,library_document}.py`. Host capabilities are composed in `mobile/composition/presentation.py`; shared Markdown authoring is in `services/documents/authoring/markdown_editor.py` | `test_notes_library.py`, `test_markdown_library_workflow.py` |
| PDF opened from a file or provider; Contents / Search | `mobile/provider_opening.py` → `mobile/provider_view.py` supplies host artwork to `features/pdf/mobile/canvas.py`; `contents.py` and `search.py` own dialogs, `continuous.py` and `scroll_script.py` the continuous WebView | `test_pdf_reader.py`, `test_pdf_scroll.py` |
| Books & Comics → Refresh / Import…; EPUB and comic readers | `mobile/{reader_ui,reader_sessions}.py` mounts `features/books/mobile/library/{catalog_panel,catalog}.py`. EPUB content uses `features/books/mobile/{content,provider_reader,text_reader}.py`; comics use `features/comics/mobile/reader_controller.py` | `test_library_catalog.py`, `test_reader_cohesion.py` |
| Notebook; Burst camera | `features/notebooks/mobile/documents.py` opens `panel.py:NotebookPanel` and `surface.py` loads its embedded `features/notebooks/assets/`. `features/images/mobile/burst_camera.py` owns capture | `test_notebook_native_tools.py`, `test_navigation.py` |
| Text editor → Edit / Preview; video playback | `mobile/managed_documents.py` mounts `features/text_editor/mobile/ui.py`. `mobile/preview.py` uses `services/documents/authoring/markdown_*.py` for Markdown. `mobile/document_sources.py` routes video to `features/video/mobile/{player,ios,android}.py` | `test_markdown_editor.py`; native `video_ui_probe.py` |

For a label outside these routes, use the [feature catalog](../../features/features.md)
and the [extension points](extension-points.md) to find its declaration. For
provider opens, follow [provider to reader](document-storage.md#trace-a-mobile-provider-reader).
For new mobile Python or embedded assets, update the owning
`mobile_sources.json` and run `test_mobile_packaging.py` (desktop) and
`test_packaged_startup.py` (mobile).

## Try the lookup on each platform

| Platform | Kind | Start at the visible control and follow its owner |
| --- | --- | --- |
| Desktop | Feature panel | **Aviation Tools → Aircraft / Airports**: find its page declaration, then `AviationToolsPage.open_tool` and `DatasetBrowser`. `test_aviation_tools.py` checks popup reuse. |
| Desktop | Shell screen | **Workspaces → Sources / Info / Actions**: find the core page in `MainWindow`, then follow `FoldersPage` and the controller. `test_folder_sources_ui.py` checks source selection and contributions. |
| Desktop | Shared widget | **Cancel** in a Cloud transfer: follow the rclone progress adapter to commonUtils `ui/tasks/process_progress.py:ProcessProgressWindow`. Run shared `test_process_progress.py` for cancellation and close behavior. |
| Mobile | Feature panel | **Chat → Model & server settings**: find the action in `ChatUI` and its form in `ChatSettingsPanel`. `test_chat_ui.py` and native `chat_settings_probe.py` exercise the panel and return path. |
| Mobile | Shell screen | **Workspaces**: follow the `files` destination to `WorkspacesScreen` and the frame in `workspace_navigation.py`. `test_workspace_navigation.py` checks retained browsing and Back. |
| Mobile | Shared widget | **API key (session only)** in Chat settings: follow `ChatSettingsPanel` to commonUtils `ui/native/password_input.py:PasswordInput`, also used by the mobile credential forms. Run shared `test_native_password_input.py` for the control contract. |

## Add or change a Settings panel

1. Add a visibly named mobile module in `mobile/settings/` and reuse `forms.py`.
   Register its lazy factory, icon and feature/camera gates in `categories.py`.
   `SettingsNavigation` retains the page per window. Category titles are route
   IDs, so check callers and restored selection when renaming.
2. Put defaults/validation in `preference_schema.py`, persistence/migrations in
   `preferences.py`, and register new mobile files in the owning source manifest.
3. Add desktop application panels in `desktop/settings/` and wire `SettingsPage`.
   Feature panels use [SettingsContribution](extension-points.md#feature-settings).
   Preserve scope, close vetoes and the `CommonUtilsPanel` alias.
4. Run `python3 dev.py test mobile 'test_settings*.py'`,
   `python3 dev.py test desktop test_settings_page.py` or
   `python3 dev.py test desktop test_mobile_packaging.py` for the affected panel
   and manifest. Check native focus, layout and gestures separately.

## Appearance and shared control edit points

| Change | Owner and default |
| --- | --- |
| Qt light/dark palette, native buttons and scrolling | commonUtils `ui/appearance/theme.py`: opt-in Slate uses Qt Fusion, a palette and a shared stylesheet. Buttons and padding use that stylesheet; native scrollbars inherit the Qt style. |
| Qt interface, browser, reading and code fonts | commonUtils `ui/appearance/styling.py:STYLE_FIELDS` supplies families and sizes. An empty family selects the runtime font for the role. `typography.py:point_size` adapts the 96-DPI reference to the display. |
| Mobile semantic colors and native controls | `services/appearance_palette.py` owns light/dark roles and the default accent. `mobile/{palette,appearance}.py` maps them to UIKit/Android colors, button roles and E Ink treatment. Native scroll views keep platform behavior unless a route owns an override. |
| Mobile text size, button dimensions and forms | `mobile/preference_schema.py` sets saved text sizes; `mobile/ui_metrics.py` sets native text roles and the 48-point/dp touch target. `font_scaling.py` applies saved reader sizes. `mobile/settings/forms.py` supplies Logistics row styles and delegates fitting to commonUtils `ui/native/forms.py`. |
| Progress, cancellation and status | commonUtils `ui/tasks/operation_progress.py` handles worker-driven desktop actions (Blender and rclone); `ui/tasks/process_progress.py` displays process stats and cancellation. Mobile transfer uses its own review and progress model with WebView and native presentations. |
| Embedded rendering | `services/appearance_palette.py:css_variables` and `mobile/palette.py` expose mobile web colors; transfer `assets/surface.css` keeps its compatibility fallbacks and scroll layout. Notebook `assets/{base,theme,desktop,mobile}.css`, Markdown authoring `markdown_style.py` and Chat `presentation.py` own their specific rendering and CSS units. |

Reuse the control when the input, cancellation and accessibility contracts
match. For example, a worker progress footer and a subprocess file list share
semantics but have different data and retirement callbacks. Keep saved native
font preferences and CSS dimensions in their respective units.

[Shared appearance APIs](../../../Python/commonUtils/docs/development/reference/ui/appearance/appearance.md)

### Shared locked/unlocked folder artwork

Edit `services/folders/appearance.py` paths, fills, stroke and state colors.
`desktop/pages/workspace_icons.py` and `mobile/control_icons.py` render them.
Keep distinct shapes and accessible labels for monochrome. Regenerate passive
mobile PNGs for geometry changes and commit them with the source:

```sh
.venv/bin/python mobile_build/build_support/generate_folder_icons.py
.venv/bin/python mobile_build/build_support/generate_folder_icons.py --check
```

## Check appearance changes

Use disposable preferences and synthetic content. Separate time in Settings
Save, theme application and event delivery. Verify a relevant update rerenders
LM or Books, and a repeated or unrelated notification avoids reimporting content.
Run from the repository root:

```sh
python3 dev.py test shared test_layered_settings_editor.py
python3 dev.py test desktop test_lm_appearance.py
python3 dev.py test desktop test_books_reader.py
```

When profiling startup, measure imports, feature initialization, main-window
construction and first show separately, with both empty and populated state.
For lazy-page changes, check direct file/IDE opens, toggles, safe close and
background ownership.

## Check ownership and packaging

Run `python3 dev.py architecture` and `python3 dev.py test desktop test_portable_imports.py`
when a move changes imports. The [portable owner policy](architecture.md#portable-owner-policy)
and `test_architecture_contracts.py` check reviewed feature-to-host edges
and prevent mobile feature adapters from importing the application host.
Use [test ownership](../testing/testing.md) to select the workflow suites.
A host test can check dispatch, retention and assets; use the
[platform suites](../testing/platform-checks.md) for native focus, scaling,
touch, Back and WebView behavior.

Notes owns Files and Links in `features/notes_library/mobile/drawers.py`,
with native swipe binding in `drawer_gestures.py` and animation in
`drawer_motion.py`. `mobile/composition/presentation.py:notes_drawer_host`
supplies the current window, fold geometry, appearance, overlays, scroll
clearance and privacy gate. The native reader host applies bottom clearance
through a view callback. See the [Notes lifecycle](../../features/notes_library/development/development.md#files-and-links-drawers)
for the open, Back and disposal paths.

## Desktop Folder Hub requests

`folder_controller.py` captures source/detail request generations. `FoldersPage`
resolves declarations on the GUI thread, runs I/O and availability in workers,
and rejects stale/revoked results before mounting. Private tools must declare
backend-aware support. Info and Actions retain separate content under Sources.
[Folder source contract](features.md#remote-folder-source-context)

Shared Qt initialization owns hover recovery. `services.seasonal.snow_enabled`
owns the December 15–January 2 season and high-contrast exclusion.
`desktop.snow.SnowOverlay` stops drawing for inactive/minimized windows.
