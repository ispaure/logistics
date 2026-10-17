"""Memory-only PDF text search, shared by desktop and mobile readers."""
from dataclasses import dataclass
from io import BytesIO
import re
from commonUtils.runtime.operations import check_cancelled

MAX_MATCHES = 1000
MAX_TEXT = 8 * 1024 * 1024


@dataclass(frozen=True)
class Match:
    page: int
    snippet: str


@dataclass(frozen=True)
class Results:
    matches: tuple
    limited: bool = False


def search_pdf(data, query, *, cancelled=lambda: False):
    """Search embedded text; no OCR, filesystem access or persistent index."""
    query = ' '.join(str(query).split())
    if not query:
        return Results(())
    if len(query) > 256:
        raise ValueError('Search is limited to 256 characters.')
    check_cancelled(cancelled)
    from pypdf import PdfReader
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    matches, text_size = [], 0
    with BytesIO(data) as stream:
        reader = PdfReader(stream)
        try:
            if reader.is_encrypted:
                raise ValueError('Password-protected PDF search is unavailable.')
            if len(reader.pages) > 10000:
                raise ValueError('Search is limited to 10,000 pages.')
            for index, page in enumerate(reader.pages):
                check_cancelled(cancelled)
                content = page.get_contents()
                if content is not None and len(content.get_data()) > MAX_TEXT:
                    raise ValueError('This PDF page is too complex to search.')
                text = ' '.join((page.extract_text() or '').split())
                check_cancelled(cancelled)
                text_size += len(text)
                if text_size > MAX_TEXT:
                    raise ValueError('PDF text exceeds the 8 MiB search limit.')
                for found in pattern.finditer(text):
                    if len(matches) == MAX_MATCHES:
                        return Results(tuple(matches), limited=True)
                    start, end = found.span()
                    snippet = ('…' if start > 55 else '') + text[max(0, start - 55):end + 80]
                    if end + 80 < len(text):
                        snippet += '…'
                    matches.append(Match(index, snippet))
            return Results(tuple(matches))
        finally:
            reader.close()


def result_text(results, cursor):
    if not results.matches:
        return 'No matches. Scanned pages need a searchable text layer.'
    match = results.matches[cursor]
    return f'Match {cursor + 1} of {len(results.matches)}{"+" if results.limited else ""} · Page {match.page + 1}\n{match.snippet}'
