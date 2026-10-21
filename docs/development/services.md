# Logistics host services

Application policies and orchestration live here. Reusable mechanisms and their API documentation stay in commonUtils.

| Owner | Responsibility |
| --- | --- |
| `services/documents/` | Provider readers, archive access, document limits, ZIP password policy and portable preparation |
| `services/documents/ui/` | Desktop document pickers, window handoffs, privacy guards and password dialogs |
| `services/folders/` | Folder entries, source aggregation, visibility and destructive-operation safety |
| `services/folders/ui/` | Desktop index service lifetime |
| `services/editors/ui/` | Shared IDE/Text Editor baseline markers and hunk review |
| `services/{local_storage,preferences}.py` | Local storage and preference policy |
| `services/{software,updates,build_version}.py` | Provisioning, updates and build identity |
| `services/{workflow_host,mobile_presentation}.py` | Explicit feature-to-host composition contracts |
| `services/documentation.py` | Application help entry points |
| `services/ally_integration.py` | Optional external host activation |

Portable document preparation must import without Qt, Toga or the mobile application. Feature-specific format rules stay with Books/Comics; encrypted storage and bounded Markdown resource loading stay with rclone. Hosts retain window/navigation, publication and recovery policy.

Start with `test_document_preparation.py`, `test_feature_boundaries.py`, `test_editor_resource_picker.py`, `test_folder_safety.py` and `test_folder_sources_ui.py` in `Python/tests/`, plus mobile picker/workspace/packaging checks. Tests retain their current flat discovery layout.

## Typed mobile presentation ports

`services/mobile_presentation.py` declares toolkit-independent callable protocols
for icon construction, icon application, Markdown previews and font binding.
`services/documents/mobile_reading.py` gives reader dimensions and validity checks
explicit signatures. Native widget values stay opaque (`Any`); these contracts do
not import Qt/Toga. Feature-specific connection dependencies are declared by
`ConnectionHost` beside the SMB workflow. Broader factories retain their existing
call shapes until their own workflows are extracted.
