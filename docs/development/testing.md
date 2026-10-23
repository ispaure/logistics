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

Run `python3 dev.py doctor` for read-only interpreter, package, submodule and
optional native-tool diagnostics. It does not read credential files or change an
environment. A nonzero status means a contributor prerequisite is missing.

The root [dev.py](../../dev.py) selects the suite's environment, sets import paths
and headless backends, and delegates to the existing runners. It works from any
working directory when invoked by its path. The `setup` command installs declared host dependencies; test, lint and doctor
do not build or deploy an app. From the repository root, use `python3` on macOS/Linux or
`py` on Windows; this bootstrap Python only needs the standard library.

For repeatable setup, run `python3 dev.py setup desktop` or
`python3 dev.py setup mobile` (use `py` on Windows). Both accept `--dry-run`.
The desktop setup uses the existing uv lock and root `.venv`. Mobile setup creates
`mobile_build/.venv` if absent and installs the hash-locked host test requirements
additively, preserving any native build tools already present. It needs no native
SDK. Setup needs uv and network access for uncached packages.

The equivalent desktop command installs the pinned environment and developer tools with uv. These commands
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
Lint covers `dev.py`, `Python`, `mobile_build`, `Scripts` and `.github/scripts`, matching CI's scope.
The Ruff configuration retains its default environment/cache exclusions and
explicitly excludes mobile build, payload, log, deployment-workspace and downloaded
toolchain trees, plus the external feature link. New, untracked application and
test source is still checked; lint selection does not depend on the Git index.

For **mobile host tests**, use a separate environment, without installing a
native SDK or Briefcase just to run dummy-backend checks:

```sh
# macOS / Linux; use py -3.12 and mobile_build/.venv/Scripts/python.exe on Windows
python3 dev.py setup mobile
python3 dev.py test mobile test_editor_picker.py
```

The helper uses root `.venv` for desktop/lint and `mobile_build/.venv` for mobile,
including Windows `Scripts/python.exe` paths. For a differently located environment,
append `--python /path/to/python`. Append `--dry-run` to inspect the command without
running it. Mobile tests use `TOGA_BACKEND=toga_dummy`; desktop tests use offscreen
Qt. These checks do not certify native appearance or interactions. See the
[mobile handbook](mobile-handbook.md) when you need an actual device build.

### Shared-library test matrix

Use the same entry point for commonUtils:

```sh
python3 dev.py test shared
python3 dev.py test shared test_streams.py
python3 dev.py test shared 'test_native*browser*.py' --dry-run
```

The full command runs the Qt/portable shared suite in `.venv`, then replays
`tests/native/test_native*.py` in `mobile_build/.venv` with Toga dummy. Each file
still runs in an isolated process with disposable storage. Native replay uses
the intersection of that native filename family and the requested filename/glob;
a portable-only selection needs no mobile environment. The Qt host-admission
fixture `test_qt_mobile_host.py` stays in the Qt leg. The two legs overlap and
their case counts are not distinct coverage to add together.

For custom environments, `--python PATH` selects the shared Qt interpreter and
`--native-python PATH` selects its native interpreter. Both selected interpreter
paths are checked before starting either leg. Missing PySide6, Toga or Toga dummy
fails its required leg before discovery, rather than silently accepting skipped
toolkit tests. Both legs run after a test failure; the command preserves the
first nonzero result. No environment is installed or modified by this command.
Use the existing desktop/mobile setup commands if either environment is absent.

Native filesystem notification access is required for real watcher tests.
Localhost fixture servers and Qt WebEngine also need the host's socket and
process capabilities. A restricted sandbox can cause permission failures or
watcher timeouts; recheck with those capabilities and disposable profiles before
classifying them as source regressions. Do not remove watcher assertions, extend
timeouts or turn unavailable required dependencies into successful skips.
Platform-specific Windows/case-sensitive-filesystem skips remain explicit, and
Toga dummy results do not certify device appearance or native interactions.

The regression runner isolates application storage and cache directories. When
using Playwright's downloaded browsers for DOM tests, set
`PLAYWRIGHT_BROWSERS_PATH` to the same explicit directory during browser installation
and test execution. The platform workflow sets this path during installation and
persists it through `GITHUB_ENV` so later fixture subprocesses can find browser
tooling after application caches are isolated.

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

### Desktop test folders

`Python/tests/` groups regression contracts by subject. Filename selection through
`dev.py` and the isolated runner searches these folders recursively; keep that
selection when a guide does not need to name an individual test class.

