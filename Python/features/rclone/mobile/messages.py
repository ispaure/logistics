"""Narrow-screen remote-operation messages without UI imports."""
from textwrap import fill


def import_hint(text):
    # Toga's native Label is single-line by default. Explicit short lines
    # keep the next action visible on narrow phones without clipping.
    return '\n'.join(fill(line, width=38) for line in text.splitlines())
