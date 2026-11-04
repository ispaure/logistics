# Archives development

Archives contributes a desktop document launcher and browser actions. See the
[desktop guide](../user/user.md) for workflows and
[mobile boundary](../user_mobile/user_mobile.md) for unsupported controls.
Follow the [browser extension contract](../../../development/file-browser.md)
and [feature conventions](../../../development/features.md) when changing it.

## Ownership

| Source under `Python/features/archives/` | Responsibility |
| --- | --- |
| `__init__.py` | Lazy Archives document launcher, browser controller factory, selection actions and activation predicates |
| `ui/browser.py` | Per-browser routing and scoped refresh after workspace mutations |
| `ui/window.py` | Retained document identity, duplicate-open reuse and worker-safe closure |
| `ui/page.py` | Commands, enabled state, operation outcomes and mutation signals |
| `ui/session.py` | One background operation, credential resolution, queued retries and shutdown |
| `ui/chrome.py` | Toolbar, location, contents requests and shortcuts |
| `ui/create.py`, `ui/dialogs.py` | Source basket, format options, extraction destination and removal confirmation |
| `ui/create_zip.py` | Separate configured-password encrypted-selection dialog |

Reusable archive validation, staging, publication, metadata and preview APIs belong
to commonUtils. Its canonical documentation is
[Archive operations](https://github.com/ispaure/commonUtils/blob/main/docs/development/reference/archives/archives.md)
and [ZIP access](https://github.com/ispaure/commonUtils/blob/main/docs/development/reference/archives/zip_access.md).
Keep those API contracts in that repository; Logistics owns configuration,
credentials, UI, routing and notifications. The shared passive contents view owns
navigation and decoded display, not filesystem writes or password prompts.

## Registration and browser routing

`register()` declares four selection actions: open manager, extract, create archive
and create encrypted ZIP. Open/extract are available when at least one selected
path is supported; the controller filters unsupported paths. Activation accepts
supported archives except `.cbz`, leaving comic activation to Comics. Explicit
Archives actions remain available for CBZ. Passive **Archive Contents** details
are shared file-model hooks and do not require Archives to be enabled.

`open_archive_window` reuses a live document with the same absolute opened or
requested path, including while its first header read is pending. The application
hosts it in Documents when available; independent browsers can use a standalone
window. Each archive retains its own page/session. Closing the originating browser
stops its controller from routing or refreshing, while retained documents remain
usable. Feature disablement removes new admission through launchers/actions;
existing documents and jobs retain their lifetime.

Successful workspace create/edit/extract operations emit `archive_changed` on the
GUI thread. The originating controller calls `refresh_item` and `refresh_changed`
for the parent only when the path lies inside the browser's library. Failure and
cancellation emit no mutation signal. The separate `CreateZipDialog` action has a
different compatibility path: its `finally` block refreshes the invoking browser
after the dialog returns, including cancellation.

## Operations and shutdown

`ArchiveSession` rejects another start while busy or closing. Busy includes queued
password retries as well as active workers. Worker calls resolve credentials;
GUI callbacks open the validated password dialog and schedule a retry with a Qt
owner context. Dismissing that prompt reports cancellation and restores controls.
Closing sets `closing`, clears queued retries and requests cooperative worker
cancellation. `ArchiveWindow` defers destruction until idle. Completed operations
must not queue another header refresh after closure starts.

`ArchivePage` preserves the current archive when another open fails. Create/edit
success queues a header refresh and emits the saved path; extraction emits the
new directory. ZIP/CBZ enable editing; TAR disables it. Create/edit/extract/test
outcomes produce desktop notifications; opening and previewing do not.

## Password policy and the two creation flows

`services.documents.zip_passwords` owns `remoteConfig.ini` inheritance and the
memory-only verified-password cache. The nearest `[LogisticsZIP]` section wins;
a missing or empty explicit `archive_password` stops inheritance. Other sections
do not stop the walk. `[DEFAULT]` values are ignored and interpolation is off.
INI parsing trims surrounding whitespace. Configuration stores plaintext;
interactive passwords are not written back. Verified replacements are remembered
under their new file identity for subsequent workspace actions.

The source basket (`NewArchiveDialog`) captures ZIP/TAR options and asks for a
confirmed password when AES protection is selected. It does not select the new
password from per-source INIs. `CreateZipDialog`, reached through **Create encrypted
ZIP…**, instead resolves a configured password for every selected source. It
rejects conflicting configured passwords before starting a job. If any source
lacks one, its confirmed fallback must match any configured password in the
selection. It keeps its dialog alive until cancellation has stopped the worker.
Publication is the success boundary; late cancellation does not undo a saved ZIP.

The validated desktop unlock dialog keeps wrong-password retries in the same
prompt, clears the input and restores focus. Enter is consumed by its event filter
to submit once. Authentication runs through its progress worker, rather than on
the GUI thread.

## Mobile boundary

`Python/services/mobile_features.py` lists the mobile feature catalogue without
Archives, and maps ZIP and comic suffixes to Comics. Archives has no
`mobile_sources.json` or mobile adapter. `Python/mobile/files_ui.py` offers an
archive-password input for reader access, not Archive manager operations. Mobile
book/comic readers and their native archive adapters have separate owners; their
tests do not validate a general mobile Archive manager.

## Validation scope

Review these Logistics test owners when changing the corresponding behavior:

| Test under `Python/tests/archives/` | Contract covered |
| --- | --- |
| `test_archive_workspace_ui.py` | Navigation/preview, invalid-open preservation, GUI credential retry/cancel, active-worker and queued-retry closure, source options, TAR editing state, retained document launcher and replacement password reuse |
| `test_archive_browser.py` | Actual BrowserView registration, ZIP/TAR activation, CBZ precedence, selection actions, direct extraction, success-only workspace refresh, feature toggles and document-host routing |
| `test_archive_password_ui.py` | Configured encrypted creation, conflicting passwords and prompt cancellation before a job starts |
| `test_archive_zip_creation_lifecycle.py` | Suggested output names, folder roots, password confirmation and cancellation without destroying a live worker |

Credential-package publication tests live in
`Python/tests/resources/test_credential_archive.py`; Comics retry tests have their
own owner. Shared commonUtils archive tests own low-level format and publication
contracts. Use [project test selection](../../../development/testing.md) for
execution; these desktop integration tests require Qt.

This documentation audit reviewed source and test definitions only during the
release quiet hold. It did not run Qt, builds, emulators or device acceptance.
Test coverage descriptions above are not a fresh passing-run claim.
