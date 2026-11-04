# Open Obsidian vaults

[Obsidian guides](../obsidian.md)

Enable **Obsidian** in Features to offer vault launch actions for local folders
on **Workspaces**. The external Obsidian application must be installed and able
to handle `obsidian://` links. This launcher supports Windows, macOS and Linux.

## Open a vault

1. Install and launch Obsidian once.
2. Select the containing local folder on **Workspaces** and open its actions.
3. Choose **Open "VaultName" Vault** for the vault you want.
4. If the vault is new to this computer, close Obsidian completely when asked,
   then retry the action.

Discovery looks for `.obsidian` directories using a bounded directory search
with depth two. Missing `app.json`, `appearance.json`, `core-plugins.json` or
`workspace.json` files produce warnings but do not exclude a vault. This is not
an unrestricted disk-wide vault search.

Registered vaults open through their vault ID. Opening an unregistered vault
first adds it to Obsidian's global `obsidian.json` registry, preserving existing
settings. Obsidian must be closed for that registration so it cannot overwrite
the update. Existing registered vaults can open while Obsidian is running.

## If opening fails

Install and launch Obsidian once if Logistics reports that it is unavailable.
Check access to the local vault and registry if reading or writing fails. Invalid
registry JSON is reported rather than replaced. On Linux, the selected registry
follows the registered URI handler where possible and supports native, Flatpak
and Snap installations. With several registries and no identifiable handler,
Logistics uses the most recently modified existing registry and logs a warning.

The action opens the local vault; it does not synchronize cloud files or install
Obsidian plugins. Use [Notes Library](../../notes_library/user/user.md) to read,
edit and organize a local or unlocked LocalCrypt library within Logistics.
Notes Library has its own feature toggle and does not require Obsidian to be
installed. [Mobile usage](../user_mobile/user_mobile.md) also uses Notes Library.
