"""Portable EPUB text locations, contents destinations and chapter search.

Offsets count UTF-16 code units, matching browser DOM Ranges and Qt positions.
A location is meaningful only within its spine resource; hosts own persistence.
"""
from dataclasses import dataclass
from array import array
from html.parser import HTMLParser
from .epub import resolve_href

MAX_OFFSET = 16 * 1024 * 1024


def valid_location(value):
    return (isinstance(value, dict) and set(value) == {'path', 'offset'}
            and isinstance(value['path'], str) and 0 < len(value['path']) <= 4096
            and type(value['offset']) is int and 0 <= value['offset'] <= MAX_OFFSET)


def utf16_length(text):
    return len(text.encode('utf-16-le')) // 2


@dataclass(frozen=True)
class Destination:
    label: str
    index: int
    fragment: str = ''
    depth: int = 0


def contents(book):
    indices = {path: index for index, path in enumerate(book.spine)}
    return [Destination(chapter.label, indices[chapter.path], chapter.fragment, chapter.depth)
            for chapter in book.chapters if chapter.path in indices]


def link_destination(book, index, href):
    path, fragment = resolve_href(book.spine[index], href)
    if path not in book.spine:
        raise ValueError('The link is not in this book’s reading order.')
    return book.spine.index(path), fragment


class ChapterText(HTMLParser):
    """Index sanitized body text exactly as DOM text nodes count it."""
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.parts, self.anchors, self.length, self.body = [], {}, 0, False
        self.language = ''
        self.breaks = set()
        self.links, self._link = [], None
        self.feed(html)
        self.text = ''.join(self.parts)

    def handle_starttag(self, tag, attrs):
        if tag in {'html', 'body'}:
            self.language = dict(attrs).get('lang') or dict(attrs).get('xml:lang') or self.language
        if tag == 'body':
            self.body = True
        if self.body:
            attrs = dict(attrs)
            if tag == 'a' and attrs.get('href', '').startswith('reader-link:'):
                self._link = (attrs['href'][len('reader-link:'):], [])
            for key in ('id', 'name'):
                if attrs.get(key):
                    self.anchors.setdefault(attrs[key], self.length)

    def handle_endtag(self, tag):
        if self.body and tag in {'p', 'div', 'li', 'h1', 'h2', 'h3', 'tr', 'blockquote', 'section'}:
            self.breaks.add(self.length)
        if tag == 'a' and self._link is not None:
            from urllib.parse import unquote
            href, parts = self._link
            self.links.append((unquote(href), ''.join(parts)))
            self._link = None
        if tag == 'body':
            self.body = False

    def handle_data(self, text):
        if self.body:
            if self._link is not None:
                self._link[1].append(text)
            self.parts.append(text)
            self.length += utf16_length(text)

    def find(self, query, start=0):
        """Case-insensitive forward search with wrap and original-text offsets."""
        if not query or not query.strip():
            return None
        # casefold can expand characters. Preserve a map to original indices.
        origins = array('I')
        for index, char in enumerate(self.text):
            value = char.casefold()
            origins.extend([index] * len(value))
        haystack = self.text.casefold()
        units = 0
        first = len(self.text)
        for index, char in enumerate(self.text):
            if units >= start:
                first = index
                break
            units += utf16_length(char)
        begin = next((i for i, original in enumerate(origins) if original >= first), len(origins))
        needle = query.casefold()
        found = haystack.find(needle, begin)
        if found < 0:
            found = haystack.find(needle)
        if found < 0:
            return None
        left, right = origins[found], origins[found + len(needle) - 1] + 1
        return utf16_length(self.text[:left]), utf16_length(self.text[:right])


def book_boundaries(book):
    """Approximate chapter weights from resource sizes without loading the book."""
    sizes = getattr(book, 'resource_sizes', {})
    weights = [max(1, sizes.get(path, 1)) for path in book.spine]
    total = sum(weights) or 1
    boundaries = [0]
    for weight in weights:
        boundaries.append(boundaries[-1] + weight / total)
    boundaries[-1] = 1
    return boundaries


def book_location(boundaries, fraction):
    from bisect import bisect_right
    fraction = min(1, max(0, fraction))
    index = min(len(boundaries) - 2, bisect_right(boundaries, fraction) - 1)
    start, end = boundaries[index:index + 2]
    return index, (fraction - start) / (end - start)


class LayoutPages:
    """Session-only screen-page counts for one exact reading layout."""
    def __init__(self, chapters):
        self.counts = [None] * chapters
        self.layout = None

    def reset(self, layout):
        if layout != self.layout:
            self.layout = layout
            self.counts[:] = [None] * len(self.counts)
            return True
        return False

    def record(self, chapter, count):
        if type(count) is not int or not 1 <= count <= 10_000_000:
            raise ValueError('Invalid rendered page count')
        self.counts[chapter] = count

    @property
    def complete(self):
        return bool(self.counts) and all(count is not None for count in self.counts)

    @property
    def boundaries(self):
        if not self.complete:
            return None
        total = sum(self.counts)
        result, offset = [0], 0
        for count in self.counts:
            offset += count
            result.append(offset / total)
        return result

    def position(self, chapter, page, span=1):
        count = self.counts[chapter] or 1
        page = max(0, min(count - 1, page))
        first, last = page + 1, min(count, page + max(1, span))
        chapter_text = f'Chapter {chapter + 1} of {len(self.counts)}'
        if not self.complete:
            return dict(fraction=None, text=f'Counting pages… · {chapter_text}',
                        mobile=f'Counting pages…\n{chapter_text}')
        before, total = sum(self.counts[:chapter]), sum(self.counts)
        first, last = before + first, before + last
        pages = str(first) if first == last else f'{first}–{last}'
        percent = 100 * last // total
        page_text = f'Page {pages} of {total}'
        return dict(fraction=last / total, text=f'{percent}% · {page_text} · {chapter_text}',
                    mobile=f'{percent}% · {page_text}\n{chapter_text}')

    def locate(self, fraction):
        """Map the whole-book track to an exact chapter/local screen page."""
        if not self.complete:
            raise ValueError('Page counting is incomplete')
        total = sum(self.counts)
        target = min(total - 1, max(0, int(max(0, min(1, fraction)) * total)))
        for chapter, count in enumerate(self.counts):
            if target < count:
                return chapter, target
            target -= count