| Folder | Responsibility |
| --- | --- |
| `application/` | Startup, feature registration, preferences and host shell |
| `files/` | Folder Hub, file browser, indexing and Bulk Rename |
| `readers/` | Books, PDF and shared document reading workflows |
| `editing/` | Text editing, notes and resource pickers |
| `resources/` | Credentials, encrypted storage, remote sessions and transfers |
| `integrations/` | External service and application adapters |
| `comics/` | Comic archives, compression, library and reading state |
| `images/` | Image conversion, color, staging and folder tools |
| `archives/` | Archive browsing, authentication and workspace presentation |
| `version_control/` | Git backend and UI workflows |
| `chat/` | LM conversations, generation, streaming and storage adapters |
| `ide/` | IDE layout, browser, navigation and search |
| `blender/` | Blender integration, library, metadata and operation UI |
| `tooling/` | Build, documentation, architecture and runner contracts |

The 23 root `test_mobile*.py` profiles remain at their established paths because
the independent portable testbed consumes them. Root fixture and driver files
also retain their paths: they are shared inputs, not extra subject groups.
Desktop cross-group imports name `tests.<owner>` explicitly; shared contracts use
`commonUtils.tests.<owner>`. The shared test owner map lives in
[commonUtils](../../Python/commonUtils/docs/reference/tests/tests.md).
The small package initializers enable recursive standard `unittest discover`
and contain no setup or runtime registration.

### Find the tests for your change

Use `python3 dev.py owners` to list developer guides, then
`python3 dev.py test-owner books --dry-run` to inspect an owner's test selection.
Remove `--dry-run` to run it across the appropriate desktop/mobile environments.
`Scripts/ownership.json` owns these source, guide, manifest and test associations;
update it when moving an owner or renaming tests. Archive, reading, chat, provider
and storage selections include their specialist workflow suites; overlapping
filename patterns execute each selected file once. Unknown suite names and
patterns matching no files are errors. Small integrations with no
specialist suite use registry checks as their starting group; that is not proof
of external application behavior. Review responsibility follows the source owner;
the map does not invent individual maintainer assignments.

| Owner | Start with |
| --- | --- |
| Feature infrastructure | `Python/tests/application/test_feature_registry.py`, `test_feature_preferences.py`, `test_settings_page.py` |
| Desktop shell/documents | `Python/tests/application/test_main_window.py`, `Python/tests/readers/test_document_workspace.py` |
| LM conversation lifecycle and presentation | `Python/tests/chat/test_lm_session.py`, `test_lm_ui.py`, `test_lm_appearance.py` |
| Git history, search, preview and job ownership | `Python/tests/version_control/test_git_ui.py`, `test_git_preferences.py`, `test_git_repository_tabs.py`, `test_git_hunk_layout.py` |
| Blender presentation and operation lifecycle | `Python/tests/blender/test_blender_page.py`, `test_blender_settings.py`, `test_blender_library.py` |
| Mobile Open/Save As and file management | `mobile_build/tests/documents/test_editor_picker.py`, `test_files_ui.py`, `test_private_sessions.py` |
| Mobile saved imports and window ownership | `mobile_build/tests/documents/test_saved_files.py`, `test_window_owners.py`, `test_workspace_ui.py` |
| Mobile source selection and import isolation | `Python/tests/test_mobile_packaging.py`, `test_mobile_portability.py`, `mobile_build/tests/tooling/test_packaged_startup.py` |

The [mobile owner map](mobile-runtime.md) explains controller
and packaging boundaries. For focused runs, use `dev.py test desktop <filename>` or
`dev.py test mobile <filename>`. Filename selectors remain valid after grouping. Isolated mode also supports nested directories,
running each file from its own parent in a separate process. Duplicate filenames
in different directories cannot shadow each other. Each isolated child loads its
exact file, so packaged child directories cannot be rediscovered in the parent run. Empty test modules fail. The runner puts the selected suite first
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
The lint policy checks syntax/correctness (`E9`, `F63`, `F7`, `F82`) and reviewed
unused redefinitions (`F811`) without forcing a formatting rewrite. `F401` and
`F841` remain optional review aids: package/module re-exports, format-registration
imports, test mocks, native type imports and retained lifetime handles need owner
review before removal. An unused assignment may still evaluate a required operation;
removing its evaluation can change behavior. In particular, downloader sync names
are explicit same-name re-exports used by its UI, and the legacy aviation
`print_info` method's lack of output is preserved rather than silently fixed during
lint cleanup. Do not apply repository-wide unused-import/local autofixes. `commonUtils.tests.qt_test_case.QtTestCase` gives GUI tests ownership of
new windows: it requests worker shutdown, drains deferred deletion and deletes
windows before the next test. Use its `temporary_directory()` for GUI filesystem
fixtures so windows and watchers are destroyed before their directories are
removed, including on assertion failures. Register fixture-specific cleanup after
creating the directory. Use `wait_until()` for condition-based Qt waits with
operation-specific timeout messages. Tests must not depend on windows retained by
other tests. See the [shared test guide](../../Python/commonUtils/docs/reference/tests/tests.md)
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
process uses a private temporary directory index and shared storage root. During
discovery and execution, `Path.home()` and platform config/cache environment
variables point into disposable test storage, so default preferences and shared
workspaces do not use the contributor's live data. Helper subprocesses inherit
the private storage/config environment; tests spawning other processes must still
supply explicit private fixtures for APIs that resolve the OS home independently.
Both single-process and isolated-module modes clean their private storage.
The runner does not replace `HOME` or disable filesystem errors.

