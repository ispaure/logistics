# Perforce Feature

Developer notes. See the [user guide](user_docs/index.md) for controls and setup,
and [UI architecture](../UI_ARCHITECTURE.md) for shared contribution conventions.

Offers a Launch P4D action for configured local folders. Launching is supported only on Linux; the action is disabled on other platforms.

## Configuration

Place `remoteConfig.ini` in the local folder:

```ini
[Perforce]
p4d_path = p4d
data_path = data
port = 1666
```

Both paths are relative to the selected folder, which is the working directory. All three settings must be present for the folder to receive the Perforce section. Supply the P4D executable and server data separately.

The button reads `server.id` from the configured data directory and displays its trimmed, uppercase contents with the port, for example `Launch P4D MY-SERVER (Port: 1666)`. If `server.id` is missing, empty, or unreadable, the button displays `Launch P4D (Port: 1666)`.

The action launches `./<p4d_path> -C1 -r ./<data_path> -p <port>` in a new terminal. It does not provide provisioning, stop controls, or health monitoring.

`Open P4 Console` opens an interactive Bash terminal in the server folder on Linux. Place the executable `p4` client alongside `remoteConfig.ini`, or install it on your system PATH. The button is disabled when no client is found. Start the server before issuing commands.

The console defines a shell function supplying the client path and configured server
address (numeric ports become `localhost:<port>`). Preserve interactive password
prompts and explicit port selection, which prevents a P4 config file from redirecting
commands to a different server. Console command examples belong to the user guide.

## Structure

- `detection.py`: reads folder settings.
- `actions.py`: Linux launch implementation.
- `ui_contributions.py`: Folders action and platform availability.

No startup initialization or rclone dependency is required.
