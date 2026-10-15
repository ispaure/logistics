"""EPUB metadata form values and sparse patches shared by native hosts."""
from features.books.metadata import EDITABLE


def values(book):
    original = {key: book.values(key) for key in EDITABLE}
    return {key: '\n'.join(value) if key in {'creator', 'subject'} else next(iter(value), '')
            for key, value in original.items()}, original


def patch(initial, edited, original):
    return {key: value.splitlines() if key in {'creator', 'subject'} else [value] + original[key][1:]
            for key, value in edited.items() if key in initial and value != initial[key]}


def catalogue_values(book):
    """Canonical collection fields shared with comic author/tag suggestions."""
    edited, _ = values(book)
    mapping = {'title': 'Title', 'creator': 'Writer', 'subject': 'Tags', 'publisher': 'Publisher',
               'description': 'Summary', 'language': 'LanguageISO', 'identifier': 'GTIN'}
    return {mapping.get(key, key): value for key, value in edited.items()}
