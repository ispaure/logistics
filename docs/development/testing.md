# Development and validation

## Set up a checkout

From a fresh clone:

```sh
git clone --recurse-submodules https://github.com/ispaure/logistics.git
cd logistics
```

For an existing checkout with missing shared files, use
`git submodule update --init --recursive` after preserving any submodule edits.
Read [AGENTS.md](../../AGENTS.md) for repository conventions. Open the platform
launcher listed in the [root README](../../README.md#get-started) to run the desktop
app. An editor can open the repository root; `Python/` is the application import
root, not a second checkout.

The existing launchers install `uv` when needed, select Python 3.12.2, and
synchronize [Python/pyproject.toml](../../Python/pyproject.toml) and its
[lockfile](../../Python/uv.lock) into the root `.venv`. Initial setup requires internet
access. [launch_config.ini](../../launch_config.ini) controls launcher paths; the entry
point is `Python/launch.py`. Feature-specific software and credentials are covered
in [configuration](../user/configuration.md).

The desktop manifest pins PySide6 6.12.0. Mobile uses its own Briefcase manifest
and Toga backends; it does not use desktop Qt. Regenerate `Python/uv.lock`
with `uv lock --project Python` after changing dependencies; CI exports it with
`--locked`. The published Qt wheels require macOS 14+, Linux glibc 2.34+ on
x86-64 or 2.39+ on ARM64, and Windows 10/11. Test runtime upgrades in a separate
environment before synchronizing the environment used by a running application.

## Run everyday checks

The root [dev.py](../../dev.py) selects the suite's environment, sets import paths
and headless backends, and delegates to the existing runners. It works from any
working directory when invoked by its path. It does not install dependencies or
build/deploy an app. From the repository root, use `python3` on macOS/Linux or
`py` on Windows; this bootstrap Python only needs the standard library.

Install the pinned desktop environment and developer tools with uv. These commands
explicitly target the root `.venv`, so activation is unnecessary. The desktop
launcher installs uv if needed.

```sh
# macOS / Linux
UV_PROJECT_ENVIRONMENT="$PWD/.venv" uv sync --project Python --locked --python 3.12.2
```

```powershell
# Windows PowerShell
$env:UV_PROJECT_ENVIRONMENT = "$PWD/.venv"
uv sync --project Python --locked --python 3.12.2
```

Then run the smallest relevant check:

```sh
python3 dev.py test desktop test_feature_registry.py
python3 dev.py test desktop 'test_git_*.py'
python3 dev.py test desktop test_documentation_layout.py
python3 dev.py lint
```

Replace `python3` with `py` on Windows. Quote wildcard patterns so the shell does
not expand them. Omit the filename/pattern to run the whole selected suite.
No matching files is an error. Each test file runs in a fresh process; failing
files or timeouts fail the command. The helper returns the check's exit status.
Lint covers `dev.py`, `Python`, `Mobile` and `.github/scripts`, matching CI's scope.

For **mobile host tests**, use a separate environment, without installing a
native SDK or Briefcase just to run dummy-backend checks:

```sh
# macOS / Linux; use py -3.12 and Mobile/.venv/Scripts/python.exe on Windows
python3.12 -m venv Mobile/.venv
Mobile/.venv/bin/python -m pip install toga-dummy==0.5.7 markdown-it-py==4.2.0 pygments==2.19.2 pypdf==6.21.0 -r Mobile/requirements-testflight.txt
python3 dev.py test mobile test_editor_picker.py
```

The helper uses root `.venv` for desktop/lint and `Mobile/.venv` for mobile,
including Windows `Scripts/python.exe` paths. For a differently located environment,
append `--python /path/to/python`. Append `--dry-run` to inspect the command without
running it. Mobile tests use `TOGA_BACKEND=toga_dummy`; desktop tests use offscreen
Qt. These checks do not certify native appearance or interactions. See the
[mobile handbook](mobile-handbook.md) when you need an actual device build.

## Make your first change

1. Find your workflow in the [code map](code-map.md), then read its owning user
   guide and developer module/test map.
2. Follow the registration factory or mobile callback to the implementation.
   A compatibility forwarding module is a pointer, not the place to add behavior.
3. Change the smallest owning module. For mobile imports, update the owner's
   `mobile_sources.json` and run `python3 dev.py test desktop test_mobile_packaging.py`.
4. Run the focused tests below, then `python3 dev.py lint`. UI changes also need
   interaction checks on the affected platform.
5. Update the owning documentation using the [hierarchy rules](documentation-hierarchy.md).
   Review `git diff` and `git status` so generated output and unrelated work stay
   out of your change.

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
and packaging boundaries. For focused runs, use `dev.py test desktop <filename>` or
`dev.py test mobile <filename>`. Preserve the flat test layout: its isolated
mode requires a nonempty flat directory. The runner puts the selected suite first
on the import path so mobile and desktop files with the same test-module name
cannot shadow each other. Use the separate mobile environment
and [host validation commands](mobile-launchers.md#host-validation) for Toga
widget tests. Loopback fixtures need permission to bind localhost; native file
watchers also need functioning OS notification access.

Run the complete desktop suite from the repository root with
`python3 dev.py test desktop` (`py dev.py test desktop` on Windows).
For the complete mobile host suite, use `python3 dev.py test mobile`.

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

Normal launchers synchronize runtime dependencies only. Use the environment setup
above to install developer tools, then run `python3 dev.py lint` (`py` on Windows).
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

## CI, release gates and advanced validation

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
Native app UI runs allow 25 minutes per iOS device, including Briefcase's cold
simulator startup and installation, and 40 minutes on Android. Hosted Android
software rendering has reached the dark-theme audit after all 32 core cases at
the former 25-minute deadline; the complete run also checks light appearance and
native Back. Each native build job has a 60-minute overall budget. The large 256 MiB
LocalCrypt seeding fixture allows four minutes for review revalidation and
transfer; smaller reviews retain their 30-second budget. Complete native case
reports and exact source identity are required before a gate can pass.
The iOS host retains each fresh cache result as `ios-native-ui-cached.json` before
validation, along with its fresh `ios-native-ui-error.txt` traceback. These are
diagnostics, not passing evidence. Failure diagnostics target the device recorded
for the current run, so an iPad failure cannot be hidden behind an earlier iPhone
report or collected from the wrong simulator.
A complete native stdout report passes the same case and source validation before
any simulator-container lookup. This avoids failing a completed native suite when
CoreSimulator becomes unresponsive after app exit. Missing stdout reports still
require a fresh, complete cache result; a structured failed report cannot fall
back to a successful cache.
Native WebView probes retry only the transient `WKErrorDomain Code=5` evaluation
error during document replacement. A successful string result must contain the
expected replacement text and exclude retired private content; repeated errors,
other failures and non-string results still fail the bounded check.

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
