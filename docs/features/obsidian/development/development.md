# Obsidian Feature

## Try a registry serialization change

On desktop (Windows, macOS or Linux), select a temporary folder with an empty `.obsidian` directory in **Workspaces**. Expect **Open "<name>" Vault**. Try indenting JSON in `Python/features/obsidian/actions.py:_write_registry`. Update the byte expectation in `test_preserves_mode_and_utf8_serialization`. From the checkout root, expect UTF-8, trailing newline, POSIX mode, concurrent-write protection and retry by existing ID to pass using temporary registries.

```sh
python3 dev.py test desktop --exact-file Python/tests/editing/test_obsidian_registry.py
```

`ui_contributions.py` binds the local Directory action. `actions.py` revalidates the vault and preserves unknown registry fields. Malformed JSON or non-object registries stop before publication. New registration requires Obsidian closed and atomically checks prior bytes. Correct launch failures and retry by registered ID. Windows uses AppData and `os.startfile`, macOS Application Support and `open`, Linux native XDG/Flatpak/Snap and `xdg-open`. Linux prefers the registered URI handler, then an existing registry. Without an existing registry, detection prefers Flatpak, Snap, then native. The fixture mocks URI dispatch.

Mobile uses the [Notes Library compatibility host](../../notes_library/development/development.md#mobile-browsing-and-document-lifecycle).
