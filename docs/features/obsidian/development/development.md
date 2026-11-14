# Obsidian Feature

Obsidian contributes a desktop Workspaces action to open a local vault in the
external Obsidian application. See [desktop usage](../user/user.md) and the
[mobile boundary](../user_mobile/user_mobile.md).

## Try a registry serialization change

On Windows, macOS or Linux, enable **Obsidian** in Features. Create a disposable
local folder with an empty `.obsidian` subfolder and choose the local folder on
**Workspaces**. Its actions show **Open "<name>" Vault** even when the marker
folder has no configuration files. The action resolves to
`obsidian_open_vault`. Use the fixture below to exercise first registration
without touching the Obsidian registry on your computer.

As a local experiment, change `Python/features/obsidian/actions.py:_write_registry`
to emit indented JSON. Keep UTF-8, the trailing newline and atomic publication.
Update the expected bytes in `test_preserves_mode_and_utf8_serialization`.
From the checkout root with the [desktop environment](../../../development/setup/getting-started.md)
set up, run:

```sh
python3 dev.py test desktop --exact-file Python/tests/editing/test_obsidian_registry.py
```

Expect five passing tests. The registry should deserialize to the same values,
preserve existing POSIX permissions, leave a competing write intact and reuse
the registered ID after a simulated launcher failure. The tests use temporary
registries and mock external URI dispatch.

## Contribution and discovery

`Python/features/obsidian/__init__.py:register` delegates to `ui_contributions.py`.
`_get_actions` supplies one folder action per vault with a `Directory` payload.
`_open_vault_workflow` accepts that type and imports `actions.open_vault` on
invocation. The feature registers only a folder contribution and workflow.

`detection.py:get_vault_paths` calls `LocalFolder.list_directories(depth=2)`
and returns parents of `.obsidian` directories. Missing `app`, `appearance`,
`core-plugins` and `workspace` JSON files produce warnings. Opening revalidates
both directories before using the registry.

## Registry and launch boundary

`actions.py` owns installation and process checks, registry selection,
registration and URI dispatch. It expands and resolves paths where possible,
then applies host case rules when matching existing entries. It preserves
unknown top-level fields and existing vault records. Invalid JSON or a
non-object registry or `vaults` field fails before publication.

| Platform | Registry and launcher |
| --- | --- |
| Windows | `%APPDATA%/Obsidian/obsidian.json` with a home-directory fallback, URI association detection and `os.startfile` dispatch |
| macOS | `~/Library/Application Support/obsidian/obsidian.json`, `open -Ra Obsidian` detection and `open` dispatch |
| Linux | Native XDG, Flatpak or Snap registry, with `xdg-open` dispatch |

Linux first consults the `obsidian://` handler. Without an identified handler
it uses the sole existing registry, or the most recently modified when
multiple exist and logs a warning. If none exists, installation checks choose
Flatpak, then Snap, then the native path.

An existing vault opens by ID without a write and can open while Obsidian is
running. New registration requires Obsidian to close first. `_register_vault`
allocates a unique random ID, records the absolute path and timestamp in
milliseconds, and passes the observed registry bytes or absence to the
atomic write check. Dispatch uses `obsidian://open?vault=<encoded-id>`.
If dispatch fails, retry the action after correcting the launcher. The
completed registration is reused. Success reports launcher acceptance.

## Mobile ownership

`Python/mobile/obsidian.py` is a compatibility host for the
[Notes Library mobile browser](../../notes_library/development/development.md#mobile-browsing-and-document-lifecycle).
`mobile_build/tests/documents/test_obsidian.py` exercises that host's
publication, containment, history and privacy.

## Validation scope

For changes to platform detection or URI dispatch, verify the affected
installation type with Obsidian installed. The focused registry suite mocks
installation checks and URI dispatch.
