# Developing Personal Links

Personal Links opens configured HTTP and HTTPS shortcuts in the desktop browser.
See the [desktop guide](../user/user.md) and [mobile scope](../user_mobile/user_mobile.md).

## Try a change to shortcut settings

On desktop, enable **Personal Links** in **Settings → Features**, then open
**Links → Quick Links** and find **Google**. The button binds the `google` key
from `Python/features/links/catalog.py:LINK_CATEGORIES`.
`Python/features/links/configuration.py:get_url` reads that key in **URLs** when
the button is clicked.

For example, factor the typed-key lookup shared by `get_url` and
`get_resolve_ip` into a single reader in `configuration.py`. Extend the
synthetic INI fixture to include both `google_str = https://example.com` and
`google = https://example.org`. The reader should choose the typed value and
still accept a file containing only the legacy key. Run from the repository
root with the desktop environment set up:

```sh
python3 dev.py test desktop --exact-file Python/tests/application/test_ini_settings.py
```

Expect the settings panel and typed/legacy reader cases to pass. They use a
temporary INI and never start a browser. The existing fixture tests each spelling
separately. The suggested extension also exercises precedence when both exist.

## Owners and registration

Follow `Python/features/links/__init__.py:register` into the desktop contributions.

| Owner | Responsibility |
| --- | --- |
| `__init__.py` | Feature name `links`, label Personal Links and lazy registration |
| `ui_contributions.py` | Configuration settings contribution and Links page factory, page ID `links`, order 40 and `links` navigation icon |
| `catalog.py` | Entry/group/category records and the fixed `LINK_CATEGORIES` button catalog |
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
