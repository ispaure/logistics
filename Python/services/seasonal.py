"""Shared local-calendar policy for decorative snow on desktop and mobile."""
from datetime import date


def snow_enabled(enabled=True, high_contrast=False, today=None):
    today = today or date.today()
    return bool(enabled and not high_contrast and
                ((today.month, today.day) >= (12, 15) or (today.month, today.day) <= (1, 2)))
