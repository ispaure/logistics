"""Portable EPUB form values and mixed-format catalogue adapters."""

from features.books.metadata import EDITABLE
from features.comics.collection.metadata import comic_values


def values(book):
    original = {key: book.values(key) for key in EDITABLE}
    return {
        key: "\n".join(value)
        if key in {"creator", "subject"}
        else next(iter(value), "")
        for key, value in original.items()
    }, original


def patch(initial, edited, original):
    return {
        key: value.splitlines()
        if key in {"creator", "subject"}
        else [value] + original[key][1:]
        for key, value in edited.items()
        if key in initial and value != initial[key]
    }


def catalogue_values(book):
    """Canonical collection fields shared with comic author/tag suggestions."""
    edited, _ = values(book)
    mapping = {
        "title": "Title",
        "creator": "Writer",
        "subject": "Tags",
        "publisher": "Publisher",
        "description": "Summary",
        "language": "LanguageISO",
        "identifier": "GTIN",
    }
    return {mapping.get(key, key): value for key, value in edited.items()}


def metadata_fields(kind, reader, *, loaders=None):
    """Dispatch only supplied format readers; never open storage or load a UI."""
    loaders = (
        {"epub": catalogue_values, "comic": comic_values}
        if loaders is None
        else loaders
    )
    return {key: str(value)[:4096] for key, value in loaders[kind](reader).items()}
