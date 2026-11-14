# Perforce Feature

Start a configured local P4D server and open a console from **Workspaces**.
The action callbacks run on Linux desktop. Other desktop platforms show
disabled buttons for eligible folders. See the [user guide](../user/user.md)
for configuration and [mobile availability](../user_mobile/user_mobile.md)
for the platform boundary.

## Try a console label change

Enable **Perforce Server** in **Settings → Features**. Create a disposable
folder under your configured local workspace root (by default
`~/Server/Local`) and give it this `remoteConfig.ini`:

```ini
[Perforce]
p4d_path = p4d
data_path = data
port = 27182
```

In **Workspaces → Local → On This Computer**, select the folder and look for
**Open P4 Console (Port: 27182)** under **Actions → Perforce**. The console
button also requires an executable `p4` in the folder or on PATH to be enabled
on Linux. Inspect the label without starting a server.

Try changing **Open P4 Console** to **Open Perforce Console** in
`Python/features/perforce/ui_contributions.py` (`_get_actions`). Keep the
configured port in the label. Update the expected button name in
`test_console_forwards_arguments_and_keeps_connection_in_interactive_shell`.
Run from the repository root after [desktop setup](../../../development/setup/getting-started.md):

```sh
python3 dev.py test desktop --exact-file Python/tests/integrations/test_perforce.py
```

Expect four passes on a POSIX host. The console test mocks Linux and the terminal
launch, then runs a stub client in Bash and checks the button label and explicit
server arguments. The Bash and executable-permission cases skip on non-POSIX
hosts. On relaunch, the selected folder should show the revised button label.

## Configuration

`detection.py` reads the three settings from the selected folder.
Relative paths resolve from that folder, which is also the working directory.
Absolute paths are accepted. Supply the P4D executable and its data separately.
The optional `server.id` is read as UTF-8 with an optional BOM, trimmed and
uppercased for display. Missing, blank or unreadable IDs leave the name out of
the button. An executable local `p4` takes precedence over `shutil.which('p4')`.
A non-executable local file falls back to PATH.

## Availability and lifecycle

`Python/features/perforce/__init__.py:register` publishes a
`FolderFeatureContribution` from `ui_contributions.py`.
`_is_available` checks for a local `FolderEntry` and the three configuration
keys. File permissions, data readiness and server health are separate runtime
concerns. The action callbacks independently enforce the Linux gate.

`actions.py:launch_server` launches
`<resolved-p4d-path> -C1 -r <resolved-data-path> -p <port>` in a new terminal.
Keep argument boundaries with `shlex.join`. `open_console` opens interactive
Bash with `P4PORT` and an exported `p4` function that supplies explicit `-p`
on each call. Numeric ports become `localhost:<port>`. Explicit addresses
pass through. Bash owns interactive password prompts.

The shared terminal wrapper indicates launch success unless it returns
`False`. Server startup, readiness, login and shutdown belong to the
terminal or normal Perforce tools. Use the terminal output and `p4 info`
to diagnose connection or readiness failures. The focused tests validate
arguments and failure propagation using fixtures. Live server connectivity
and native terminal availability require Linux runtime checks.

See [feature conventions](../../../development/architecture/features.md) for the shared
folder contribution contract.
