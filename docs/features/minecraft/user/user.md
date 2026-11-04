# Manage Minecraft servers

The Minecraft integration is available on desktop. Enable **Minecraft Server**
under **Settings → Features**, then select a local folder on **Workspaces**.
See [mobile availability](../user_mobile/user_mobile.md) for iOS and Android limits.

## Find a server

A directory with a `server.properties` file is recognized as a server. Discovery
checks directories one to three levels below the selected folder; it does not
check the selected folder itself. Select a containing parent rather than the
server directory. Remote-only folders and private encrypted copies do not expose
these local server controls.

The Minecraft section groups servers into **Java** and **Bedrock** tabs. It starts
on Java when Java servers exist, otherwise Bedrock. Choose a server to show its
name, path and actions. Discovery does not start it or download a distribution.
Refresh Workspaces after adding or moving a server.

## Configure launching

For Java servers, create `logistics_cfg.ini` in the server directory:

```ini
[LaunchScript]
win = start.bat
mac = start.command
linux = start.sh

[Documentation]
wiki = https://minecraft.wiki/
```

Supply the script for your desktop OS and install its required Java runtime and
server files yourself. Script paths are resolved relative to the server directory,
which is also the launch working directory. A configured script makes the launch
button available; this is not a check that Java, the script or the server is healthy.

A directory containing `bedrock_server.exe` or `bedrock_server` is classified as
Bedrock, even when that executable belongs to a different OS. Launching Bedrock
requires `bedrock_server.exe` on Windows or executable `bedrock_server` on Linux.
There is no macOS Bedrock launch adapter. The Java script entries do not override
Bedrock detection. Bedrock can use the same optional `[Documentation]` setting.

## Use the controls

- **Launch Server** starts the configured script or matching Bedrock executable.
  Missing launch configuration or an unavailable Bedrock executable disables it.
- **Open Folder** opens the server directory in the system file manager.
- **server.properties** opens that file in the default external editor. Save
  there; Logistics does not apply changes to a running server. Restart or reload
  through the server's own controls as appropriate.
- **Open Wiki** opens the configured documentation URL in the browser. It is
  disabled when the wiki setting is absent.

These controls do not provide an embedded console, stop/restart control, process
status monitor or automatic Java/server installation. Use your launch script and
server console/logs to manage the running server and diagnose startup failures.

See [Using Logistics](../../../user/user.md) for navigation and settings.
