# Launch a local Perforce server

Enable **Perforce Server** in **Settings → Features** on Linux desktop.

## Configure the folder

Place `remoteConfig.ini` in a local folder. Paths can be absolute or folder-relative.

```ini
[Perforce]
p4d_path = p4d
data_path = data
port = 1666
```

## Start and use the console

Select the folder in **Workspaces**, choose **Launch P4D**, then
**Open P4 Console** after startup. Run `p4 info` to check readiness.
A numeric port becomes `localhost:1666`; explicit addresses pass through.
Stop the server from its terminal or service tools.

## More help

See [Using Logistics](../../../user/user.md) and [mobile availability](../user_mobile/user_mobile.md).

## Troubleshooting

Check all three keys, executable permissions, data access and port availability.
The console uses an executable `p4` beside the INI or on PATH. Windows and macOS
can show configured controls with launch and console disabled.
