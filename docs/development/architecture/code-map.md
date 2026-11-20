# Finding your way around the code

Use this map after identifying the behavior you want to change. The
[architecture overview](architecture.md) explains how the hosts, features and
shared code fit together. If you are still deciding what to work on, start
with [your first contribution](../development.md#make-your-first-contribution).

## Checkout root

| Path | What belongs there |
| --- | --- |
| `Python/` | Desktop and mobile application source, feature modules, desktop tests and the pinned commonUtils submodule. |
| `docs/` | User and developer wiki. Start at `docs/docs.md`. |
| `Scripts/` | Existing development helpers called by the root launchers and `dev.py`. Keep their paths when updating callers. |
| `Credentials/` | Local, ignored credentials. Keep this directory out of shared and exported source. |
| `logistics_build/` | The external Build Deployment Manager adapter, source capture, platform execution and retention policy. Start at `logistics_build/build_project.py` and `build-project.json`. |
| `mobile_build/` | Mobile staging, Briefcase project and deployment recipes, mobile host tests and native fixtures. |
| `.github/` | Hosted validation, release workflows and packaging scripts. |
| `dev.py` and `LaunchLogistics_*` | Checkout setup and test commands, and platform-specific desktop launchers. |
| `tmp/` | Ignored temporary work, including new evidence under `tmp/test-results/<run-id>/`. Older evidence remains at its recorded path. See [validation artifacts](../testing/validation-artifacts.md). |

## Application owners

| Task | Start here |
| --- | --- |
| Start desktop or change the rail, chooser or tabs | `Python/launch.py`, `Python/desktop/{main_window,sidebar,landing,documents}.py` |
| Find the owner of a named screen | [Screen map](ui-architecture.md) |
| Add an action, file type or panel | `Python/features/<id>/`, [feature declarations](features.md) and [browser wiring](file-browser.md) |
| Change folder sources or document policy | `Python/{models,services}/`, [host services](services.md) |
| Change mobile shell behavior | `Python/mobile/`, [runtime owner map](mobile-runtime.md) and [workspace routes](mobile-workspace-navigation.md) |
| Change remote or encrypted document opening | [Provider-to-reader trace](document-storage.md#trace-a-mobile-provider-reader) |
| Package mobile or change a native adapter | Owning `mobile_sources.json`, `mobile_build/tools.py` and [mobile preparation](../build-release/mobile-preparation.md) |
| Change build policy or release gates | `logistics_build/` and `.github/{workflows,scripts}/` |
| Change reusable code or APIs | Separate `Python/commonUtils/` submodule and its own wiki |

## Trace a visible action

Start with the action a user takes. If it belongs to a feature, find its
declaration and follow the registered handler. If it changes what the host
shows, start with the corresponding desktop or mobile entry point above.
For example, the plain text file opened in the
[first document walkthrough](../setup/getting-started.md) enters through
`Python/desktop/file_browser.py`. Text Editor's browser declaration lives in
`Python/features/text_editor/contributions.py`; its handler calls the editor
service under `Python/features/text_editor/ui/`. That service keeps the
editor available even after the file browser is closed. The
[Text Editor development guide](../../features/text_editor/development/development.md)
separates browser actions, editor lifetime and saving, and lists their tests.

For other entry points, follow the
[desktop transfer controls](../../features/rclone/development/transfers.md#find-desktop-transfer-controls)
to their window and progress adapter, or find
[Settings → Appearance](ui-architecture.md#find-a-screen-by-its-visible-name)
in the desktop and mobile screen map. The
[notebook brush walkthrough](../../features/notebooks/development/brush-calibration.md#try-a-brush-change)
follows a drawing gesture to its feature and renderer. To see how a build
workflow is wired, use the
[Build Manager plan walkthrough](../build-release/build-manager-journeys.md#trace-a-validation-plan).

## Find checks and follow import boundaries

For a desktop registry change, run
`python3 dev.py test desktop test_feature_registry.py` from root and expect
dependency, contribution and activation checks to pass. Desktop tests live in
`Python/tests/`, mobile host tests in `mobile_build/tests/`, and native fixtures
in `mobile_build/native_tests/`.

Use canonical imports rooted at `desktop`, `features`, `services`, `mobile` and
`commonUtils` with `Python/` on the import path. Keep native source paths and
manifest entries synchronized when moving a module. Check
`python3 dev.py architecture` and `python3 dev.py compatibility`.

## Native and compatibility identities

The former `Python/ui_new/`, `Python/logisticsmobile/` and root `Mobile/`
paths became `Python/desktop/`, `Python/mobile/` and `mobile_build/`. Update
external host imports to those owners. Briefcase still uses app key
`logisticsmobile` and installed ID `io.github.ispaure.logisticsmobile`.
Staging generates a tiny launcher delegating to `mobile.app.main`. Preserve
the generated native project and `tests.logisticsmobile` acceptance names.

Trace a desktop registry change from `features.application.registry` to
`FeatureRegistry`, then to its preference, dependency, activation or catalog
owner. Patch the application instance for integration tests and construct an
independent registry for ownership tests. Move together the import, test
patch target and payload declaration when changing a source owner.

[Developer index](../development.md)
