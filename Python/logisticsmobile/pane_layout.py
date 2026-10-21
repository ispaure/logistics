"""Portable workspace pane allocation; physical divisions override preferences."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PaneLayout:
    axis: str
    leading: float
    gap: float
    trailing: float


def panes(width, height, *, fold=None, browser_priority=False):
    """Allocate local points, including the whole fold's interaction margins."""
    width, height = max(1, width), max(1, height)
    if fold is not None:
        extent = width if fold.vertical else height
        start, thickness = (fold.x, fold.width) if fold.vertical else (fold.y, fold.height)
        if 0 < start < start + thickness < extent:
            return PaneLayout('row' if fold.vertical else 'column', start,
                              thickness, extent - start - thickness)
    gap = min(16, width / 10)
    usable = width - gap
    # Keep workspace labels usable, without taking half of a broad file browser.
    preferred = max(180, min(320, usable / 3)) if browser_priority else usable / 2
    leading = min(preferred, max(1, usable - 320)) if browser_priority else preferred
    return PaneLayout('row', leading, gap, usable - leading)
