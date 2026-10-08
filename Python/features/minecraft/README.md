# Minecraft Feature

Developer notes. See the [user guide](user_docs/index.md) for controls and setup,
and [UI architecture](../UI_ARCHITECTURE.md) for shared contribution conventions.

Provides Minecraft server integration for Logistics.

## Responsibilities

- Discover Java and Bedrock servers within selected local folders.
- Represent individual Minecraft servers.
- Launch supported servers.
- Open server folders and documentation.
- Edit `server.properties`.
- Contribute a Minecraft server selector and controls to the Folders page.

## Structure

- `detection.py` finds directories containing `server.properties`.
- `server.py` contains the `MinecraftServer` model and server actions.
- `folder_widget.py` contains the server selector and controls.
- `ui_contributions.py` contributes the Minecraft section to Folders.

## Detection

Servers are discovered one to three directory levels below the selected local folder. Any directory containing `server.properties` is included; discovery does not use fixed Dropbox roots or exclude directories by a `Backups` suffix.

A server containing `bedrock_server.exe` (Windows) or `bedrock_server` (Linux) is classified as Bedrock. Launching requires the matching platform executable; the Linux binary must have execute permission. Other detected servers are classified as Java.

## Launch configuration

Java servers use `logistics_cfg.ini` in the server directory:

```ini
[LaunchScript]
win = start.bat
mac = start.command
linux = start.sh

[Documentation]
wiki = https://minecraft.wiki/
```

Script paths are relative to the server directory. Include entries for the platforms you use. Missing launch settings prevent launching; missing documentation prevents opening the wiki. Property edits modify the server's `server.properties`.
