"""Explicit presentation services for feature-owned read-aloud controls."""

from dataclasses import dataclass
from typing import Callable
from types import SimpleNamespace
import toga


def apply_icon(button, name, label):
    button.control_icon = name
    button.accessible_name = label
    button.text = label


def icon_button(name, label, **kwargs):
    button = toga.Button(label, **kwargs)
    apply_icon(button, name, label)
    return button


def accessible_name(widget, label):
    widget.accessible_name = label


def inline_overlay(panel, owner, *, anchor=None):
    owner.add(panel)
    return SimpleNamespace(
        close=lambda: owner.remove(panel) if panel in owner.children else None,
        reposition=lambda: None,
    )


@dataclass(frozen=True)
class SpeechPresentation:
    icon_button: Callable = icon_button
    apply_icon: Callable = apply_icon
    surface: Callable = lambda widget, **kwargs: widget
    accessible_name: Callable = accessible_name
    overlay: Callable = inline_overlay
    voice: Callable = lambda: ""
    playback: Callable = lambda panel, **kwargs: None
