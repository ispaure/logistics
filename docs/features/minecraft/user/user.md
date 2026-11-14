# Manage Minecraft servers

Enable **Minecraft Server** in **Settings → Features**, then choose a local
parent folder in **Workspaces**. See [mobile availability](../user_mobile/user_mobile.md).

## Find a server

Logistics looks one to three levels below the selected folder for
**server.properties**. Select a containing directory and choose the server
under **Java** or **Bedrock**. Refresh after adding or moving a server.

## Configure launching

For Java, install the required runtime and server files, then add the
applicable launch script to **logistics_cfg.ini** in the server directory.

```ini
[LaunchScript]
win = start.bat
mac = start.command
linux = start.sh
```

Bedrock needs **bedrock_server.exe** on Windows or executable **bedrock_server**
on Linux. macOS has no Bedrock launch action. Set **wiki** in **Documentation**
to enable **Open Wiki**.

## Use the controls

Use **Launch Server** to start it and **Open Folder** to inspect its files.
**server.properties** opens the file in your editor. Reload or restart through
the server's own controls after saving. Use its console and logs for failures.

See [Using Logistics](../../../user/user.md).
