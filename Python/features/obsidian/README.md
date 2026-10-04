# Obsidian Feature

Finds Obsidian vaults in a selected local folder and offers an Open Vault action for each on the Folders page.

## Discovery and opening

Vaults are recognized by `.obsidian` directories found through a bounded directory search (`list_directories(depth=2)`). Missing expected `app.json`, `appearance.json`, `core-plugins.json`, or `workspace.json` files produce warnings but do not exclude the vault.

Obsidian must be installed and launchable. Registered vaults open through an `obsidian://` URI using their vault ID. New vaults are added to the platform's `obsidian.json` registry before opening. Obsidian must be closed for registration; the action asks you to close it if necessary.

Registry lookup supports Windows, macOS, and Linux, including native, Flatpak, and Snap installs. Registry writes preserve unknown settings and use temporary-file replacement.

## Structure

- `detection.py`: vault discovery.
- `actions.py`: installation/process checks, registry handling, and URI launching.
- `ui_contributions.py`: folder actions and workflow.

No startup initialization or rclone dependency is required. Opening an unregistered vault modifies Obsidian's global vault registry.
