# Feature and application infrastructure ownership

Use [feature organization](features.md) for registration and
lifecycle contracts, or the [code map](code-map.md) to find
an implementation. Direct feature packages keep their stable runtime IDs.

This directory also contains application infrastructure modules. They are not
optional tools:

| Module | Responsibility |
| --- | --- |
| `contributions.py` | Logistics contribution declarations and the extended Feature contract |
| `registry.py` | Compatible module functions forwarding to the application default registry |
| `feature_runtime.py` | Instance-owned discovery, enablement, initialization, preferences, declaration cache and observers |
| `discovery.py` | Direct package enumeration and isolated import failures |
| `settings.py` | Application and feature configuration registration/store composition |
| `preferences.py` | Feature preference paths, loading and migration |
| `code_font.py` | Application policy for binding code view fonts |


The infrastructure keeps its existing import paths. Moving it into a new package
now would change discovery/import contracts across desktop, curated mobile sources
and tests, with little immediate navigation benefit. This ownership table and
the feature convention make the exception explicit. New feature code belongs in
its owner, rather than expanding the registry with feature-specific behavior.

Use lightweight `__init__.py` registration, portable named domain modules,
desktop `ui/`, optional `mobile/`, a `docs/docs.md` wiki with `development/development.md`,
`user/user.md` and, where supported, `user_mobile/user_mobile.md`. Existing packages migrate incrementally; do not create
empty layers or duplicate Core UI/Bulk Rename packages to match a template.

Start feature-infrastructure validation with `Python/tests/test_feature_registry.py`,
`test_feature_preferences.py` and `test_settings_page.py`. The isolated regression
runner supports nested test files while keeping one process per file. Existing flat paths remain supported.

Desktop editor baseline discovery, markers and hunk review live in `Python/services/editors/ui/`; Text Editor and IDE consume that neutral host integration.

## Enforced import boundaries

Run `python3 dev.py architecture` to inspect absolute/relative imports and literal
lazy module/factory references without importing a feature. The reviewed baseline
is `Scripts/architecture.json`. It records existing desktop host adapters and
cross-feature relationships; new edges require an ownership review and an explicit
policy change. Dynamic expressions are not statically resolved. Toolkit-free
module rules complement the runtime portability tests, not replace them.

The current desktop adapters use shell dialogs, notifications, settings and
browser/location hosting. Keep those host integration points narrow; move a caller
to an injected host service when its workflow is refactored. Mobile features use
host services instead of importing the mobile application. Presentation integration
edges among Books/Comics/rclone and IDE/Git/LM do not imply that domain modules may
import one another's UI. Avoid broad repository-wide controller or utility folders.

## Dependency graph implementation

`Python/features/feature_graph.py` owns dependency availability and initialization
ordering as toolkit-independent functions. Registry wrappers inject identity and
dependency accessors, preserving its public APIs, cached declarations and test
patch points. Preferences/migrations, activation and contribution aggregation
remain registry responsibilities; graph traversal does not read settings, discover
features or run registration hooks. Existing registry regressions cover cycles,
missing dependencies, duplicate identities and startup ordering.

## Registry runtime ownership

`FeatureRegistry` owns its enabled/initialized sets, preference mode/path, weak
registered-declaration cache and weak observers. The application uses
`registry.default_registry`; existing module functions preserve their signatures
and delegate to that instance at call time. Independent owners can inject a
`feature_loader`, `settings_provider` and discovery `features_path` callback.
Preferences, dependency ordering, activation rollback and contribution validation
keep their existing behavior. Shared commonUtils file-type machinery remains
process-owned and is shared by independent registries.

Tests that replace internal registry dependencies target `default_registry`, or
construct their own instance. Public caller mocks can still replace the module
facade functions. `test_feature_runtime.py` verifies independent preferences,
declaration caches, once-per-owner initialization and observer retirement;
`test_feature_registry.py` and `test_feature_preferences.py` retain behavioral
contracts through the module facade.
