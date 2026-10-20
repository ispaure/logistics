"""Portable comic metadata snapshots for collection search and suggestions."""


def comic_values(reader):
    document = reader.document if hasattr(reader, "document") else reader
    fields = {}
    for key in document.info.FIELDS:
        try:
            fields[key] = document.info.get_field(key)
        except ValueError:
            continue
    return fields


def metadata_fields(reader):
    return {key: str(value)[:4096] for key, value in comic_values(reader).items()}
