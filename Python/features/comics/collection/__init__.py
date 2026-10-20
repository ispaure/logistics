"""Bounded portable collection search, suggestions and recursive comic plans."""

from pathlib import PurePosixPath
from features.comics.catalog_values import (
    CATALOG_FIELDS,
    LIST_FIELDS,
    split_values,
    normalize_value,
)
from commonUtils.runtime.operations import check_cancelled

MAX_COMICS = 200
MAX_ENTRIES = 10000


def matches(name, fields, query):
    haystack = "\n".join([name, *fields.values()]).casefold()
    return all(token in haystack for token in query.casefold().split())


def suggestions(snapshots):
    result = {}
    for fields in snapshots:
        for field in CATALOG_FIELDS:
            value = fields.get(field, "")
            items = (
                split_values(value)
                if field in LIST_FIELDS
                else [normalize_value(value)]
            )
            target = result.setdefault(field, set())
            target.update(item for item in items if item and len(item) <= 200)
            if len(target) > 1000:
                result[field] = set(
                    sorted(target, key=lambda text: (text.casefold(), text))[:1000]
                )
    return {
        field: sorted(items, key=lambda text: (text.casefold(), text))[:1000]
        for field, items in result.items()
    }


def scan_comics(provider, folder, *, cancelled=lambda: False):
    """Provider owns path/link rules; reject escaping rows and oversized scans."""
    folder = provider.relative(folder)
    pending, seen, found, scanned = [(folder, 0)], set(), [], 0
    while pending:
        check_cancelled(cancelled)
        current, depth = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        if depth > 16:
            raise ValueError("Comic collection nesting exceeds 16 folders.")
        for row in provider.list(current):
            check_cancelled(cancelled)
            scanned += 1
            if scanned > MAX_ENTRIES:
                raise ValueError(
                    "Choose a smaller folder: scans are limited to 10,000 entries."
                )
            path = provider.relative(row["path"])
            if str(PurePosixPath(path).parent) != (current or "."):
                raise ValueError(
                    "Provider returned a comic outside the selected folder."
                )
            if row["directory"]:
                if not row["name"].startswith("."):
                    pending.append((path, depth + 1))
            elif PurePosixPath(path).suffix.lower() in (".cbz", ".zip"):
                found.append(dict(row))
                if len(found) > MAX_COMICS:
                    raise ValueError("Choose at most 200 comics per batch.")
    from features.comics.pages import natural_key

    return sorted(found, key=lambda row: natural_key(row["path"]))


class CollectionBatch:
    """Hosts inject publication; feature validates every baseline before writing."""

    def __init__(self, entries, *, open_document, revision, publish):
        self.entries, self.open_document, self.revision, self.publish = (
            entries,
            open_document,
            revision,
            publish,
        )
        self.documents = [open_document(row["path"]) for row in entries]

    def apply(self, changes, *, cancelled=lambda: False):
        for row, document in zip(self.entries, self.documents):
            check_cancelled(cancelled)
            if self.revision(row["path"]) != row["revision"]:
                raise ValueError("A selected comic changed. Reopen the folder batch.")
            document.prepare_metadata(changes)
        completed, failures = [], []
        for index, (row, document) in enumerate(zip(self.entries, self.documents)):
            if cancelled():
                break
            try:
                self.publish(row["path"], document, changes)
                row["revision"] = self.revision(row["path"])
                self.documents[index] = self.open_document(row["path"])
                completed.append(row["path"])
            except Exception as error:
                failures.append((row["path"], str(error)))
        return completed, failures


def open_local_comic(path):
    """Ordinary folder batches require a supported unencrypted archive writer."""
    from zipfile import ZipFile
    from features.comics.library import ComicDocument

    with ZipFile(path) as archive:
        from .pages import page_names

        page_names(archive)
        if any(info.flag_bits & 1 for info in archive.infolist()):
            raise ValueError("Encrypted standalone comics cannot be batch rewritten.")
    return ComicDocument(path)
