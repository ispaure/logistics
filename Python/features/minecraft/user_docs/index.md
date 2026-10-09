# Manage Minecraft servers

Minecraft controls appear for servers discovered below a selected local folder
on **Folder Hub**. A directory with `server.properties` is recognized as a server;
searching is limited to one to three directory levels.

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

Supply scripts for the platforms you use; paths are relative to the server folder.
Bedrock needs the matching Windows/Linux server executable. A Linux executable
must have execute permission. Logistics does not download server distributions.

## Use the controls

1. Select the containing local folder on Folders.
2. Choose a server in the Minecraft section.
3. Launch it, open its folder/documentation, or edit its properties.

Property changes modify `server.properties`. Missing launch settings or executables
prevent launching; discovery does not start a server. Check your script and server
logs when launch fails. These controls do not replace the server's own console.

## More help

Read [Using Logistics](../../../../USER_GUIDE.md) for navigation, resources and
feature controls. Use Back/Forward in this viewer to return to a previous guide.
