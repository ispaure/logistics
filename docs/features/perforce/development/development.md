# Perforce Feature

For workflows, settings and troubleshooting, see the [user guide](../user/user.md).

See [feature conventions](../../../development/features.md) for shared contribution contracts.

Offers a Launch P4D action for configured local folders. Launching is supported only on Linux; the action is disabled on other platforms.

## Configuration

Place `remoteConfig.ini` in the local folder:

```ini
[Perforce]
p4d_path = p4d
data_path = data
port = 1666
```

Relative paths resolve from the selected folder, which is the working directory;
absolute paths are accepted. All three settings must be present for the folder to receive the Perforce section. Supply the P4D executable and server data separately.

The button reads `server.id` from the configured data directory and displays its trimmed, uppercase contents with the port, for example `Launch P4D MY-SERVER (Port: 1666)`. If `server.id` is missing, empty, or unreadable, the button displays `Launch P4D (Port: 1666)`.

The action resolves the executable and data paths, then launches
`<resolved-p4d-path> -C1 -r <resolved-data-path> -p <port>` in a new terminal.
`shlex.join` preserves argument boundaries, including spaces in either path. It does not provide provisioning, stop controls, or health monitoring.

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

## Availability and lifecycle

`_is_available` requires a local `FolderEntry` and the three configuration keys;
remote-only entries do not receive this contribution. Contribution availability
does not validate client permissions, data-directory readiness or a running server. Both action
callbacks independently reject non-Linux execution. In `detection.py`, client
discovery prefers a local `p4` only if it is a regular executable file.
Otherwise it tries `shutil.which('p4')`. `test_perforce.py` covers fallback
when the local file lacks execute permission.

The terminal wrapper returning anything except `False` is treated as launch
success. The feature does not own or await the resulting server process, perform
login, or manage server storage. Interactive console commands use an exported
Bash function with an explicit `-p` argument and `P4PORT`; numeric ports are
qualified with `localhost:`. No password is collected by Logistics.

`services/mobile_features.py` has no Perforce entry and `mobile_build/tools.py`
does not package this feature as a source owner. There is no Android/iOS folder
action or console adapter; see [mobile availability](../user_mobile/user_mobile.md).
Reusable Perforce wrapper APIs belong in commonUtils' own documentation; this
guide covers the Logistics folder integration only.

## Validation

`Python/tests/integrations/test_perforce.py` covers resolved launch arguments and
failure propagation, client PATH fallback, missing-client handling, and a POSIX
interactive Bash fixture that verifies explicit server and argument forwarding.
It uses a stub client rather than provisioning a real P4D server. Changes can be
checked through the owning desktop test entry point:

```sh
python3 dev.py test desktop test_perforce.py
```

The November 4, 2026 documentation audit read these tests and the feature source,
then checked Markdown structure and links. No tests, Qt, terminal/server launches,
builds or device validation ran during the release quiet hold. This review does
not establish live-server connectivity, terminal availability or native acceptance.
