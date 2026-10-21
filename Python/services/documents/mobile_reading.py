"""Presentation and lifecycle services injected into feature reader workflows."""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ReadingPresentation:
    seam: Callable[[Any], float | None]
    mode: Callable[[Any], str]
    layout_changed: Callable
    content_width: Callable[[str], int]
    private_label: Callable[[Any], str]
    speech_valid: Callable[[], bool]
    speech_presentation: object
    highlight_allowed: Callable[[], bool]
    comic_path: Callable
    notify_layout: Callable[[], None]
    themed_chapter: Callable

    seam_gap: Callable[[Any], float] = lambda view: 0
    page_region: Callable[[Any], tuple | None] = lambda view: None
    comic_boundary: Callable | None = None
    clear_comic_boundary: Callable = lambda: None
    comic_sharing: Callable[[], bool] = lambda: False
