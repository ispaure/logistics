# Obsidian Feature

This integration opens local vaults in the external Obsidian application.
Logistics owns discovery and safe registration of a vault; editing notes inside
Logistics belongs to [Notes Library](../../notes_library/development/development.md).

## Follow vault registration

A local folder containing `.obsidian` offers an Open Vault action in Workspaces.
`Python/features/obsidian/registry.py:_write_registry` publishes registration
while preserving unknown fields and detecting concurrent writes. The temporary
registry fixtures verify UTF-8, file mode and retry using an existing ID:

```sh
python3 dev.py test desktop --exact-file Python/tests/editing/test_obsidian_registry.py
```

`ui_contributions.py` binds the local Directory action. `actions.py` revalidates the vault, checks whether Obsidian must close and dispatches the URI. `registry.py` validates the JSON, matches canonical paths and preserves unknown fields. Before publishing a new registration, it checks the bytes it originally read. First registration uses atomic no-replace publication. If URI dispatch fails, retrying reuses the saved ID. The fixture mocks URI dispatch.

Windows uses AppData and `os.startfile`. macOS uses Application Support and `open`. Linux uses native XDG, Flatpak or Snap and launches with `xdg-open`. Registry selection follows the registered URI handler, then the most recently modified existing registry. Without a handler or existing registry, it prefers Flatpak, Snap, then native.

Mobile uses the [Notes Library compatibility host](../../notes_library/development/development.md#mobile-browsing-and-document-lifecycle).
