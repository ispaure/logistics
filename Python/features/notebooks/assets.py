"""Load packaged, offline notebook assets by their explicit owner-relative name."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).with_name('assets')


def _asset_path(name):
    if Path(name).name != name:
        raise ValueError('Notebook assets must be direct children of assets/.')
    return _ROOT / name


@lru_cache(maxsize=None)
def asset(name):
    return _asset_path(name).read_text(encoding='utf-8')


def asset_bytes(name):
    return _asset_path(name).read_bytes()
