# Set up and run Logistics

The [first document walkthrough](getting-started.md#1-prepare-your-environment)
takes you from a Git checkout to a local file you can open, edit, save and
reopen. You need Git, Python 3 and an internet connection for initial setup. Check the
[desktop platform requirements](../../../README.md#get-started) before you start.

## Desktop interpreter and lockfile

The setup command uses uv to install the dependencies from the lockfile in
`Python/` and puts the pinned Python 3.12.2 environment in `.venv` at the
checkout root. It uses the revision of commonUtils pinned by the checkout. If
you already cloned Logistics and the submodule is missing, preserve any edits
there before running `git submodule update --init --recursive`.

Use `python3 dev.py doctor` from the checkout root when diagnosing setup.
On Windows use `py` in place of `python3`. Doctor can report missing mobile
environments or native prerequisites even when desktop setup is ready.
To prepare a mobile host for tests, use the [testing guide](../testing/testing.md).
To stage or deploy a native app, use the [mobile build handbook](../build-release/mobile-handbook.md).

If macOS setup reports that it cannot verify the host boot identity, run it
in a local Terminal with access to `/usr/sbin/sysctl -n kern.bootsessionuuid`.

When changing a dependency, see the [project dependencies](../../../Python/pyproject.toml)
and update the lockfile with `uv lock --project Python`. Use a separate
environment to try interpreter or dependency changes.

### Set up without the project command

On macOS or Linux, run from the checkout root.

```sh
UV_PROJECT_ENVIRONMENT="$PWD/.venv" uv sync --project Python --locked --python 3.12.2
```

On Windows PowerShell:

```powershell
$env:UV_PROJECT_ENVIRONMENT = "$PWD/.venv"
uv sync --project Python --locked --python 3.12.2
```
