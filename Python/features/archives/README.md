# Archives

Developer notes. See the [user guide](user_docs/index.md) for controls and setup,
and [UI architecture](../UI_ARCHITECTURE.md) for shared contribution conventions.

This feature contributes an **Archives** workspace and browser actions for
opening the manager, creating archives, and **Archives → Create encrypted ZIP…** to all Logistics
file browsers, including the Debug tab browser and comic library. Comics password support belongs to Comics and does not depend on this action
being enabled. `__init__.py:register()` declares the action; `ui/create_zip.py`
owns the dialog and captures input for shared ZIP workers. Browser wiring belongs
to [the central guide](../FILE_BROWSER.md).

## Workspace architecture

`__init__.py` contributes a lazy `archives.workspace` page and browser actions.
`ui/page.py` uses the generic `OperationProgress` worker and the Logistics password
service. It exposes `idle`, `can_close` and `prepare_close` for the main-window
lifecycle. Its workspace navigation order is 15, between sync actions and Git (20).
The rail paints a palette-aware zipper icon. Standalone browsers use the retained
host in `ui/window.py`, which defers closure until its worker stops.

`ui/create.py` captures a source basket, format, ZIP compression preset and optional
confirmed AES password. `backend.py` owns ZIP/TAR metadata, bounded text/image previews,
selected extraction and safe ZIP rebuilding. Shared ZIP creation, verification,
streaming, cancellation and metadata copying come from commonUtils. The shared
ZIP API accepts optional compression/level parameters and cancellable authentication;
existing callers keep their defaults.

Extraction stages the full selection, then reserves a new output directory with
exclusive `mkdir`. Validation happens before writing entry payloads. Failures and
cancellation discard the staging directory. Publication never replaces an existing
folder. ZIP edits preserve encryption, verify decrypted hashes and check the input
file identity before atomic replacement. They reject mixed protection and duplicate
additions. TAR creation uses bounded cancellable reads, rejects links/special files,
verifies staged hashes and refuses changed sources. No external executable is needed.
Supported format boundaries and shortcut keys are in the user guide.

Tests: `test_archive_workspace.py` exercises filesystem safety and ZIP/TAR operations;
`test_archive_workspace_ui.py` covers navigation, filtering, password retries,
shutdown, source options and rail placement. Shared ZIP tests cover presets and
cancellation during authentication.

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

## Validation

Use the [project test commands](../../../README.md#development).
`test_archive_password_ui.py` checks dialog/password behavior; commonUtils ZIP
creation tests check source validation, cancellation, verification and publication.
Keep this workflow's chunk-level cancellation separate from Comics' per-comic boundary.
