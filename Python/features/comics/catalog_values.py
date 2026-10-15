"""Portable metadata suggestion fields and Unicode value normalization."""

LIST_FIELDS = frozenset(('Writer', 'Penciller', 'Inker', 'Colorist', 'Letterer',
                         'CoverArtist', 'Editor', 'Translator', 'Genre', 'Tags',
                         'Characters', 'Teams', 'Locations', 'StoryArc', 'SeriesGroup'))
VALUE_FIELDS = frozenset(('Publisher', 'Imprint', 'Format'))
CATALOG_FIELDS = LIST_FIELDS | VALUE_FIELDS


def normalize_value(text):
    """Suggestions are single-line text with consistent Unicode whitespace."""
    return ' '.join(text.split())


def split_values(text):
    """Comma-separated XML values; text-entry mode also accepts one per line."""
    return list(dict.fromkeys(normalize_value(value) for value in text.replace('\r', '\n').replace('\n', ',').split(',')
                             if normalize_value(value)))
