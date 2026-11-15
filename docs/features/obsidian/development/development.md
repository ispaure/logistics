# Obsidian Feature

## Try a registry serialization change

On desktop (Windows, macOS or Linux), select a temporary folder with an empty `.obsidian` directory in **Workspaces**. Expect **Open "<name>" Vault**. Try indenting JSON in `Python/features/obsidian/registry.py:_write_registry`. Update the byte expectation in `test_preserves_mode_and_utf8_serialization`. From the checkout root, expect UTF-8, trailing newline, POSIX mode, concurrent-write protection and retry by existing ID to pass using temporary registries.

```sh
python3 dev.py test desktop --exact-file Python/tests/editing/test_obsidian_registry.py
```

`ui_contributions.py` binds the local Directory action. `actions.py` revalidates the vault, checks whether Obsidian must close and dispatches the URI. `registry.py` validates the JSON, matches canonical paths and preserves unknown fields. Before publishing a new registration, it checks the bytes it originally read. First registration uses atomic no-replace publication. If URI dispatch fails, retrying reuses the saved ID. The fixture mocks URI dispatch.

Windows uses AppData and `os.startfile`. macOS uses Application Support and `open`. Linux uses native XDG, Flatpak or Snap and launches with `xdg-open`. Registry selection follows the registered URI handler, then the most recently modified existing registry. Without a handler or existing registry, it prefers Flatpak, Snap, then native.

Mobile uses the [Notes Library compatibility host](../../notes_library/development/development.md#mobile-browsing-and-document-lifecycle).