Platform release checks with `--install` provision the platform’s pinned rclone
using archive and executable SHA-256 verification, then require the real synthetic
LocalCrypt regressions. They never access user remotes or credential packages.
Without that provisioning, local runs may skip crypt tests if rclone is absent.
Review tests keep their non-CLI cases active and explicitly skip only cases that
need the missing pinned executable. Report those skips separately from native
coverage; an installed-tool run still executes the complete review file.
Release provisioning uses the locked certifi CA bundle if `SSL_CERT_FILE` is not
already configured, including on macOS framework Python; TLS verification remains
enabled.

## Updating mobile host dependencies

Edit `mobile_build/requirements-host.in`, then regenerate its hash lock with
`uv pip compile mobile_build/requirements-host.in --python-version 3.12 --universal
--generate-hashes --output-file mobile_build/requirements-host.txt`. Commit both files.
Native app requirements remain in `mobile_build/pyproject.toml`; authentication tools
remain host-only. Do not copy a host virtual environment into a mobile payload.

## Local disk usage and private files

Virtual environments, `mobile_build/build/`, `mobile_build/payload/`, `mobile_build/logs/`,
`mobile_build/.tools/` and `mobile_build/.deploy-workspaces/` are ignored generated output.
They can be much larger than the tracked source. Git exclusions do not reclaim
local space. Stop builds and apps, and save wanted reports before removing a
particular generated directory; the corresponding setup/build recreates it.
Keep credentials, `.env` files and signing keys local. Never put real secret values
in examples or fixtures. Release packaging also excludes conventional private
files and generated mobile output, even if accidentally tracked.

Run `python3 dev.py toolchain` after dependency updates. It compares mobile host
inputs and their lock, native/host Toga versions, shared desktop/mobile dependency
pins and CI Ruff pins against the existing application manifests. CI runs it too.
Python's application manifest and the native Briefcase manifest remain canonical;
the checker adds no second version registry.

Before committing, run `python3 dev.py hygiene` to check indexed paths against
ignore rules and inspect indexed text blobs for recognizable private keys and
GitHub/AWS token shapes. It prints only paths and categories, never matching
values. Stage specific reviewed paths first: the check reads the Git index, so it
does not certify unstaged/untracked content or arbitrary provider token formats.
Review every staged diff; never stage a virtual environment, native build output,
credentials or a local feature link.

## Worked contribution: desktop LM attachments

The attachment extraction is a complete example of the current ownership flow:

1. `Python/features/lm/__init__.py` registers the `lm.chat` page through
   `create_page`; it lazily imports `ui.page.LMPage`.
2. `ui/page.py` composes `AttachmentController` from `ui/attachments.py`.
   Menu callbacks keep their old page methods, which delegate to that owner.
3. The controller obtains registered project/buffer context through
   `AttachmentHost`. Portable `project_tools.py` owns file containment and IDE
   exclusions; the controller owns picking and publishing bounded composer text.
   Conversation records and checkpoints remain with `ConversationSession`.
4. `test_lm_ui.py` covers selection/file attachments, excluded paths, project
   choice across reopening and draft preservation. Run
   `python3 dev.py test desktop test_lm_ui.py`; its synthetic endpoint needs
   permission to bind localhost. Also run `python3 dev.py architecture` and lint.
5. This extraction is desktop-only, so it adds no mobile payload entry. A new
   mobile source instead needs its owner's `mobile_sources.json` and
   `test_mobile_packaging.py`, including any separately curated proof payload.
6. Update the LM developer guide for implementation and its user guide only when
   user-visible behavior changes. Review explicit paths, stage them, run hygiene,
   then commit. Do not stage runtime output or unrelated work.

Follow that sequence for a first change: identify a registration/callback, keep
policy with its owner, exercise behavior tests, check packaging and update the
owning guide. Use `dev.py compatibility` when an older path forwards to new code.

The architecture check includes module-qualified imports and literal
`module:attribute` references used by deferred factories. Portable-owner checks
also reject deferred commonUtils UI, PySide6 and Toga references. It inspects
syntax without importing features or optional toolkits; dynamically constructed
strings still require source review. The reviewed edge policy is unchanged.

## Portable import matrix

Run `python dev.py test desktop test_portable_imports.py` and
`python dev.py test desktop test_architecture_contracts.py` after changing portable
owners or their policy. The import matrix uses fresh child interpreters and isolated
XDG directories per owner, actively rejecting presentation imports even when the
application catches `ImportError`. Its probe regression demonstrates an indirect,
caught import is still a failure. The static CI job runs both checks without
installing a desktop toolkit. See the [portable owner policy](architecture.md#portable-owner-policy)
for selection and limits; the document smoke suite additionally exercises real
format operations without desktop/image packages.
