# Links development

Personal Links contributes a desktop page for a fixed catalog of configured
HTTP/HTTPS shortcuts. See the [desktop guide](../user/user.md) and
[mobile availability](../user_mobile/user_mobile.md).

## Owners and registration

Source is under `Python/features/links/`:

| Owner | Responsibility |
| --- | --- |
| `__init__.py` | Feature name `links`, label Personal Links and lazy registration |
| `ui_contributions.py` | Configuration settings contribution and Links page factory, page ID `links`, order 40 and `links` navigation icon |
| `catalog.py` | Immutable entry/group/category records and the fixed `LINK_CATEGORIES` button catalog |
| `configuration.py` | Layered defaults/personal configuration access and typed/legacy key compatibility |
| `actions.py` | Substitution, URL validation and `webbrowser.open` handoff |
| `ui/page.py` | Scrollable category layout, four-column button grids and inline launch status |

The page imports desktop PySide UI lazily through its contribution factory.
There is no mobile adapter or `mobile_sources.json` for this feature, and
`Python/services/mobile_features.py` does not register `links`. Notes Library
connection discovery and its mobile Links drawer have separate owners.

## Configuration and launch boundary

`configuration.get_url(key)` reads `[URLs]` through `effective_settings` for the
feature's `config.ini`; `get_resolve_ip(name)` reads `[ResolveIP]`. Both prefer
`<key>_str` with an unsuffixed-key fallback. Personal overrides follow the central
settings policy; do not introduce a separate feature preference store.

`open_config_file_url(entry_str)` resolves only `<goat-pc>` and `<yagi-mac>`.
Missing replacements become empty strings before validation. Validation rejects
remaining angle brackets, whitespace, schemes other than `http`/`https` and URLs
without a hostname. Missing targets raise `ValueError`. Accepted URLs pass to
`webbrowser.open`, whose return value reaches the page. The action performs no
network request, DNS lookup, authentication or server-health probe itself.

`LinksPage._open_link` catches `ValueError` and `OSError`, displaying their text.
A truthy launcher result displays success; a false result displays browser-launch
failure. Bind new catalog entries with captured config keys, as the existing
button callbacks do. Adding configuration entries alone does not add UI buttons;
change the catalog and its defaults together for a new supported shortcut.

## Validation scope

`Python/tests/application/test_ini_settings.py` covers the Links configuration
reader's typed and legacy keys, together with central configuration-panel wiring.
`Python/tests/application/test_features_page.py` checks the Personal Links label.
These tests do not establish browser launch, service availability or native
mobile support. The similarly named `test_links_images_voices_probe.py` covers
Notes Library links, images and voices, not this launcher.

For a launcher change, review missing/invalid targets, both known placeholders,
unresolved placeholders, HTTP/HTTPS restrictions, a false browser result and
inline error presentation. Keep browser calls mocked for automated checks.
When native desktop interaction is needed, separately check the configured
browser handoff; do not interpret an accepted launch as a reachable service.
Use the owning workflow in [Testing](../../../development/testing.md).

The November 4, 2026 documentation audit inspected source and tests and ran only
static documentation checks during a release hold. It did not launch a browser,
Qt application, build, simulator or device, or rerun runtime acceptance.
