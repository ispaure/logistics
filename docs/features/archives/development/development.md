# Archives development

Archives browses, creates and extracts archives on Qt desktop. Use the
[desktop guide](../user/user.md) for the supported formats and controls.

## Try an extraction menu change

Put a ZIP containing only `notes.txt` in a disposable folder. In desktop
**File Browser**, right-click the ZIP and choose **Extract archive…**. Select
a new output folder inside the browser's library. The file appears inside
that folder and the archive page reports the destination. Enable **Archives**
in **Settings → Features** if the action is missing.

To clarify that the action extracts every entry, try changing its label to
**Extract entire archive…** in `register()` in
`Python/features/archives/__init__.py`. Keep the `extract_archive` action ID
and `_extract` callback. Update the matching menu labels in
`Python/tests/archives/test_archive_browser.py`, including the CBZ menu
assertion, and relaunch the app to see the new label.

Run the focused routing check from the repository root using the
[desktop environment](../../../development/setup/getting-started.md).

```sh
python3 dev.py test desktop --exact-file Python/tests/archives/test_archive_browser.py
```

Expect the renamed action to appear on supported archives, including CBZ.
Triggering it on the synthetic TAR publishes `notes.txt` with its original
contents and refreshes the output item and its parent once. Failed and cancelled
extracts preserve the sources and leave the browser refresh callbacks untouched.

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

Reusable archive validation, staging, publication, metadata and preview APIs
belong to commonUtils. See
[Archive operations](https://github.com/ispaure/commonUtils/blob/main/docs/development/reference/archives/archives.md)
and [ZIP access](https://github.com/ispaure/commonUtils/blob/main/docs/development/reference/archives/zip_access.md).
Logistics owns configuration, credentials, UI, routing and notifications. For
registration changes, use the [browser extension contract](../../../development/architecture/file-browser.md)
and [feature conventions](../../../development/architecture/features.md).

## Registration and browser routing

`register()` supplies the **Archives** card in **New / Open Document…** and
four File Browser actions. The card calls `launch` to show a file picker, then
`open_archive_window`. In File Browser, open and extract appear when at least
one selected path is a supported archive. `ArchiveBrowserController.open`
filters the selection and calls `ArchivePage.extract_path` for direct
extraction. Comics handles CBZ double-clicks, and explicit Archives actions
remain available for CBZ. The shared file-model hook supplies passive
**Archive Contents** even when Archives is disabled. That view displays headers
and decoded previews, and leaves write operations and password prompts to
the workspace.

`ui/window.py:open_archive_window` reuses a live, non-closing document by its
current absolute archive path. It falls back to the initial requested path only
while no archive has been admitted, including pending or failed initial opens.
After a successful switch, opening the old path opens or reveals a document for
that path. Each document retains its page and worker session in Documents or in
a standalone window. Closing the originating browser stops its controller from
routing and refreshing. Open documents and running jobs remain usable after
browser closure or feature disablement.

Successful workspace create, edit and extract operations emit
`archive_changed` on the GUI thread. For output inside the browser's library,
the originating controller calls `refresh_item` on the output and
`refresh_changed` on its parent. The separate `CreateZipDialog` action
refreshes the invoking browser when the dialog returns, including cancellation.

## Operations and shutdown

`ArchiveSession` rejects another start while busy or closing. Busy includes queued
password retries as well as active workers. Worker calls resolve credentials;
GUI callbacks open the validated password dialog and schedule a retry with a Qt
owner context. Dismissing that prompt reports cancellation and restores controls.
Closing sets `closing`, clears queued retries and requests cooperative worker
cancellation. `ArchiveWindow` defers destruction until idle. Completed operations
must not queue another header refresh after closure starts.

`ArchivePage` preserves the current archive when another open fails. Create and
edit success emit the saved path and queue a header refresh. Extraction emits
the new directory. ZIP and CBZ enable editing, and TAR disables it. Successful
ZIP edits replace the verified archive. Use a disposable copy to test edits.
Create, edit, extract and integrity-check outcomes produce desktop notifications.

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
| `test_archive_failure_cleanup.py` | Actual creation fixtures retain an intentional assertion while cancelling and retiring active workers, removing their fixtures and exiting without a native abort |
| `test_archive_worker_progress.py` | A fresh-process cold encrypted creation retains the actual fixture's five-second wait and payload/source assertions while the GUI admits a Python worker under a controlled GIL-contention schedule |

Use managed fixture scopes for dialogs that own workers so failed assertions
still cancel and retire the worker. When a creation wait fails, read the last
progress phase and the running/finished flags to localize the failure in the
worker or in queued GUI retirement.

Credential-package publication tests live in
`Python/tests/resources/test_credential_archive.py`; Comics retry tests have their
own owner. Shared commonUtils archive tests own low-level format and publication
contracts. Use [project test selection](../../../development/testing/testing.md) for
execution. These desktop integration tests require Qt.
