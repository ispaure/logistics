# Development and validation

## Python and dependencies

The existing launchers install `uv` when needed, select Python 3.12.2, and
synchronize [Python/pyproject.toml](../../Python/pyproject.toml) and its
[lockfile](../../Python/uv.lock) into the root `.venv`. Initial setup requires internet
access. [launch_config.ini](../../launch_config.ini) controls launcher paths; the entry
point is `Python/launch.py`. Feature-specific software and credentials are covered
in [configuration](../../CONFIGURATION.md).

Both application manifests pin PySide6 6.12.0. Regenerate `Python/uv.lock`
with `uv lock --project Python` after changing dependencies; CI exports it with
`--locked`. The published Qt wheels require macOS 14+, Linux glibc 2.34+ on
x86-64 or 2.39+ on ARM64, and Windows 10/11. Test runtime upgrades in a separate
environment before synchronizing the environment used by a running application.

## Testing

Run the regression suite from the repository root:

```sh
# macOS / Linux
PYTHONPATH=Python .venv/bin/python Python/tests/run_regressions.py Python/tests --isolate-modules
```

On Windows PowerShell, set `$env:PYTHONPATH = "Python"` and run `.venv/Scripts/python.exe Python/tests/run_regressions.py Python/tests --isolate-modules`.

For both repositories' suites and the historical comic compression comparison,
use the same project interpreter:

```sh
.venv/bin/python Python/tests/run_platform_checks.py
```

On Windows, use `.venv/Scripts/python.exe Python/tests/run_platform_checks.py`.
The runner configures the import path and headless Qt automatically. See
[cross-platform testing](../../Python/tests/PLATFORM_CHECKS.md) for CI and platform details,
[UI architecture](features.md) for extension conventions,
and [maintenance notes](../../Python/MAINTENANCE.md) for remaining validation gaps.

Tests cover application startup, contributions, local fixtures and simulated
failures. Desktop interaction, real remote transfers/mounts, external applications
and installed drivers require separate validation.

## Correctness checks and test ownership

Normal launchers synchronize runtime dependencies only. Install developer tools
with `UV_PROJECT_ENVIRONMENT=.venv uv sync --project Python --locked`, then run
`.venv/bin/ruff check --config Python/pyproject.toml Python .github/scripts`.
The initial lint policy checks syntax and correctness without forcing a formatting
rewrite. `commonUtils.tests.qt_test_case.QtTestCase` gives GUI tests ownership of
new windows: it requests worker shutdown, drains deferred deletion and deletes
windows before the next test. Use its `temporary_directory()` for GUI filesystem
fixtures so windows and watchers are destroyed before their directories are
removed, including on assertion failures. Register fixture-specific cleanup after
creating the directory. Use `wait_until()` for condition-based Qt waits with
operation-specific timeout messages. Tests must not depend on windows retained by
other tests. See the [shared test guide](../../Python/commonUtils/tests/README.md)
for lifecycle details.

Platform checks also run on main pushes and launcher changes. The release workflow
calls those checks before packaging, so a tag cannot bypass failing application
regressions. Both headless suites and historical archive parity must pass.
New pushes and PR updates cancel superseded checks for the same branch/PR;
tag releases and manual runs retain their validation. Windows platform checks
collect browser screenshot diagnostics alongside their logs. The separate browser
diagnostic workflow remains available manually and does not repeat on every push.
Publish a commonUtils commit before pushing a Logistics commit that references it;
an unavailable submodule revision fails checkout before any test runs.

The platform runner isolates both shared and Logistics test modules in separate
processes to prevent native Qt state from leaking between suites. Each regression
process uses a private temporary directory index, so browser tests do not compete
with the running application’s cache or leave test paths in its persistent index.
