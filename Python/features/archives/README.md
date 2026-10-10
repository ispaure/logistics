# Archives

Developer notes. See the [user guide](user_docs/index.md) for controls and setup,
and [UI architecture](../UI_ARCHITECTURE.md) for shared contribution conventions.

This feature contributes the **Archives** workspace and declarative browser
opening, extraction and creation actions. Browser installation follows
[the central guide](../FILE_BROWSER.md); the generic host contains no archive
format checks or feature-specific window routing. Comics password support and
comic-reader activation remain independent of Archives.

## Responsibilities

| Location | Responsibility |
| --- | --- |
| `__init__.py` | Lazy page, controller, action and activation declarations |
| `ui/browser.py` | Per-browser routing, independent hosts and mutation refresh |
| `ui/page.py` | Commands, operation outcomes and main-window lifecycle |
| `ui/session.py` | Background jobs, configured/session credentials, GUI retries and cancellation |
| `ui/chrome.py` | Workspace toolbar, location, status and shortcuts |
| `ui/create.py`, `ui/dialogs.py` | Source/options capture, destination and removal prompts |
| `ui/create_zip.py` | Existing configured-password encrypted-selection dialog |
| `ui/window.py` | Retained independent host with deferred worker-safe closure |
| `commonUtils.archives` | Reusable ZIP/TAR operations and metadata |
| `commonUtils.ui.archive_view` | Passive contents navigation and previews |

`backend.py` keeps compatibility imports; it has no archive implementation.
The shared [archive guide](../../commonUtils/ARCHIVES.md) documents formats,
validation, publication, preview bounds and public APIs. Existing low-level ZIP
callers retain their defaults and extraction behavior.

## Browser flow

Enabled browser bindings install `ArchiveBrowserController` through
`BrowserExtension.create_controller`. ZIP and supported TAR activation opens the
manager in the current main window's contributed page. CBZ activation stays with
Comics, with explicit Archives actions available in the comic library and generic
browsers. Ordinary files and folders offer creation actions; supported archives
also offer **Open archive manager…** and **Extract archive…**. Multiple selected
archives can use separate retained windows.

Routing uses the invoking host and a live contributed tab. It does not search
unrelated application windows or resurrect hidden disabled pages. Standalone and
detached browsers use independent hosts when no local contributed page exists.
Controllers retain and reuse their standalone host; independent windows own
and cancel their workers, while the main page participates in main-window
`prepare_close`/`idle` handling. Feature toggles remove actions and activation
without deleting existing jobs or open windows.

Successful creation, editing and extraction emit `archive_changed` on the GUI
thread. The invoking binding invalidates the affected file and reconciles its
parent through `refresh_item` and `refresh_changed`, within the browser's library
scope. Failures and cancellations emit no mutation notification. Passive archive
information uses `ArchiveFile.browser_panels` on the existing preview worker;
headers never prompt for a password.

## Workspace lifecycle

`ArchiveSession` owns one `OperationProgress` job, includes queued credential
retries in its busy state and schedules callbacks with a Qt owner context.
Passwords are resolved in the worker; entry prompts and retries run on the GUI
thread. Verified replacements are remembered under their new file identity.
Closing cancels work and prevents queued retries or refreshes from restarting it.
The contents widget only displays validated entries and decoded previews and
emits requests; it does not own jobs, credentials or filesystem writes.

Workspace navigation order 15 places Archives after sync actions and before Git
(20). The rail paints a palette-aware zipper icon. The page preserves Logistics'
shared theme and works in light and dark modes.

## Validation

Shared tests cover archive formats, staging, traversal/collision checks, source
changes, encryption, cancellation, file hooks and the passive contents view.
`test_archive_workspace_ui.py` covers Logistics jobs, credentials, shutdown,
source options and rail placement. `test_archive_browser.py` installs the actual
feature into a Logistics `BrowserView` and checks activation, CBZ reader precedence,
selection menus, direct extraction, refresh, toggles and standalone routing.
The existing browser and Comics regression suites check compatibility.

## Password configuration

Place this in `remoteConfig.ini` beside a file or inside a selected folder:

```ini
[LogisticsZIP]
archive_password = change-me
```

`services.zip_passwords.configured_password` walks ancestors. The nearest INI
containing `[LogisticsZIP]` wins. Other sections do not stop the search; an empty
or missing `archive_password` in that section stops inheritance. Interpolation is
disabled, so percent signs work. `[DEFAULT]` passwords are ignored; the password
must be an explicit key in `[LogisticsZIP]`. INI syntax trims surrounding whitespace; use a
password without leading/trailing whitespace. The INI stores plaintext: keep real
passwords out of Git and limit access to the configuration.

## Creation and verification

Creation uses the configured password, or asks for a nonempty password and matching
confirmation when any selected item has no configured password. The entered password
is not saved to the INI. A ZIP has one password: conflicting configured passwords,
or an entered fallback different from a selected item's configured password, require
separate ZIPs. Sources are never deleted and existing outputs are never overwritten.
Selected folders keep their own root directories. Unsafe paths, symbolic links,
colliding names and outputs inside sources are rejected. Files are AES-256 encrypted,
verified by decrypted hashes before publication. Filenames are visible without a
password. Creating ZIPs is distinct from comic image recompression and does not
change input bytes.

Reusable ZIP operations live in [commonUtils](../../commonUtils/ZIP_ARCHIVES.md).

The destination must be outside selected folders even when reached through a
symbolic-link alias. Existing destinations created by another operation during
verification are retained, and source changes abort publication. Ordinary empty
directories have no secret payload and may have unencrypted directory headers;
their names are visible like all ZIP member names.

## Progress and cancellation

ZIP creation uses the shared background progress widget. The dialog reports
assessment, source hashing, streaming creation and verification. **Cancel ZIP
creation**, Escape or closing the dialog requests cancellation between chunks,
including while verifying. Temporary archives are discarded; sources and existing
destinations are retained. Cancellation is checked once more before publication.
The dialog stays alive until its worker has stopped; failures and cancellation
leave it open with an explanation. Completion after publication remains success.

Use the [project test commands](../../../README.md#development).
`test_archive_password_ui.py` checks the legacy dialog/password behavior;
commonUtils ZIP and archive tests check source validation, cancellation, verification
and publication.
Keep this workflow's chunk-level cancellation separate from Comics' per-comic boundary.
