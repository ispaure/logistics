# Developing Personal Links

Personal Links maps configured desktop shortcuts to validated browser URLs.
The catalog defines available shortcuts, configuration resolves their values,
and the action boundary validates a URL before handing it to the browser.

## Follow a configured shortcut

**Links → Quick Links → Google** reads its URL through `get_url` in
`Python/features/links/configuration.py`. When a shortcut includes a
computer placeholder, the action also reads host substitutions through
`get_resolve_ip`. Typed INI keys take precedence and older untyped keys
remain a fallback. Temporary INI fixtures check that compatibility without
opening a browser.

```sh
python3 dev.py test desktop --exact-file Python/tests/application/test_ini_settings.py
```

`ui_contributions.py` registers settings and the desktop page. Add shortcuts to `catalog.py` and config defaults together. `actions.py` substitutes `<goat-pc>` and `<yagi-mac>`, admits HTTP(S) URLs with a hostname, rejecting whitespace and unresolved placeholders, and hands off to the browser. Mock dispatch and check inline errors for missing/invalid URLs and failed launch. [Desktop usage](../user/user.md)
