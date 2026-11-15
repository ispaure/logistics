# Set up and run Logistics

Follow [your first contribution](getting-started.md) to clone with the pinned
shared library, install the locked desktop environment and launch the app. The
walkthrough uses synthetic files and local checks.

Run `python3 dev.py doctor` from the repository root to inspect prerequisites.
On Windows use `py` in place of `python3`. A desktop setup can pass while doctor
reports missing mobile tools. For packaging and native platform setup, see the
[mobile build handbook](../build-release/mobile-handbook.md).

## Desktop interpreter and lockfile

If a checkout is missing its submodules, preserve local edits before running
`git submodule update --init --recursive`. The desktop interpreter is
Python 3.12.2. See the [desktop platform requirements](../../../README.md#get-started)
and [project dependency pins](../../../Python/pyproject.toml). To update the
lockfile, use `uv lock --project Python`. Use a separate environment for
runtime experiments.

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
