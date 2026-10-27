"""Isolated retained compression-comparison attempts under the owning results root."""
from pathlib import Path
from tempfile import mkdtemp


def comparison_workspace(output=None):
    if output is None:
        return Path(mkdtemp(prefix='logistics-zip-version-parity-'))
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    return Path(mkdtemp(prefix='attempt-', dir=output))
