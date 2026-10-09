# Launch a local Perforce server

Perforce controls are offered for configured local folders. Launch and console
actions require Linux and separately supplied Perforce executables/data.

## Configure the folder

Place `remoteConfig.ini` in the local folder:

```ini
[Perforce]
p4d_path = p4d
data_path = data
port = 1666
```

Paths are relative to that folder. All three values are needed. An optional
`server.id` in the data folder is shown in the launch button.

## Start and use the console

1. Select the configured local folder on **Folder Hub**.
2. Choose **Launch P4D** and inspect the new terminal.
3. Use **Open P4 Console** after the server has started.

Supply an executable `p4` client beside `remoteConfig.ini`, or put it on PATH.
The console supplies the configured server address automatically. Commands such
as `p4 info` use that server; interactive password prompts work normally.

Logistics provides no server stop controls, provisioning or health monitoring.
Manage the server process from its terminal or your usual service tools.

## More help

Read [Using Logistics](../../../../USER_GUIDE.md) for navigation, resources and
feature controls. Use Back/Forward in this viewer to return to a previous guide.
