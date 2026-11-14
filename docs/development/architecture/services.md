# Logistics host services

Paths below are under `Python/services/`. Keep portable policy importable
without Qt, Toga or the mobile application.

| Change | Owner |
| --- | --- |
| Permission, protection and resume | `{access_policy,protection,session_auth}.py`; [privacy](access-privacy.md) |
| Provider I/O, previews, desktop editor handoffs | `documents/`, `documents/ui/`; [document sessions](document-storage.md) |
| Source discovery, exclusions, destructive checks | `folders/`, with desktop indexing in `folders/ui/` |
| Baseline markers and hunk review | `editors/ui/` shared by IDE and Text Editor |
| Appearance, provisioning or Help | `appearance_palette.py`, `software.py`, `updates.py`, `documentation.py` |

`MobilePresentation` injects icons, font binding, previews, favourites and fold
geometry through portable callable protocols. `workflow_host` supplies explicit
host/state aliases. `mobile.composition.assembly.composed_workflow` creates one
lazy controller per app, installs declared compatibility names and rejects
competing aliases. Keep mutable state on the controller.
Check `test_workflow_ownership.py`.

`folders.catalog` projects descriptors by logical, physical or mobile name
identity. Credential scope uses full package identity. Availability requires one
available copy; lock requires all copies locked. The caller still owns filtering,
discovery and admission. Providers declare encrypted names. Case-insensitive
exclusions apply whole-name rules to remotes and suffix rules to both.
Check `test_folder_catalog.py` and `test_folder_policy.py`.

`documents.page_visits.PageVisits` owns 100 session-only page visits and retires
Back on successful display. `documents.ui.page_transition` overlays the last
painted page during successful turns. `documents.mobile_views.retire_webview`
detaches memory-only views and clears native content before replacement.

Use backend-independent `DocumentProtection` and explicit protected roots.
rclone supplies its own LocalCrypt policy adapter. Run
`python3 dev.py test-owner document-services` for storage, wrapper restrictions,
resume, screen/audio and payload contracts.

For a folder-catalog change, follow desktop `services.folders.workspaces` or
mobile `folder_hub` from discovered copies to `project_catalog`. Capture two
copies with the same display name and distinct package identities. Run
`python3 dev.py test desktop test_folder_catalog.py` and expect identity,
deduplication and lock state to follow the requested grouping. The stable
physical key drives UI selection restoration. Run `test_folder_sources_ui.py`
for the provider discovery and encrypted-name snapshot handoff.

`documents.file_preview` owns preview admission and memory-only content.
The library supplies contained provider paths and retains its document lifetime.
`services.personal_paths.get_marc_dropbox_root()` owns the historical Windows
B-drive and home-directory fallback used by rclone discovery.
