"""Load packaged, offline notebook assets by their explicit owner-relative name."""
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).with_name('assets')


@lru_cache(maxsize=None)
def asset(name):
    if Path(name).name != name:
        raise ValueError('Notebook assets must be direct children of assets/.')
    return (_ROOT / name).read_text(encoding='utf-8')
