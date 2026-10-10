"""Page-spread decisions and naturally ordered neighbouring comic files."""

from pathlib import Path
from commonUtils.filesystem.directories import Directory
from .pages import natural_key

SPREAD_GAP = 8


def comic_siblings(path):
    path = Path(path)
    return sorted((item.path for item in Directory(path.parent).list_files(recursive=False, filter_extension='cbz')
                   if item.path.is_file() and not item.path.is_symlink()), key=lambda item: natural_key(item.name))


def visible_pages(start, sizes, viewport, mode='auto', double_pages=()):
    first = sizes.get(start)
    second = sizes.get(start + 1)
    if first is None or second is None or mode == 'single':
        return (start,)
    if start in double_pages or start + 1 in double_pages:
        return (start,)
    ratios = [width / height for width, height in (first, second)]
    if any(ratio >= 1 for ratio in ratios):
        return (start,)
    width, height = viewport
    if mode == 'double' or width >= sum(ratios) * max(1, height) + SPREAD_GAP:
        return (start, start + 1)
    return (start,)
