"""Bounded PDF contents destinations, read in memory without rendering pages."""
from dataclasses import dataclass
from io import BytesIO


@dataclass(frozen=True)
class Entry:
    label: str
    depth: int
    index: int


def contents(data):
    from pypdf import PdfReader
    from .document import MAX_PDF
    if not data or len(data) > MAX_PDF:
        raise ValueError('PDF contents are limited to 32 MiB.')
    entries = []
    with BytesIO(data) as stream:
        reader = PdfReader(stream)
        if reader.is_encrypted:
            raise ValueError('Contents are unavailable for this protected PDF.')
        pending = [(iter(reader.outline), 0)]
        visited = 0
        while pending:
            iterator, depth = pending[-1]
            item = next(iterator, None)
            if item is None:
                pending.pop()
                continue
            visited += 1
            if visited > 2000 or depth > 32:
                raise ValueError('This PDF contents tree is too large to display.')
            if isinstance(item, list):
                pending.append((iter(item), depth + 1))
                continue
            page = reader.get_destination_page_number(item)
            if page is not None and 0 <= page < len(reader.pages):
                entries.append(Entry(str(item.title or f'Page {page + 1}')[:500], depth, page))
    return tuple(entries)
