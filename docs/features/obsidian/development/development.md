# Obsidian Feature

[Obsidian guides](../obsidian.md) · [Desktop usage](../user/user.md) ·
[Mobile boundary](../user_mobile/user_mobile.md)

The feature owns external desktop vault launching. Provider-backed Markdown,
library navigation and mobile note editing belong to
[Notes Library](../../notes_library/development/development.md).

## Contribution and discovery

`Python/features/obsidian/__init__.py` lazily delegates to `ui_contributions.py`.
The contribution registers one folder feature and the `obsidian_open_vault`
workflow; it does not create a destination page. Availability requires a local
folder and at least one discovered vault. Each vault gets an
`Open "<name>" Vault` action carrying a `Directory`; the workflow refuses other
payload types and imports desktop actions only when invoked.

`detection.py` calls `LocalFolder.list_directories(depth=2)` and identifies
`.obsidian` directories. It warns about missing `app`, `appearance`,
`core-plugins` and `workspace` JSON files but still returns the parent vault.
Opening revalidates that the vault and its `.obsidian` marker remain directories.
There is no startup initialization or rclone dependency.

## Registry and launch boundary

`actions.py` owns installation checks, process checks, registry selection,
registration and URI dispatch. Paths are expanded, resolved where possible and
normalized with the host's case rules before matching registered entries.
Unknown top-level registry fields and existing vault records are retained.
Invalid JSON, a non-object registry or a non-object `vaults` field fails without
replacing the file.

| Platform | Registry and launcher |
| --- | --- |
| Windows | `%APPDATA%/Obsidian/obsidian.json`, with a home-directory fallback; URI association detection and `os.startfile` dispatch |
| macOS | `~/Library/Application Support/obsidian/obsidian.json`; `open -Ra Obsidian` detection and `open` URI dispatch |
| Linux | Native XDG config, Flatpak or Snap registry; `xdg-open` URI dispatch |

Linux registry selection first consults the `obsidian://` handler. Without an
identified handler, it uses a sole existing registry, or the most recently
modified registry with a warning when several exist. If none exists, installation
checks choose Flatpak, then Snap, then the native path.

An existing matching vault opens by its registered ID without a registry write.
A new registration requires Obsidian to be closed, allocates a unique random ID,
stores the absolute path and millisecond timestamp, then atomically publishes the
UTF-8 JSON through `commonUtils.persistence.atomic_write_bytes`. The integration
opens `obsidian://open?vault=<encoded-id>` after publication. Failures display an
error and return false. Successful dispatch does not prove that the external
application finished opening the vault.

## Mobile ownership

`Python/mobile/obsidian.py` is a compatibility host for the feature-owned
`features.notes_library.mobile.notes_library.VaultBrowser`. It does not call
this desktop registry workflow. `Python/mobile/notes_discovery.py` discovers
local and unlocked LocalCrypt libraries for Documents; it stops descending once
a library root is found. The legacy module/class naming does not indicate a
mobile external-Obsidian launcher.

## Validation scope

`Python/tests/editing/test_obsidian_registry.py` checks UTF-8 serialization,
existing POSIX mode preservation and failed atomic publication retaining the
original registry with no leftover staging file. Mobile tests named
`mobile_build/tests/documents/test_obsidian.py` cover Notes Library publication,
containment, history and privacy, rather than external Obsidian launching.

The November 4, 2026 documentation review inspected source and tests and used
static documentation checks only. It did not launch Obsidian or rerun desktop,
mobile or native acceptance. Registry detection and external URI handling still
need platform-specific validation when those implementations change; the focused
registry tests do not certify every installation format.
