# Feature and application infrastructure ownership

Use [feature organization](features.md) for registration and
lifecycle contracts, or the [code map](code-map.md) to find
an implementation. Direct feature packages keep their stable runtime IDs.

This directory also contains application infrastructure modules. They are not
optional tools:

| Module | Responsibility |
| --- | --- |
| `contributions.py` | Logistics contribution declarations and the extended Feature contract |
| `registry.py` | Discovery, availability, dependency order, enablement and contribution aggregation |
| `discovery.py` | Direct package enumeration and isolated import failures |
| `settings.py` | Application and feature configuration registration/store composition |
| `preferences.py` | Feature preference paths, loading and migration |
| `code_font.py` | Application policy for binding code view fonts |
| `editor_changes.py`, `editor_hunks.py` | Host editor baseline discovery, asynchronous markers and hunk review |

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
runner requires flat test directories; group ownership in documentation before
changing discovery or CI.
