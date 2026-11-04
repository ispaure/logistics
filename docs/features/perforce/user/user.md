# Launch a local Perforce server

Enable **Perforce Server** under **Settings → Features** to use these tools.

Perforce controls are offered for configured local folders. Launch and console
actions require Linux desktop and separately supplied Perforce executables/data.
There are no corresponding Android/iOS controls; see [mobile availability](../user_mobile/user_mobile.md).

## Configure the folder

Place `remoteConfig.ini` in the local folder:

```ini
[Perforce]
p4d_path = p4d
data_path = data
port = 1666
```

Relative paths are resolved from that folder; absolute paths are also accepted.
All three values are needed. An optional
`server.id` in the data folder is shown in the launch button.

## Start and use the console

1. Select the configured local folder on **Workspaces**.
2. Choose **Launch P4D** and inspect the new terminal.
3. Use **Open P4 Console** after the server has started.

Supply an executable `p4` client beside `remoteConfig.ini`, or put it on PATH.
The console supplies the configured server address automatically. Commands such
as `p4 info` use that server; interactive password prompts work normally.

Logistics provides no server stop controls, provisioning or health monitoring.
Manage the server process from its terminal or your usual service tools.

## More help

See [Using Logistics](../../../user/user.md) for navigation and settings.

This is a local server launcher, not a Perforce changelist or workspace client.
Missing controls usually mean the selected folder is not local or lacks the
required `[Perforce]` settings; disabled launch controls on Windows/macOS reflect the Linux-only support.
Server data persists at the configured `data_path`; closing Logistics does not
provide a server stop operation.

## Troubleshooting

The folder section detects configuration, not server readiness. Before launching,
check that the configured P4D path exists, is executable and can access the data
directory and port. The console also prefers a local `p4` file over PATH, so ensure
that local client is executable or remove it to use the installed client.

A numeric `port`, such as `1666`, becomes `localhost:1666` in the console. An
explicit address, such as `localhost:1666`, is passed through. Type `p4 info` to
query the configured server; the launcher does not wait for it to become ready.
The console runs interactive Bash and supplies the server using `-p` on each
`p4` invocation. Review terminal errors there: Logistics does not turn a successful
terminal launch into confirmation that the server or client command succeeded.
