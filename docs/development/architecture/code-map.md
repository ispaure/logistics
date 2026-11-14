# Finding your way around the code

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

Follow a visible action to its lazy registration, then to the feature handler.
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
