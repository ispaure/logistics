"""Video container admission, independent of providers and native decoders."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

VIDEO_EXTENSIONS = frozenset({'.mp4', '.mkv', '.avi', '.mov', '.m4v', '.webm', '.mpg', '.mpeg', '.ts', '.m2ts', '.wmv', '.ogv'})

AVI_HEADER_BYTES = 64 * 1024


def avi_uses_xvid(prefix):
    """Identify an XVID video stream using the bounded start of a RIFF AVI."""
    if len(prefix) < 12 or prefix[:4] != b'RIFF' or prefix[8:12] != b'AVI ':
        return False

    def chunks(start, end):
        while start + 8 <= min(end, len(prefix)):
            tag = prefix[start:start + 4]
            body = start + 8
            stop = body + int.from_bytes(prefix[start + 4:body], 'little')
            if stop > end:
                return
            yield tag, body, stop
            start = stop + (stop & 1)

    def lists(start, end, kind):
        for tag, body, stop in chunks(start, end):
            if tag == b'LIST' and body + 4 <= stop and prefix[body:body + 4] == kind:
                yield body + 4, stop

    riff_end = 8 + int.from_bytes(prefix[4:8], 'little')
    for header in lists(12, riff_end, b'hdrl'):
        for stream in lists(*header, b'strl'):
            fields = {tag: prefix[body:min(stop, body + 20)] for tag, body, stop in chunks(*stream)
                      if tag in (b'strh', b'strf')}
            if (fields.get(b'strh', b'')[:8].upper() == b'VIDSXVID'
                    and fields.get(b'strf', b'')[16:20].upper() == b'XVID'):
                return True
    return False
