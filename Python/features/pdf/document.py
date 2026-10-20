"""Bounded, memory-only PDF input and platform page rasterization."""
from contextlib import contextmanager
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
    def __init__(self, data):
        if not data or len(data) > MAX_PDF:
            raise ValueError('PDF reading is limited to 32 MiB.')
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
        if not self.data:
            raise ValueError('PDF is closed.')
        backend = ApplePDF if sys.platform == 'ios' else AndroidPDF if sys.platform == 'android' or hasattr(sys, 'getandroidapilevel') else QtPDF
        with backend(self.data) as document:
            yield document

    def page(self, index):
        if not 0 <= index < self.count:
            raise ValueError('Page does not exist.')
        with self.open() as document:
            return document.render(index)

    def close(self):
        self.data = b''
