"""Mobile decoder policy over the shared desktop comic page ordering."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path
from features.comics.pages import comic_page_names

PAGE_TYPES = frozenset({".png", ".jpg", ".jpeg", ".webp"})


def validate_page_names(pages):
    if not pages:
        raise ValueError("The comic contains no PNG/JPEG/WebP pages.")
    if any(Path(name).suffix.lower() not in PAGE_TYPES for name in pages):
        raise ValueError(
            "The mobile comic reader currently supports PNG/JPEG/WebP pages only."
        )
    return pages


def page_names(archive):
    """Reject unsupported pages instead of silently changing comic positions."""
    return validate_page_names(comic_page_names(archive))
