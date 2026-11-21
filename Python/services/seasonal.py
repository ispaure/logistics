"""Shared local-calendar policy for decorative snow on desktop and mobile."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from datetime import date


def snow_enabled(enabled=True, high_contrast=False, today=None):
    today = today or date.today()
    return bool(enabled and not high_contrast and
                ((today.month, today.day) >= (12, 15) or (today.month, today.day) <= (1, 2)))
