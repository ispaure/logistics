"""Bounded, seekable chapter metadata for desktop Matroska and MP4 playback.

Native players enumerate chapters through VLC. Qt has no chapter API, so read
Matroska ChapterAtoms and the MP4 chpl atom without staging the movie or spawning
an external decoder. Unsupported chapter-track formats return an empty list.
"""
from dataclasses import dataclass
from pathlib import PurePosixPath
import struct


@dataclass(frozen=True)
class Chapter:
    start_ms: int
    title: str


class MetadataReader:
    def __init__(self, stream, size, check):
        self.stream, self.size, self.check = stream, size, check
        self.bytes, self.operations = 0, 0

    def read(self, offset, count):
        self.check()
        self.bytes += count
        self.operations += 1
        if (offset < 0 or count < 0 or offset + count > self.size or
                self.bytes > 2 * 1024 * 1024 or self.operations > 8192):
            raise ValueError('Chapter metadata exceeds its bounds.')
        self.stream.seek(offset)
        data = self.stream.read(count)
        self.check()
        if len(data) != count:
            raise ValueError('Incomplete chapter metadata.')
        return data


def _vint(reader, offset, *, identifier=False):
    first = reader.read(offset, 1)[0]
    mask, width = 128, 1
    while mask and not first & mask:
        mask >>= 1
        width += 1
    if not mask or width > (4 if identifier else 8):
        raise ValueError('Invalid Matroska element.')
    value = first if identifier else first & (mask - 1)
    for byte in reader.read(offset + 1, width - 1):
        value = value * 256 + byte
    return value, width


def _elements(reader, start, end):
    while start < end:
        tag, width = _vint(reader, start, identifier=True)
        size, size_width = _vint(reader, start + width)
        body = start + width + size_width
        unknown = size == (1 << (7 * size_width)) - 1
        stop = end if unknown else body + size
        if stop > end or stop <= start:
            raise ValueError('Invalid Matroska element size.')
        yield tag, body, stop
        start = stop


def _uint(reader, start, end):
    if not 0 < end - start <= 8:
        raise ValueError('Invalid chapter number.')
    return int.from_bytes(reader.read(start, end - start), 'big')


def _atoms(reader, start, end):
    while start + 8 <= end:
        size, tag = struct.unpack('>I4s', reader.read(start, 8))
        width = 8
        if size == 1:
            size = int.from_bytes(reader.read(start + 8, 8), 'big')
            width = 16
        if size == 0:
            size = end - start
        if size < width or start + size > end:
            raise ValueError('Invalid MP4 atom.')
        yield tag, start + width, start + size
        start += size


def _mp4(reader, start, end, depth=0):
    if depth > 4:
        return []
    for tag, body, stop in _atoms(reader, start, end):
        if tag in (b'moov', b'udta'):
            found = _mp4(reader, body, stop, depth + 1)
            if found:
                return found
        elif tag == b'chpl':
            data = reader.read(body, stop - body)
            if len(data) < 5 or data[0] not in (0, 1):
                return []
            pos = 8 if data[0] == 1 else 4
            if len(data) <= pos:
                raise ValueError('Incomplete MP4 chapters.')
            count, pos = data[pos], pos + 1
            result = []
            for _ in range(count):
                if pos + 9 > len(data):
                    raise ValueError('Incomplete MP4 chapter.')
                ticks, length = struct.unpack_from('>QB', data, pos)
                pos += 9
                if pos + length > len(data):
                    raise ValueError('Incomplete chapter title.')
                result.append(Chapter(ticks // 10000, data[pos:pos + length].decode('utf-8', 'replace')))
                pos += length
            return result
    return []


def _chapter_atom(reader, start, end, depth=0):
    if depth > 8:
        raise ValueError('Chapters are nested too deeply.')
    offset, title, enabled, children = None, '', True, []
    for tag, body, stop in _elements(reader, start, end):
        if tag == 0x91:
            offset = _uint(reader, body, stop) // 1000000
        elif tag == 0x4598:
            enabled = bool(_uint(reader, body, stop))
        elif tag == 0x80:
            for item, text, text_end in _elements(reader, body, stop):
                if item == 0x85 and not title:
                    title = reader.read(text, text_end - text).decode('utf-8', 'replace')
        elif tag == 0xB6:
            children.extend(_chapter_atom(reader, body, stop, depth + 1))
    return ([Chapter(offset, title)] + children) if enabled and offset is not None else []


def _chapter_editions(reader, start, end):
    for tag, body, stop in _elements(reader, start, end):
        if tag != 0x45B9:
            continue
        result, ordered = [], False
        for item, entry, entry_end in _elements(reader, body, stop):
            if item == 0x45DD:
                ordered = bool(_uint(reader, entry, entry_end))
            elif item == 0xB6:
                result.extend(_chapter_atom(reader, entry, entry_end))
        if result and not ordered:
            return result
    return []


def _matroska(reader):
    for tag, body, end in _elements(reader, 0, reader.size):
        if tag != 0x18538067:
            continue
        for item, start, stop in _elements(reader, body, end):
            if item == 0x1043A770:
                return _chapter_editions(reader, start, stop)
            if item == 0x1F43B675:
                # Without a SeekHead, scanning every cluster can turn a tiny
                # cloud metadata lookup into thousands of provider range reads.
                return []
            if item == 0x114D9B74:
                for seek, entry, entry_end in _elements(reader, start, stop):
                    if seek != 0x4DBB:
                        continue
                    target, position = None, None
                    for key, value, value_end in _elements(reader, entry, entry_end):
                        if key == 0x53AB:
                            target = _uint(reader, value, value_end)
                        elif key == 0x53AC:
                            position = _uint(reader, value, value_end)
                    if target == 0x1043A770 and position is not None:
                        found, chapter_start, chapter_end = next(_elements(reader, body + position, end))
                        if found != target:
                            raise ValueError('Invalid chapter index.')
                        return _chapter_editions(reader, chapter_start, chapter_end)
        return []
    return []


def read_chapters(content, *, cancelled=lambda: False):
    suffix = PurePosixPath(content.path).suffix.lower()
    if suffix not in ('.mkv', '.webm', '.mp4', '.m4v', '.mov'):
        return []
    def check():
        if cancelled():
            raise OSError('Chapter lookup cancelled.')
        content.check_access()
    with content.open() as stream:
        reader = MetadataReader(stream, content.size, check)
        result = _matroska(reader) if suffix in ('.mkv', '.webm') else _mp4(reader, 0, content.size)
    result = sorted({chapter.start_ms: chapter for chapter in result}.values(), key=lambda chapter: chapter.start_ms)
    return [Chapter(chapter.start_ms, chapter.title.strip() or f'Chapter {index + 1}')
            for index, chapter in enumerate(result)]
