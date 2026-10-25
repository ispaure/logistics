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

Start with `test_document_preparation.py`, `test_feature_boundaries.py`, `test_editor_resource_picker.py`, `test_folder_safety.py` and `test_folder_sources_ui.py` in `Python/tests/`, plus mobile picker/workspace/packaging checks. Use the recursive runner or `dev.py` selectors; test files live under the subject folders listed in the [test map](testing.md#desktop-test-folders).

## Typed mobile presentation ports

`services/mobile_presentation.py` declares toolkit-independent callable protocols
for icon construction, icon application, Markdown previews and font binding.
`services/documents/mobile_reading.py` gives reader dimensions and validity checks
explicit signatures. Native widget values stay opaque (`Any`); these contracts do
not import Qt/Toga. Feature-specific connection dependencies are declared by
`ConnectionHost` beside the SMB workflow. Broader factories retain their existing
call shapes until their own workflows are extracted.

## Desktop document page transitions

`services.documents.ui.page_transition` owns the Logistics readers' short,
content-only outgoing-page overlay. EPUB, PDF and comic owners capture the last
successful display immediately before replacing it. The live destination paints
behind the overlay; PDF rendering can finish asynchronously without capturing an
empty destination frame. The overlay passes input through, cancels on rapid
turns/resize/hide/close, and releases its pixmap on completion. Initial loads,
failed loads and unchanged pages do not start a slide. EPUB restores QTextEdit's
paginated layout after grabbing the outgoing spread and before committing a turn.

## Detached Folder Hub projection

`services.folders.catalog` is the pure shared desktop/mobile projection owner.
Adapters supply `FolderCopy` descriptors with physical identity, logical name,
credential-source identity, category, availability and lock state. `project_catalog`
groups logically by `(source_identity, name)`, physically by copy identity, or by
name for mobile Workspaces. Workspaces treats a shared remote name across
credential packages as the same folder and keeps its displayed name unchanged. It
retains input preference order and deduplicates equal physical copies within a
group. A projection is available if any copy is available and locked only if all
copies are locked. This metadata projection performs no discovery, credential
loading or storage access.

`CredentialScope` retains the full supplied package identity, rather than its
label or basename. Two equal display names do not establish a shared source.
Desktop `services.folders.workspaces` and mobile `folder_hub` adapt their existing
discovery results to this catalog. The host still filters visibility, owns caches,
revokes credentials and approves operations; a projected row is not permission
to open or mutate storage. Focused checks include `test_folder_catalog`,
`test_folder_sources_ui`, mobile Folder Hub and credential invalidation tests.

The desktop `FolderTreePresentation` adapter keeps source/category/legacy
filtering and ordering in `_selected_entries`, Qt item/copy-label construction
in `_render_entries`, and selection restoration in `refresh`. Rendering clears
and repopulates the same tree with the same signals, tooltips, grouping and
physical entry keys. Discovery and catalog ownership remain unchanged.

## Personal path defaults

`services.personal_paths.get_marc_dropbox_root()` owns the historical personal Dropbox default used for rclone credential discovery. It preserves the Windows B-drive probe and the home-directory fallback. The shared library has no personal Dropbox configuration.


## Mobile document view retirement

`services.documents.mobile_views.retire_webview` owns the document privacy policy
used by notebook canvases and Text Editor/Notes views. It disposes font bindings,
detaches memory-only private views before clearing them, and clears a live iOS
web document before replacement navigation. Features import this shared policy
directly; notebooks do not depend on the Text Editor feature. The service is in
the mobile source allowlist and has no GUI or feature imports at module load.
