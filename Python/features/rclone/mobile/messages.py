"""Narrow-screen remote-operation messages without UI imports."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from textwrap import fill


def import_hint(text):
    # Toga's native Label is single-line by default. Explicit short lines
    # keep the next action visible on narrow phones without clipping.
    return '\n'.join(fill(line, width=38) for line in text.splitlines())
