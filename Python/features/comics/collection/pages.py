"""Mobile decoder policy over the shared desktop comic page ordering."""

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
