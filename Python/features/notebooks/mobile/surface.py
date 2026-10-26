"""Touch presentation composed with the common offline notebook engine."""
from ..canvas import editor_html


def mobile_editor_html(state, bridge, *, console_bridge=False):
    return editor_html(state, bridge, console_bridge=console_bridge, mobile=True)
