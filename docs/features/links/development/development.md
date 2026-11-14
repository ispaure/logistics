# Developing Personal Links

## Try a change to shortcut settings

On desktop, find **Links → Quick Links → Google**. Factor typed-key lookup in `Python/features/links/configuration.py:get_url` and `get_resolve_ip`. Extend the temporary INI fixture with both `google_str` and `google`. Run from the checkout root. Expect typed precedence and legacy-only fallback without starting a browser.

```sh
python3 dev.py test desktop --exact-file Python/tests/application/test_ini_settings.py
```

`ui_contributions.py` registers settings and the desktop page. Add shortcuts to `catalog.py` and config defaults together. `actions.py` substitutes `<goat-pc>` and `<yagi-mac>`, admits HTTP(S) URLs with a hostname, rejecting whitespace and unresolved placeholders, and hands off to the browser. Mock dispatch and check inline errors for missing/invalid URLs and failed launch. [Desktop usage](../user/user.md)
