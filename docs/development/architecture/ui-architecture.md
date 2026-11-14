# Screen and panel ownership

## Find a screen by its visible name

Paths are relative to `Python/`. Desktop labels the category **Appearance &
shared controls**. Mobile uses **Appearance**. Follow the category host to
the panel and then its palette or typography adapter.

| Screen | Presentation owner |
| --- | --- |
| Desktop Settings → Appearance & shared controls, Configuration, Feature settings | `desktop/settings/{appearance,configuration,feature_settings}.py`, mounted by `desktop/pages/settings.py:SettingsPage` |
| Desktop Files, Workspaces, Open Documents | `desktop/file_browser.py`, `desktop/pages/folders.py`, `desktop/documents.py` |
| Desktop Bulk Rename and workspace actions | `desktop/bulk_rename/`, `desktop/folder_actions.py` |
| Mobile Home, Documents | `mobile/{home,documents_hub,hub_controls}.py`; `hub_ui.py` retains sessions and reopen |
| Mobile Workspaces, browser heading, drawer | `mobile/{workspaces_screen,browser_location,file_drawer}.py`; `folder_hub_ui.py` owns discovery/workflows |
| Mobile New/Open/Save As | `mobile/document_destination_form.py`; `editor_picker.py` owns state and publication |
| Mobile Settings → Appearance, App, Privacy & Security, Workspaces, Help | `mobile/settings/{appearance,app,privacy_security,workspaces,help}.py`; accent, audio and trusted Wi-Fi use sibling modules |
| Mobile Settings → Text, Markdown, EPUB | `mobile/settings/{text,epub}.py`; EPUB Reader reuses its Settings form |
| Credential packages and unlock | `features/rclone/{ui,mobile}/credential_panels.py`; desktop owner `ui/page.py`, mobile owner `mobile/cloud_ui.py` |
| Transfer and review | `features/rclone/transfers/ui/progress.py` on desktop, `transfers/mobile/{ui,review_ui,surface,native_fallback}.py` on mobile |
| Mobile Chat, Conversations, Model & server | `features/lm/mobile/{ui,presentation,laptop,chat_settings}.py` |
| Mobile Books & Comics library | `features/books/mobile/library/{catalog_panel,catalog}.py` |
| Mobile Burst camera, Saved files, Help viewer | `features/images/mobile/burst_camera.py`, `mobile/{saved_files_ui,documentation_ui}.py` |

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

| Change | Owner |
| --- | --- |
| Qt palette, fonts, buttons | commonUtils `ui/appearance/` |
| Semantic native colors and web CSS variables | `services/appearance_palette.py`, `mobile/{palette,appearance}.py` |
| Native sizes and form fitting | `mobile/{ui_metrics,font_scaling}.py`, commonUtils `ui/native/forms.py` |
| Feature transfer styling | [Mobile transfer appearance](../../features/rclone/development/transfers.md#mobile-transfer-appearance) |

Native Toga font adaptation applies to explicit widget fonts. CSS and native
fonts keep their own units. For a shared-control trace, follow Blender or rclone
`ui/page.py` to commonUtils `ui/tasks/operation_progress.py`. Inspect appearance
Save with temporary settings. Expect the form, focus and scroll to remain,
and LM/Books to rerender when effective content styling changes.
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

## Desktop Folder Hub requests

`folder_controller.py` captures source/detail request generations. `FoldersPage`
resolves declarations on the GUI thread, runs I/O and availability in workers,
and rejects stale/revoked results before mounting. Private tools must declare
backend-aware support. Info and Actions retain separate content under Sources.
[Folder source contract](features.md#remote-folder-source-context)

Shared Qt initialization owns hover recovery. `services.seasonal.snow_enabled`
owns the December 15–January 2 season and high-contrast exclusion.
`desktop.snow.SnowOverlay` stops drawing for inactive/minimized windows.
