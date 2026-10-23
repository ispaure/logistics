# Feature and application infrastructure ownership

Use [feature organization](features.md) for registration and
lifecycle contracts, or the [code map](code-map.md) to find
an implementation. Direct feature packages keep their stable runtime IDs.

This directory also contains application infrastructure modules. They are not
optional tools:

| Module | Responsibility |
| --- | --- |
| `contributions.py` | Logistics contribution declarations and the extended Feature contract |
| `application.py` | Explicit application-owned `FeatureRegistry` instance |
| `feature_runtime.py` | `FeatureRegistry` facade coordinating discovery, state, runtime owners, declaration cache and observers |
| `runtime/` | Preference persistence, dependency ordering, activation and contribution validation |
| `discovery.py` | Direct package enumeration and isolated import failures |
| `settings.py` | Application and feature configuration registration/store composition |
| `preferences.py` | Feature preference paths, loading and migration |
| `code_font.py` | Application policy for binding code view fonts |


Public registry imports remain compatible. The implementation owners under
`features/runtime/` are infrastructure, so discovery must not treat that package
as an optional feature. New feature behavior belongs in its own package; the
registry coordinates the runtime owners rather than absorbing feature workflows.

Use lightweight `__init__.py` registration, portable named domain modules,
desktop `ui/`, optional `mobile/`, a `docs/docs.md` wiki with `development/development.md`,
`user/user.md` and, where supported, `user_mobile/user_mobile.md`. Existing packages migrate incrementally; do not create
empty layers or duplicate Core UI/Bulk Rename packages to match a template.

Start feature-infrastructure validation with `Python/tests/application/test_feature_registry.py`,
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

`Python/features/runtime/dependencies.py` owns dependency availability and initialization
ordering as toolkit-independent functions. Registry wrappers inject identity and
dependency accessors, preserving its public APIs, cached declarations and test
patch points. The registry delegates preferences/migrations to `runtime.preferences`,
activation to `runtime.activation` and contribution validation/collection to
`runtime.catalog`. Graph traversal does not read settings, discover features or
run registration hooks. Existing registry regressions cover cycles,
missing dependencies, duplicate identities and startup ordering.

## Registry runtime ownership

`FeatureRegistry` retains a `PreferenceState`, `FeatureActivation` and
`ContributionCatalog`. Preference state owns disabled choices, mode/path and
migrations; activation owns the initialized set and validates startup hooks
before invoking them. The catalog validates contribution categories before UI
construction and wraps them with registered owner identities. The registry keeps
the weak registered-declaration cache and weak observers. The application uses
`features.application.registry` directly; the former module forwarding functions
and compatibility imports have been removed. Independent owners can inject a
`feature_loader`, `settings_provider` and discovery `features_path` callback.
Preferences, dependency ordering, activation rollback and contribution validation
keep their existing behavior. Shared commonUtils file-type machinery remains
process-owned and is shared by independent registries.

Tests patch the application registry instance or construct an independent registry.
`test_feature_runtime.py` verifies independent preferences, declaration caches,
once-per-owner initialization and observer retirement. `test_feature_registry.py`
and `test_feature_preferences.py` exercise the application instance contracts.
