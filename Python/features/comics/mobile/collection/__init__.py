"""Compatibility exports for portable collection operations."""

from features.comics.collection import (
    MAX_COMICS,
    MAX_ENTRIES,
    matches,
    suggestions,
    scan_comics,
    CollectionBatch,
    open_local_comic,
)


def metadata_fields(kind, reader):
    if kind == "epub":
        from features.books.library.metadata import metadata_fields as load

        return load("epub", reader)
    from features.comics.collection.metadata import metadata_fields as load

    return load(reader)
