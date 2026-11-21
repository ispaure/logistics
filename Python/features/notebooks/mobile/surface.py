"""Touch presentation composed with the common offline notebook engine."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from ..canvas import editor_html


def mobile_editor_html(state, bridge, *, console_bridge=False, stylesheet='', paper_preview=True):
    return editor_html(state, bridge, console_bridge=console_bridge, mobile=True, stylesheet=stylesheet, paper_preview=paper_preview)
