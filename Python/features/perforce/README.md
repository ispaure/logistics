# Perforce Feature

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

The action launches `./<p4d_path> -C1 -r ./<data_path> -p <port>` in a new terminal. It does not provide provisioning, stop controls, or health monitoring.

## Structure

- `detection.py`: reads folder settings.
- `actions.py`: Linux launch implementation.
- `ui_contributions.py`: Folders action and platform availability.

No startup initialization or rclone dependency is required.
