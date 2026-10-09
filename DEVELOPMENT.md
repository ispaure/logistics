# Developing Logistics


`Python/features/` owns feature logic and feature-specific UI; `Python/ui_new/` hosts the generic interface; `Python/models/` and `Python/services/` provide folder models and discovery support. `Python/commonUtils/` is a Git submodule. See [UI architecture](Python/features/UI_ARCHITECTURE.md) for contribution and configuration conventions, and [file browser development](Python/features/FILE_BROWSER.md) for panels, context actions and activation. `Scripts/` contains standalone scripts.

## Python and dependencies

The existing launchers install `uv` when needed, select Python 3.12.2, and
synchronize [Python/pyproject.toml](Python/pyproject.toml) and its
[lockfile](Python/uv.lock) into the root `.venv`. Initial setup requires internet
access. [launch_config.ini](launch_config.ini) controls launcher paths; the entry
point is `Python/launch.py`. Feature-specific software and credentials are covered
in [configuration](CONFIGURATION.md).

## Testing

Run the regression suite from the repository root:

```sh
# macOS / Linux
PYTHONPATH=Python .venv/bin/python -m unittest discover -s Python/tests -v
```

On Windows PowerShell, set `$env:PYTHONPATH = "Python"` and run `.venv/Scripts/python.exe -m unittest discover -s Python/tests -v`.

For both repositories' suites and the historical comic compression comparison,
use the same project interpreter:

```sh
.venv/bin/python Python/tests/run_platform_checks.py
```

On Windows, use `.venv/Scripts/python.exe Python/tests/run_platform_checks.py`.
The runner configures the import path and headless Qt automatically. See
[cross-platform testing](Python/tests/PLATFORM_CHECKS.md) for CI and platform details,
[UI architecture](Python/features/UI_ARCHITECTURE.md) for extension conventions,
and [maintenance notes](Python/MAINTENANCE.md) for remaining validation gaps.

Tests cover application startup, contributions, local fixtures and simulated
failures. Desktop interaction, real remote transfers/mounts, external applications
and installed drivers require separate validation.

## Single application instance

`launch.main()` initializes Qt, then acquires a per-user QLockFile in the shared
commonUtils Temp directory before initializing features or constructing a window.
The lock path is shared across checkouts. Duplicate launches use commonUtils.ui
for an informational dialog and return exit status 0. Real lock I/O failures remain
errors. Ownership lasts through the event loop and is released in `finally`, even
when startup fails. Qt's long-lived-lock timeout is disabled, so an old live owner
is retained while dead process owners can be detected. See the
[Qt lock documentation](https://doc.qt.io/qt-6/qlockfile.html).

## Startup failures

Contribution categories are validated before pages are created, so a settings
entry in a folder-source list fails with a clear feature/category error. MainWindow
tracks each successfully created page as it builds the UI. If a later constructor
fails, it requests worker shutdown and drains a Qt event loop before destroying
the window and re-raising the original error. Shared index cancellation also
handles workers that have exited before their queued GUI completion is delivered.

The macOS launcher supports the system Bash 3.2. Pause flags use portable,
case-insensitive case patterns; avoid Bash 4 lowercase parameter expansion there.

## Text Editor

The independent feature and its application document lifecycle live in
`Python/features/text_editor`; its [developer guide](Python/features/text_editor/README.md)
explains module boundaries, limits and tests. Reusable text-file IO and code-editor
widgets belong to the existing commonUtils submodule. Pygments 2.19.2 is pinned
in the same project/lockfile; no separate editor environment is introduced.
