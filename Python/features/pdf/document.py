"""Bounded PDF input and platform page rasterization."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from contextlib import contextmanager
from pathlib import Path
import sys

MAX_PDF = 32 * 1024 * 1024
MAX_PAGES = 10000
from .limits import PAGE_EDGE
from .backends.qt import QtPDF
from .backends.apple import ApplePDF
from .backends.android import AndroidPDF


def page_index(value, count):
    """Convert the displayed, one-based page number without silently wrapping."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError('Enter a whole page number.') from None
    if not 1 <= number <= count:
        raise ValueError(f'Enter a page number from 1 to {count}.')
    return number - 1


def read_pdf(stream):
    """Read in bounded ranges, including providers with a per-read ceiling."""
    data = bytearray()
    while len(data) <= MAX_PDF:
        part = stream.read(min(1024 * 1024, MAX_PDF + 1 - len(data)))
        if not part:
            break
        data.extend(part)
    if len(data) > MAX_PDF:
        raise ValueError('PDF reading is limited to 32 MiB.')
    return bytes(data)


class PDFDocument:
    def __init__(self, data, *, max_bytes=MAX_PDF):
        self.check_size(data, max_bytes)
        self.data = data
        with self.open() as document:
            self.count = document.count
        if not 1 <= self.count <= MAX_PAGES:
            self.data = b''
            raise ValueError('PDF must contain between 1 and 10,000 pages.')

    @classmethod
    def from_source(cls, name, source):
        with source.open(name) as stream:
            return cls(read_pdf(stream))

    @contextmanager
    def open(self):
        data = self.data
        if not data:
            raise ValueError('PDF is closed.')
        with self.backend(data) as document:
            yield document

    @staticmethod
    def check_size(data, max_bytes):
        size = data.stat().st_size if isinstance(data, Path) else len(data)
        if not 0 < size <= max_bytes:
            raise ValueError(f'PDF reading is limited to {max_bytes // (1024 * 1024)} MiB.')

    @staticmethod
    def backend(data):
        if sys.platform == 'ios':
            return ApplePDF(data)
        if sys.platform == 'android' or hasattr(sys, 'getandroidapilevel'):
            return AndroidPDF(data)
        return QtPDF(data)

    @classmethod
    def render_page(cls, data, index, *, max_bytes=MAX_PDF, edge=PAGE_EDGE):
        """Open one native renderer for a self-contained page request."""
        cls.check_size(data, max_bytes)
        with cls.backend(data) as document:
            if not 1 <= document.count <= MAX_PAGES:
                raise ValueError('PDF must contain between 1 and 10,000 pages.')
            if not 0 <= index < document.count:
                raise ValueError('Page does not exist.')
            return document.render(index, edge=edge)

    @staticmethod
    def can_select_text():
        return (not (sys.platform == 'android' or hasattr(sys, 'getandroidapilevel'))
                or AndroidPDF.text_renderer() is not None)

    @classmethod
    def select_text(cls, data, index, start, end, *, max_bytes=MAX_PDF):
        """Select a text range in normalized top-left page coordinates."""
        from math import isfinite

        cls.check_size(data, max_bytes)
        renderer = (AndroidPDF(data, text=True) if sys.platform == 'android' or hasattr(sys, 'getandroidapilevel')
                    else cls.backend(data))
        with renderer as document:
            if not 0 <= index < document.count <= MAX_PAGES:
                raise ValueError('Page does not exist.')
            text, rectangles = document.select_text(index, start, end)
        clipped = []
        for x, y, w, h in rectangles:
            if not all(isfinite(v) for v in (x, y, w, h)):
                continue
            left, top, right, bottom = max(0, x), max(0, y), min(1, x + w), min(1, y + h)
            if left < right and top < bottom:
                clipped.append((left, top, right - left, bottom - top))
        return text, clipped

    def page(self, index):
        if not 0 <= index < self.count:
            raise ValueError('Page does not exist.')
        with self.open() as document:
            return document.render(index)

    def close(self):
        self.data = b''
