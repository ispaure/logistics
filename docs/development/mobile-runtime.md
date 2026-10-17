# Mobile host code

This package is the Toga application source. `Mobile/` owns builds, deployment
and native acceptance packaging. Start with the [code map](code-map.md)
and [mobile preparation guide](mobile-preparation.md).
User behavior belongs in [the mobile user guide](../user_mobile/user_mobile.md).

## Owners

| Change | Owner |
| --- | --- |
| Startup, navigation composition and managed text-document lifetime | `app.py` |
| Workspace identities, generations and sessions | `workspace.py`, `window_owners.py`, `window_scenes.py` |
| Adaptive panes and destination drawers | `workspace_navigation.py`, `adaptive_workspace.py` |
| Folder Hub sources and presentation | `folder_hub.py`, `local_sources.py`, `folder_hub_ui.py` |
| Local file management and comic batch entry points | `files_ui.py` |
| Text Open/Save As, picker widgets and pending bytes | `editor_picker.py` |
| Saved-import inventory and confirmed deletion | `saved_files_ui.py`: composed `SavedFilesController` |
| Explicit host dependencies and legacy state access | `host_services.py` |
| Managed text bytes, checkpoints and editing widgets | `documents.py` (host recovery), `features/text_editor/mobile/ui.py` (widgets) |
| Ordinary and provider reader ownership | `reader_sessions.py`, `private_sessions.py` |
| Reader-facing host services and shared controls | `reader_host.py`, `reader_controls.py`, `reader_chrome.py` |
| Device screen locking and sensitive-content protection | `screen_privacy.py` |

Format behavior and presentation remain with `features/books/mobile` and
`features/comics/mobile`. Cloud, managed collections and encrypted-copy adapters
remain with `features/rclone/mobile`. The host owns navigation, session policy and
workflow composition. Shared toolkit mechanisms remain in commonUtils.

## Open/Save As lifecycle

`app.editor_picker()` lazily creates one `EditorPicker` per host. It owns picker
widgets, rows, provider associations, source document, pending bytes, privacy gate
and cancellation. The app's existing picker methods/attributes delegate to that
owner for native probes and existing callbacks; they do not duplicate its state.
The controller explicitly enumerates host services with `HostService`; it has no
catch-all attribute forwarding. `files_ui.py` retains file-management behavior
and small compatibility delegates for picker entry points.

Provider selection and widget values are captured on the UI loop. Listing,
resolution, publication and verification run in worker threads using captured
models/values and a workflow-local cancellation event. The picker participates
in the host busy policy, but never takes over another workflow's `_crypt_cancel`.
Host Cancel dispatches to each relevant owner. Busy remains set until the picker
worker returns; a cancelled blocking call must still settle before reuse.

Worker results are checked against the owning host, picker epoch, credential
client/generation, navigation generation and source privacy gate. Late listings,
errors and resolved opens cannot replace newer state. Private catalog clearing,
host replacement and successful exit invalidate/clear picker state. Concealing
private content also cancels picker work. Cancellation can arrive after a file
was published; it does not imply that completed publication was rolled back.

Save As still publishes without overwriting, verifies the reopened bytes, and
retains its draft if reopening fails. `app.finish_save_as_source()` owns the
managed-document handoff after successful reopening; the picker cannot mutate
an editor widget through an implicit host attribute. Privacy gates follow the
exported provider session. Storage/cancellation correctness remains owned by the
existing resource operations, not a second implementation here.

## Saved imports and host composition

`app.saved_files()` composes `SavedFilesController`, replacing its former app
mixin. The controller owns inventory presentation/message state and explicitly
uses host reader/workspace services. Deletion still checks other windows and busy
readers before and after confirmation, retires affected sessions, and forgets
Recent/import mappings. Original sources and managed Local/LocalCrypt folders
are outside this workflow. Chat, Cloud, Transfers, Folder Hub, Home/Documents, Locations and Storage are now composed controllers. Their `METHODS` and `FIELDS` enumerate compatibility accessors; explicit host descriptors supply other dependencies. No catch-all attribute forwarding is used. The app retains document/provider lifecycle and reader manager integration.

## Packaging and verification

Add host modules to `Python/logisticsmobile/mobile_sources.json` and feature/service modules to their owning manifests in the same change as imports. `Mobile/tools.py` aggregates and validates these declarations.
`editor_picker.py` and `host_services.py` are explicitly staged. Do not edit
generated `Mobile/payload/` or Briefcase projects as application source.

| Contract | Tests |
| --- | --- |
| Picker ownership, cancellation, stale results, locked-source saving | `Mobile/tests/test_editor_picker.py` |
| Provider identity, Save As verification and reopen failures | `Mobile/tests/test_files_ui.py` |
| Private drafts, privacy handoff and delayed opens | `Mobile/tests/test_private_sessions.py` |
| Saved-import safety, other windows and reader retirement | `Mobile/tests/test_saved_files.py` |
| Window ownership, layout/navigation and paired panes | `Mobile/tests/test_window_owners.py`, `test_workspace_ui.py` |
| Payload completeness and portable imports | `Python/tests/test_mobile_packaging.py`, `test_mobile_portability.py` |

Use the [host validation commands](mobile-launchers.md#host-validation).
These are host contracts. Apple/Android picker layout, native Back and real
LocalCrypt transfer behavior still need the existing native acceptance scenarios
in `Mobile/native_tests/tests/logisticsmobile/localcrypt_checks.py`.

## Workflow controllers

`features/lm/mobile/controller.py` owns chat state; rclone owns cloud and transfer controllers. Host navigation workflows have dedicated `*_controller.py` modules. `services/workflow_host.py` supplies explicit read/write host attributes. `host_services.composed_workflow` installs only declared compatibility names. Transfer/review cancellation is independent from file/cloud cancellation; global Cancel dispatches to both. Ownership and cancellation are exercised by `Mobile/tests/test_workflow_ownership.py`.
