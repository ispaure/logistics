"""Isolated retained compression-comparison attempts under the owning results root."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path
from tempfile import mkdtemp


def comparison_workspace(output=None):
    if output is None:
        return Path(mkdtemp(prefix='logistics-zip-version-parity-'))
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    return Path(mkdtemp(prefix='attempt-', dir=output))
