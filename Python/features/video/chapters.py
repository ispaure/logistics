"""Bounded chapter and track timing metadata for Matroska and MP4 playback.

Native players enumerate chapters through VLC. Qt has no chapter API, so read
Matroska ChapterAtoms and the MP4 chpl atom without staging the movie or spawning
an external decoder. Unsupported chapter-track formats return an empty list.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from dataclasses import dataclass
from itertools import islice
from pathlib import PurePosixPath
import re
import struct


_MATROSKA_SUFFIXES = ('.mkv', '.webm', '.mka')
_MP4_SUFFIXES = ('.mp4', '.m4v', '.mov')
_SEGMENT, _SEEK_HEAD, _CLUSTER = 0x18538067, 0x114D9B74, 0x1F43B675
_INFO, _TRACKS, _CHAPTERS, _TAGS = 0x1549A966, 0x1654AE6B, 0x1043A770, 0x1254C367
_MAX_END_MS = (1 << 53) - 1  # Safe in native and JSON timeline representations.


@dataclass(frozen=True)
class Chapter:
    start_ms: int
    title: str


@dataclass(frozen=True)
class TrackBound:
    container_id: int | None
    end_ms: int | None


@dataclass(frozen=True)
class MediaBounds:
    """Declared ends by track type in container order."""

    video: tuple[TrackBound, ...] = ()
    audio: tuple[TrackBound, ...] = ()
    source: str | None = None

    @property
    def end_ms(self) -> int | None:
        ends = [track.end_ms for track in self.video + self.audio]
        return max(ends) if ends and None not in ends else None


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
            raise ValueError('Media metadata exceeds its bounds.')
        self.stream.seek(offset)
        data = self.stream.read(count)
        self.check()
        if len(data) != count:
            raise ValueError('Incomplete media metadata.')
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
    if width > 1:
        value = (value << (8 * (width - 1))) + int.from_bytes(reader.read(offset + 1, width - 1), 'big')
    return value, width


def _elements(reader, start, end, *, strict=False):
    while start < end:
        tag, width = _vint(reader, start, identifier=True)
        size, size_width = _vint(reader, start + width)
        body = start + width + size_width
        unknown = size == (1 << (7 * size_width)) - 1
        stop = end if unknown else body + size
        if stop > end or stop <= start or (strict and unknown and tag not in (_SEGMENT, _CLUSTER)):
            raise ValueError('Invalid Matroska element size.')
        yield tag, body, stop
        start = stop


def _uint(reader, start, end):
    if not 0 < end - start <= 8:
        raise ValueError('Invalid Matroska number.')
    return int.from_bytes(reader.read(start, end - start), 'big')


def _atoms(reader, start, end, *, strict=False):
    while start + 8 <= end:
        size, tag = struct.unpack('>I4s', reader.read(start, 8))
        width = 8
        if size == 1:
            if start + 16 > end:
                raise ValueError('Incomplete MP4 atom header.')
            size = int.from_bytes(reader.read(start + 8, 8), 'big')
            width = 16
        if size == 0:
            size = end - start
        if size < width or start + size > end:
            raise ValueError('Invalid MP4 atom.')
        yield tag, start + width, start + size
        start += size
    if strict and start != end:
        raise ValueError('Incomplete MP4 atom header.')


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
        if tag != _SEGMENT:
            continue
        for item, start, stop in _elements(reader, body, end):
            if item == _CHAPTERS:
                return _chapter_editions(reader, start, stop)
            if item == _CLUSTER:
                # Without a SeekHead, scanning every cluster can turn a tiny
                # cloud metadata lookup into thousands of provider range reads.
                return []
            if item == _SEEK_HEAD:
                for target, position in _seek_entries(reader, start, stop):
                    if target == _CHAPTERS:
                        chapter_start, chapter_end = _seek_element(reader, body + position, end, target)
                        return _chapter_editions(reader, chapter_start, chapter_end)
        return []
    return []


def _seek_entries(reader, start, end, *, strict=False):
    for tag, body, stop in _elements(reader, start, end, strict=strict):
        if tag != 0x4DBB:
            continue
        target, position = None, None
        for key, value, value_end in _elements(reader, body, stop, strict=strict):
            if key == 0x53AB:
                target = _uint(reader, value, value_end)
            elif key == 0x53AC:
                position = _uint(reader, value, value_end)
        if target is not None and position is not None:
            yield target, position


def _seek_element(reader, offset, end, target, *, strict=False):
    entry = next(_elements(reader, offset, end, strict=strict), None)
    if entry is None or entry[0] != target:
        raise ValueError('Invalid Matroska index.')
    return entry[1:]


def read_chapters(content, *, cancelled=lambda: False):
    suffix = PurePosixPath(content.path).suffix.lower()
    if suffix not in ('.mkv', '.webm') + _MP4_SUFFIXES:
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


def _milliseconds(units, scale):
    end = (units * 1000 + scale - 1) // scale
    return end if 0 < end <= _MAX_END_MS else None


def _mp4_fields(reader, span, *names):
    fields = {}
    for name, body, end in _atoms(reader, *span, strict=True):
        if name in names:
            if name in fields:
                raise ValueError('Duplicate MP4 timing metadata.')
            fields[name] = (body, end)
    return fields


def _mp4_timing(reader, span, kind):
    if span is None or span[0] == span[1]:
        return None, None
    body, end = span
    version = reader.read(body, 1)[0]
    suffix = {b'tkhd': 72, b'mvhd': 88, b'mdhd': 12}[kind]
    if version not in (0, 1) or end - body < suffix + 12 + version * 12:
        return None, None
    offset = body + 12 + version * 8
    fmt = ('>I4x' if kind == b'tkhd' else '>I') + ('Q' if version else 'I')
    identity, duration = struct.unpack(fmt, reader.read(offset, struct.calcsize(fmt)))
    maximum = (1 << (64 if version else 32)) - 1
    return identity or None, duration if 0 < duration < maximum else None


def _mp4_edit_end(reader, span, track_duration, movie_scale, media_scale, media_duration, *, video):
    body, end = span
    if end - body < 8:
        return None
    version, count = struct.unpack('>B3xI', reader.read(body, 8))
    fmt = {0: '>IiI', 1: '>QqI'}.get(version)
    if fmt is None or not 1 <= count <= 3:
        return None
    width = struct.calcsize(fmt)
    if end - body != 8 + count * width:
        return None
    elapsed, playable_end = 0, None
    for duration, media_time, rate in struct.iter_unpack(fmt, reader.read(body + 8, count * width)):
        elapsed += duration
        if duration == 0 or rate != 0x10000:
            return None
        if media_time == -1:
            continue
        # Video composition timestamps can be shifted relative to the decode
        # timeline described by mdhd. Validate the span, including one movie
        # tick of rounding. For audio, also account for media_time preroll.
        available = media_duration if video else media_duration - media_time
        if playable_end is not None or media_time < 0 or (duration - 1) * media_scale > available * movie_scale:
            return None
        playable_end = elapsed
    return playable_end if elapsed == track_duration else None


def _mp4_track_bound(reader, track, movie_scale):
    fields = _mp4_fields(reader, track, b'tkhd', b'mdia', b'edts')
    if b'mdia' not in fields:
        raise ValueError('Missing MP4 media metadata.')
    media = _mp4_fields(reader, fields[b'mdia'], b'hdlr', b'mdhd')
    if b'hdlr' not in media:
        raise ValueError('Missing MP4 media handler.')
    body, end = media[b'hdlr']
    if end - body < 24 or reader.read(body, 1) != b'\0':
        raise ValueError('Invalid MP4 media handler.')
    kind = reader.read(body + 8, 4)
    if kind not in (b'vide', b'soun'):
        return kind, None

    identity, duration = _mp4_timing(reader, fields.get(b'tkhd'), b'tkhd')
    scale, media_duration = _mp4_timing(reader, media.get(b'mdhd'), b'mdhd')
    end_ms = None
    if identity and duration and movie_scale and scale and media_duration:
        if b'edts' in fields:
            edits = _mp4_fields(reader, fields[b'edts'], b'elst').get(b'elst')
            duration = edits and _mp4_edit_end(reader, edits, duration, movie_scale, scale, media_duration,
                                               video=kind == b'vide')
        elif abs(duration * scale - media_duration * movie_scale) > scale:
            duration = None
        if duration is not None:
            end_ms = _milliseconds(duration, movie_scale)
    return kind, TrackBound(identity, end_ms)


def _mp4_media_bounds(reader):
    movie = None
    for tag, body, stop in _atoms(reader, 0, reader.size, strict=True):
        if tag == b'moof':
            return MediaBounds()
        if tag == b'moov':
            if movie is not None:
                return MediaBounds()
            movie = list(_atoms(reader, body, stop, strict=True))
            if any(tag == b'mvex' for tag, _, _ in movie):
                return MediaBounds()
    if movie is None:
        return MediaBounds()
    headers = [(body, end) for tag, body, end in movie if tag == b'mvhd']
    movie_scale, _ = _mp4_timing(reader, headers[0], b'mvhd') if len(headers) == 1 else (None, None)
    video, audio, identities = [], [], set()
    for tag, body, end in movie:
        if tag != b'trak':
            continue
        kind, track = _mp4_track_bound(reader, (body, end), movie_scale)
        if track is None:
            continue
        if track.container_id is not None:
            if track.container_id in identities:
                return MediaBounds()
            identities.add(track.container_id)
        (video if kind == b'vide' else audio).append(track)
    return MediaBounds(tuple(video), tuple(audio), 'mp4-track-header')


def _mkv_metadata_items(reader, segment):
    start, end = segment
    wanted = (_INFO, _TRACKS, _CHAPTERS, _TAGS)
    items = {tag: set() for tag in wanted}
    cluster = None
    for tag, body, stop in _elements(reader, start, end, strict=True):
        if tag == _CLUSTER:
            cluster = (body, stop)
            break
        if tag in wanted:
            items[tag].add((body, stop))
        elif tag == _SEEK_HEAD:
            for target, position in _seek_entries(reader, body, stop, strict=True):
                if target in wanted:
                    items[target].add(_seek_element(reader, start + position, end, target, strict=True))
    return items, cluster


def _mkv_fields(reader, span, *wanted):
    result = {}
    for tag, body, stop in _elements(reader, *span, strict=True):
        if tag in wanted:
            if tag in result:
                raise ValueError('Duplicate Matroska timing metadata.')
            result[tag] = (body, stop)
    return result


def _mkv_tracks(reader, spans):
    tracks, numbers, uids = [], set(), set()
    for span in sorted(spans):
        for tag, body, stop in _elements(reader, *span, strict=True):
            if tag != 0xAE:  # TrackEntry
                continue
            fields = _mkv_fields(reader, (body, stop), 0xD7, 0x73C5, 0x83, 0x23314F, 0x537F)
            if not all(key in fields for key in (0xD7, 0x73C5, 0x83)):
                raise ValueError('Incomplete Matroska track identity.')
            number, uid, kind = (_uint(reader, *fields[key]) for key in (0xD7, 0x73C5, 0x83))
            if not (0 < number < 1 << 56 and uid) or number in numbers or uid in uids:
                raise ValueError('Invalid Matroska track identity.')
            if kind not in (1, 2, 0x10, 0x11, 0x12, 0x20, 0x21):
                raise ValueError('Ambiguous Matroska track type.')
            numbers.add(number)
            uids.add(uid)
            if kind in (1, 2):  # Video, audio
                simple_timing = not any(key in fields for key in (0x23314F, 0x537F))
                tracks.append((number, uid, kind, simple_timing))
    return tracks


def _mkv_string(reader, span, limit=256):
    if span is None:
        return None
    start, end = span
    return reader.read(start, end - start).rstrip(b'\0') if 0 < end - start <= limit else None


def _mkv_track_tags(reader, spans, track_uids):
    values = {}
    for span in sorted(spans):
        for tag, body, stop in _elements(reader, *span, strict=True):
            if tag != 0x7373:  # Tag
                continue
            children = list(_elements(reader, body, stop, strict=True))
            targets = [(start, end) for key, start, end in children if key == 0x63C0]
            if len(targets) != 1:
                continue
            target_keys = _mkv_fields(reader, targets[0], 0x63C5, 0x63C9, 0x63C4, 0x63C6)
            if target_keys.keys() != {0x63C5}:  # A single track, without an edition/chapter/attachment target
                continue
            uid = _uint(reader, *target_keys[0x63C5])
            if uid not in track_uids:
                continue
            for key, start, end in children:
                if key != 0x67C8:  # SimpleTag
                    continue
                fields = _mkv_fields(reader, (start, end), 0x45A3, 0x4487)
                name = _mkv_string(reader, fields.get(0x45A3), limit=32)
                if name in (b'DURATION', b'_STATISTICS_WRITING_APP'):
                    value = _mkv_string(reader, fields.get(0x4487))
                    identity = (uid, name)
                    if values.get(identity, value) != value:
                        value = None  # Conflicting tag declarations.
                    values[identity] = value
    return values


def _mkv_first_block_times(reader, cluster, numbers):
    if cluster is None or not numbers:
        return {}
    timestamp, relative = None, {}
    for tag, body, stop in islice(_elements(reader, *cluster, strict=True), 128):
        if tag == 0xE7:  # Timestamp, in segment ticks
            timestamp = _uint(reader, body, stop)
        if tag in (0xA0, 0xA3):  # BlockGroup, SimpleBlock
            if tag == 0xA0:
                block = _mkv_fields(reader, (body, stop), 0xA1).get(0xA1)
                if block is None:
                    continue
                body, stop = block
            if stop - body < 4:
                raise ValueError('Incomplete Matroska block header.')
            number, width = _vint(reader, body)
            if body + width + 3 > stop:
                raise ValueError('Incomplete Matroska block timestamp.')
            if number in numbers and number not in relative:
                relative[number] = struct.unpack('>h', reader.read(body + width, 2))[0]
        if timestamp is not None and numbers == relative.keys():
            break
    # The first block seen for a track can be later than its earliest PTS
    # when frames are reordered. Using it rounds the declared end upwards.
    return {number: max(0, timestamp + offset) for number, offset in relative.items()} if timestamp is not None else {}


_MKV_DURATION = re.compile(rb'([0-9]{2,12}):([0-5][0-9]):([0-5][0-9])(?:\.([0-9]{1,9}))?')


def _mkv_duration_ns(value):
    match = _MKV_DURATION.fullmatch(value or b'')
    if match is None:
        return None
    hours, minutes, seconds = map(int, match.groups()[:3])
    fraction = (match[4] or b'').ljust(9, b'0')
    return ((hours * 60 + minutes) * 60 + seconds) * 1_000_000_000 + int(fraction)


def _mkv_statistics_writer(value):
    return bool(value and value.split(b' ', 1)[0] in (b'mkvmerge', b'mkvpropedit'))


def _mkv_ordered_editions(reader, spans):
    for span in spans:
        for tag, body, stop in _elements(reader, *span, strict=True):
            if tag == 0x45B9:
                flags = _mkv_fields(reader, (body, stop), 0x45DD)
                if 0x45DD in flags and _uint(reader, *flags[0x45DD]):
                    return True
    return False


def _mkv_media_bounds(reader):
    segments = [(body, stop) for tag, body, stop in _elements(reader, 0, reader.size, strict=True) if tag == _SEGMENT]
    if len(segments) != 1:
        return MediaBounds()
    items, cluster = _mkv_metadata_items(reader, segments[0])
    if len(items[_INFO]) != 1 or _mkv_ordered_editions(reader, items[_CHAPTERS]):
        return MediaBounds()
    info = _mkv_fields(reader, next(iter(items[_INFO])), 0x4D80, 0x5741, 0x2AD7B1, 0x3CB923, 0x3EB923)
    if 0x3CB923 in info or 0x3EB923 in info:  # A linked segment can have a different playback timeline.
        return MediaBounds()
    scale = _uint(reader, *info[0x2AD7B1]) if 0x2AD7B1 in info else 1_000_000
    muxer = _mkv_string(reader, info.get(0x4D80))
    ffmpeg = re.fullmatch(rb'Lavf(?:[0-9]+\.[0-9]+\.[0-9]+)?', muxer or b'') is not None
    mkvtoolnix = _mkv_statistics_writer(_mkv_string(reader, info.get(0x5741)))
    tracks = _mkv_tracks(reader, items[_TRACKS])
    tags = _mkv_track_tags(reader, items[_TAGS], {uid for _, uid, _, _ in tracks})
    # FFmpeg writes a segment-relative end. MKVToolNix writes the span from
    # first to last presentation timestamp, including for delayed tracks.
    durations, spans = {}, set()
    for number, uid, _, simple_timing in tracks:
        length = _mkv_duration_ns(tags.get((uid, b'DURATION')))
        if not simple_timing or not length:
            continue
        if mkvtoolnix or _mkv_statistics_writer(tags.get((uid, b'_STATISTICS_WRITING_APP'))):
            spans.add(number)
            durations[number] = length
        elif ffmpeg:
            durations[number] = length
    starts = _mkv_first_block_times(reader, cluster, spans) if scale else {}

    video, audio = [], []
    for number, _, kind, _ in tracks:
        duration = durations.get(number)
        end_ms = None
        if duration is not None and (number not in spans or number in starts):
            end_ms = _milliseconds(duration + starts.get(number, 0) * scale, 1_000_000_000)
        bound = TrackBound(number if number <= _MAX_END_MS else None, end_ms)
        (video if kind == 1 else audio).append(bound)
    return MediaBounds(tuple(video), tuple(audio), 'matroska-duration-tag')


def read_media_bounds(content, *, cancelled=lambda: False):
    """Read optional declared bounds through the current retained source.

    Unknown or unsupported metadata leaves playback to the backend. Access and
    cancellation errors propagate so the caller can retire a stale lookup.
    """
    suffix = PurePosixPath(content.path).suffix.lower()
    if suffix not in _MATROSKA_SUFFIXES + _MP4_SUFFIXES:
        return MediaBounds()

    def check():
        if cancelled():
            raise OSError('Media timing lookup cancelled.')
        content.check_access()

    check()
    with content.open() as stream:
        reader = MetadataReader(stream, content.size, check)
        try:
            bounds = _mkv_media_bounds(reader) if suffix in _MATROSKA_SUFFIXES else _mp4_media_bounds(reader)
        except ValueError:
            bounds = MediaBounds()
    check()
    return bounds
