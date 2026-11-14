# Feature and application infrastructure ownership

Under `Python/features/`, `application.registry` owns the live
`FeatureRegistry`. `discovery.py` enumerates public direct packages, excludes
`INFRASTRUCTURE_PACKAGES` and reports failed imports. `contributions.py` declares
the host contract. See [feature organization](features.md).

## Registry runtime ownership

`runtime/{preferences,dependencies,activation,catalog}.py` own migrations,
dependency order, once-per-owner initialization and category validation.
The registry retains weak declarations and observers. Each projection uses one
roster even when a hook changes preferences. Independent registry tests inject
loader, settings and discovery providers. commonUtils file types remain
process-owned. Check `test_feature_runtime.py`, `test_feature_registry.py` and
`test_feature_preferences.py`.

Run `python3 dev.py architecture` for static import and literal deferred factory
checks. Review new edges in `Scripts/architecture.json`. Mobile features accept
injected host services. Desktop presentation exceptions apply to declared owners.

`features.settings` registers configuration layers. `features.preferences`
loads preference paths and legacy selections. `runtime.dependencies` accepts
identity and dependency accessors and computes the graph independently of
discovery or settings. The catalog wraps entries with their registered owner.
Activation validates hooks before any startup side effects and tracks completed
initializers per registry. Rejected enablement restores the active type rules.
