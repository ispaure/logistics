"""Presentation and lifecycle services injected into feature reader workflows."""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ReadingPresentation:
    seam: Callable
    mode: Callable
    layout_changed: Callable
    content_width: Callable
    private_label: Callable
    speech_valid: Callable
    speech_presentation: object
    highlight_allowed: Callable
    comic_path: Callable
    notify_layout: Callable
    themed_chapter: Callable
