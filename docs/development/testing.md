# Development and validation

## Python and dependencies

The existing launchers install `uv` when needed, select Python 3.12.2, and
synchronize [Python/pyproject.toml](../../Python/pyproject.toml) and its
[lockfile](../../Python/uv.lock) into the root `.venv`. Initial setup requires internet
access. [launch_config.ini](../../launch_config.ini) controls launcher paths; the entry
point is `Python/launch.py`. Feature-specific software and credentials are covered
in [configuration](../user/configuration.md).

Both application manifests pin PySide6 6.12.0. Regenerate `Python/uv.lock`
with `uv lock --project Python` after changing dependencies; CI exports it with
`--locked`. The published Qt wheels require macOS 14+, Linux glibc 2.34+ on
x86-64 or 2.39+ on ARM64, and Windows 10/11. Test runtime upgrades in a separate
environment before synchronizing the environment used by a running application.

## Testing

### Find the tests for your change

| Owner | Start with |
| --- | --- |
| Feature infrastructure | `Python/tests/test_feature_registry.py`, `test_feature_preferences.py`, `test_settings_page.py` |
| Desktop shell/documents | `Python/tests/test_main_window.py`, `test_document_workspace.py` |
| LM conversation lifecycle and presentation | `Python/tests/test_lm_session.py`, `test_lm_ui.py`, `test_lm_appearance.py` |
| Git history, search, preview and job ownership | `Python/tests/test_git_ui.py`, `test_git_preferences.py`, `test_git_repository_tabs.py`, `test_git_hunk_layout.py` |
| Blender presentation and operation lifecycle | `Python/tests/test_blender_page.py`, `test_blender_settings.py`, `test_blender_library.py` |
| Mobile Open/Save As and file management | `Mobile/tests/test_editor_picker.py`, `test_files_ui.py`, `test_private_sessions.py` |
| Mobile saved imports and window ownership | `Mobile/tests/test_saved_files.py`, `test_window_owners.py`, `test_workspace_ui.py` |
| Mobile source selection and import isolation | `Python/tests/test_mobile_packaging.py`, `test_mobile_portability.py`, `Mobile/tests/test_packaged_startup.py` |

The [mobile owner map](mobile-runtime.md) explains controller
and packaging boundaries. For focused desktop runs, pass a filename to the
regression runner's `--pattern`. Preserve the flat test layout: its isolated
mode requires a nonempty flat directory. Use the separate mobile environment
and [host validation commands](mobile-launchers.md#host-validation) for Toga
widget tests. Loopback fixtures need permission to bind localhost; native file
watchers also need functioning OS notification access.

The Windows platform runner starts with one native Qt startup smoke using the
`windows` platform plugin. It constructs the real public main window, applies
theme/font settings, runs its event loop and closes it under isolated preferences
and caches. Feature initialization hooks are excluded. Fatal startup exits report
the Windows exception code and Python faulthandler trace before running headless
regressions. Cleanup uses the shared Qt fixture lifecycle. Mixed-DPI monitor
crossings additionally need physical Windows hardware validation; synthetic
native-message tests cover the preservation policy on every CI host.
The startup smoke also checks the rendered application font against the shared
reference size. Shared styling tests measure text at 72, 96 and 120 font DPI and
verify that editor zoom persists the reference value. Launch-card tests exercise
the macOS conversion at maximum size and several window widths. Offscreen tests
alone use 96 DPI even on macOS, so native macOS font measurements remain relevant.
Native startup logs include Git history font, row and header metrics to distinguish
list density from screen scaling. Filesystem-refresh tests check that activity
settles without index writes; native watcher notification counts are not portable.

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
[cross-platform testing](platform-checks.md) for CI and platform details,
[UI architecture](features.md) for extension conventions,
and [maintenance notes](maintenance.md) for remaining validation gaps.

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

Platform checks also run on main pushes and launcher changes.

Release packaging stamps `.app-version.json` with the tag, packaged commit and
commit time, and includes its hash in the installed-file manifest. The desktop
launch label reads this managed file in ZIP installations and reads Git locally
in checkouts. Commit time identifies the source revision, rather than a variable
packaging timestamp. No release version file needs a manual edit.

The release workflow
calls those checks before packaging, so a tag cannot bypass failing application
regressions. Every release also calls the native mobile build and document runtime
workflows with both targets, using workflow files and source from the same release
commit. Packaging requires macOS, Windows and Linux desktop checks (including
Fedora and archive parity), Android and iOS native builds, and both mobile runtime
checks to succeed. Failed, cancelled or skipped prerequisites block packaging and
publication. A manual Source release run exercises these gates without publishing;
tag pushes publish only after they pass. Mobile gates cover the prototype and
portable core, not unported desktop features or physical-device interactions.
Standalone branch checks cannot cancel a release's mobile jobs, and tag runs
retain their validation.
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

Platform release checks with `--install` provision the platform’s pinned rclone
using archive and executable SHA-256 verification, then require the real synthetic
LocalCrypt regressions. They never access user remotes or credential packages.
Without that provisioning, local runs may skip crypt tests if rclone is absent.
Release provisioning uses the locked certifi CA bundle if `SSL_CERT_FILE` is not
already configured, including on macOS framework Python; TLS verification remains
enabled.
