"""Calibre OPF naming and filename normalization, without filesystem writes."""

from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET

from commonUtils.filesystem import directories as dirUtils



def get_clean_book_name(book_directory: dirUtils.Directory) -> str:
    """
    Returns the Calibre book folder name without its trailing internal Calibre ID.

    Example:
        "Book Title (1234)"
    becomes:
        "Book Title"
    """
    return re.sub(r'\s+\(\d+\)$', '', book_directory.name)


def normalize_series_index(series_index: str) -> str:
    """
    Simplifies Calibre series indexes such as 21.00 to 21 while preserving
    meaningful decimal values such as 21.5.
    """
    if '.' in series_index:
        series_index = series_index.rstrip('0').rstrip('.')

    return series_index


def normalize_path(path: Path) -> str:
    """
    Returns an NFC-normalized path string for reliable Unicode comparisons.

    Filesystems can represent accented characters using different Unicode
    compositions while displaying the same filename.
    """
    return unicodedata.normalize('NFC', str(path))


def sanitize_file_name(file_name: str) -> str:
    """
    Removes or replaces characters that are unsafe or undesirable in filenames.

    All dash variants and substituted characters use the standard ASCII dash (-).
    Unicode characters are normalized to NFC for consistent filesystem names.
    """
    file_name = unicodedata.normalize('NFC', file_name)
    file_name = re.sub(r'[‐-‒–—―]', '-', file_name)
    file_name = re.sub(r'[\\/:*?"<>|]+', ' - ', file_name)
    file_name = re.sub(r'\s*-\s*-\s*', ' - ', file_name)
    file_name = re.sub(r'\s*-\s*', ' - ', file_name)
    file_name = re.sub(r'\s+', ' ', file_name)
    file_name = file_name.strip(' .-')

    return file_name


def title_contains_series(title: str, series: str) -> bool:
    """
    Returns True when the title already starts with the series name.

    Punctuation between the series name and the rest of the title is allowed.
    """
    normalized_title = re.sub(r'\s+', ' ', title).strip().casefold()
    normalized_series = re.sub(r'\s+', ' ', series).strip().casefold()

    if normalized_title == normalized_series:
        return True

    if not normalized_title.startswith(normalized_series):
        return False

    remainder = normalized_title[len(normalized_series):]

    return not remainder or bool(re.match(r'^[\s,:;\-‐-‒–—―()\[\]]', remainder))


def title_contains_series_index(title: str, series_index: str) -> bool:
    """
    Returns True when the title already appears to contain the series index.

    Examples:
        "Book Volume 6" with index 6
        "Book Vol. 6" with index 6
        "Book Vol 6" with index 6
    """
    escaped_index = re.escape(series_index)

    patterns = [
        rf'\bvolume\s*0*{escaped_index}\b',
        rf'\bvol\.?\s*0*{escaped_index}\b',
    ]

    for pattern in patterns:
        if re.search(pattern, title, re.IGNORECASE):
            return True

    return False


def get_metadata_book_name(book_directory: dirUtils.Directory) -> str | None:
    """
    Builds a human-readable book name from Calibre's metadata.opf.

    Examples:
        Title
        Series - Title
        Series - Title - Vol 5
        Title Volume 5

    Duplicate information is avoided where possible:
    - The series is not prepended if the title already starts with it.
    - Punctuation after the series name is tolerated.
    - The series index is not appended if the title already contains the same volume.
    """
    metadata_path = book_directory.path / 'metadata.opf'

    if not metadata_path.is_file():
        return None

    try:
        root = ET.parse(metadata_path).getroot()
    except (ET.ParseError, OSError):
        return None

    title = None
    series = None
    series_index = None

    for element in root.iter():
        element_name = element.tag.split('}')[-1]

        if element_name == 'title' and element.text and title is None:
            title = element.text.strip()

        if element_name == 'meta':
            metadata_name = element.attrib.get('name')
            metadata_content = element.attrib.get('content')

            if metadata_name == 'calibre:series' and metadata_content:
                series = metadata_content.strip()
            elif metadata_name == 'calibre:series_index' and metadata_content:
                series_index = normalize_series_index(metadata_content.strip())

    if not title and not series:
        return None

    if title:
        book_name = title

        if series and not title_contains_series(title, series):
            book_name = f'{series} - {title}'
    else:
        book_name = series

    if series and series_index and not title_contains_series_index(book_name, series_index):
        book_name = f'{book_name} - Vol {series_index}'

    return sanitize_file_name(book_name)
