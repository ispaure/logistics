# Open Obsidian vaults

[Obsidian guides](../obsidian.md)

## Open a vault

1. Install and launch Obsidian once, then enable **Obsidian** in Logistics Features.
2. Select the containing local folder on **Workspaces** and choose **Open "VaultName" Vault**.
3. If prompted, quit Obsidian completely and retry so Logistics can register the vault in `obsidian.json`.

Discovery looks for `.obsidian` directories up to two levels below the selected folder.

## If opening fails

Check that Obsidian handles `obsidian://` links and that the vault and registry are accessible. Invalid registry JSON is reported and preserved. Linux supports native, Flatpak and Snap handlers.

For editing inside Logistics, see [Notes Library](../../notes_library/user/user.md) or [mobile usage](../user_mobile/user_mobile.md).
