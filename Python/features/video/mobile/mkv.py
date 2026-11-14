"""Session-scoped HLS access to the iOS Matroska stream-copy adapter."""
from base64 import b64decode
from bisect import bisect_left, bisect_right
from html import escape, unescape
import json
from math import ceil
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from re import fullmatch
from secrets import token_urlsafe
from threading import BoundedSemaphore, Event, Lock, Thread

from features.video.subtitles import MAX_SUBTITLE, Subtitles
from features.video.transport import VideoHTTPServer, byte_range


PLAYLIST_MIME = 'application/vnd.apple.mpegurl'
MEDIA_RESOURCE = r'(video|audio-[0-9]{1,10})/(init\.mp4|segment-([0-9]{1,6})\.m4s)'
SUBTITLE_RESOURCE = r'(text-[0-9]{1,10}|sidecar-[0-9]{1,3})/segment-([0-9]{1,6})\.vtt'


def playlist(boundaries, extension, *, initialization=False):
    spans = [end - start for start, end in zip(boundaries, boundaries[1:])]
    lines = ['#EXTM3U', '#EXT-X-VERSION:7', f'#EXT-X-TARGETDURATION:{ceil(max(spans) / 1000)}',
             '#EXT-X-MEDIA-SEQUENCE:0', '#EXT-X-PLAYLIST-TYPE:VOD']
    if initialization:
        lines.append('#EXT-X-MAP:URI="init.mp4"')
    for index, milliseconds in enumerate(spans):
        lines.extend((f'#EXTINF:{milliseconds / 1000:.3f},', f'segment-{index}.{extension}'))
    return ('\n'.join([*lines, '#EXT-X-ENDLIST']) + '\n').encode('ascii')


def rendition_name(track, number):
    name = track['name'] or track['language']
    if name == 'und':
        name = 'Track'
    name = ''.join(c for c in name[:96] if c.isprintable() and c not in '"\\')
    return f'{name or "Track"} ({number})'


def codec_string(track):
    """RFC 6381 identifiers for the formats produced by the native remuxer."""
    codec = track['codec']
    if codec in {'ac3', 'eac3', 'opus'}:
        return {'ac3': 'ac-3', 'eac3': 'ec-3', 'opus': 'mp4a.40.2'}[codec]
    config = b64decode(track.get('configuration', ''), validate=True)
    if codec == 'h264' and len(config) >= 4 and config[0] == 1:
        return 'avc1.' + config[1:4].hex().upper()
    if codec == 'hevc' and len(config) >= 13 and config[0] == 1:
        space = ('', 'A', 'B', 'C')[config[1] >> 6]
        profile = config[1] & 31
        compatibility = int(f'{int.from_bytes(config[2:6]):032b}'[::-1], 2)
        tier = 'H' if config[1] & 32 else 'L'
        constraints = ''.join(f'.{byte:02X}' for byte in config[6:12].rstrip(b'\0'))
        return f'hvc1.{space}{profile}.{compatibility:X}.{tier}{config[12]}{constraints}'
    if codec == 'aac' and len(config) >= 2:
        object_type = config[0] >> 3
        if object_type == 31:
            object_type = 32 + ((config[0] & 7) << 3) + (config[1] >> 5)
        if object_type:
            return f'mp4a.40.{object_type}'
    raise ValueError('The MKV codec configuration could not be prepared for AirPlay.')


def rendition_language(track):
    language = track['language']
    return language if fullmatch(r'[a-zA-Z]{2,8}(-[a-zA-Z0-9]{1,8})*', language) else 'und'


def rendition_characteristics(track, subtitles):
    if subtitles and track.get('hearingImpaired'):
        return 'public.accessibility.transcribes-spoken-dialog,public.accessibility.describes-music-and-sound'
    if not subtitles and track.get('visualImpaired'):
        return 'public.accessibility.describes-video'
    return ''


def master_playlist(audio, subtitles, default_audio, bandwidth, video):
    lines = ['#EXTM3U', '#EXT-X-VERSION:7']
    for kind, group, renditions in (('AUDIO', 'audio', audio), ('SUBTITLES', 'text', subtitles)):
        def selection_key(track):
            return (rendition_language(track).lower(), bool(track.get('forced')) if kind == 'SUBTITLES' else False,
                    rendition_characteristics(track, kind == 'SUBTITLES'))

        # Alternatives with the same language and role stay explicitly selectable
        # without letting automatic language matching pick a commentary at random.
        automatic = {selection_key(track) for track in renditions.values()
                     if kind == 'AUDIO' and track['id'] == default_audio}
        for number, (route, track) in enumerate(renditions.items(), 1):
            default = kind == 'AUDIO' and track['id'] == default_audio
            key = selection_key(track)
            autoselect = default or key[1] or bool(key[2]) or (key not in automatic and not track.get('commentary') and
                                     (key[0] != 'und' or key[1] or key[2]))
            if autoselect:
                automatic.add(key)
            flags = f'DEFAULT={"YES" if default else "NO"},AUTOSELECT={"YES" if autoselect else "NO"}'
            if kind == 'SUBTITLES':
                flags += f',FORCED={"YES" if track.get("forced") else "NO"}'
            flags += f',LANGUAGE="{rendition_language(track)}"'
            if key[2]:
                flags += f',CHARACTERISTICS="{key[2]}"'
            if kind == 'AUDIO' and track['channels'] > 0:
                flags += f',CHANNELS="{track["channels"]}"'
            lines.append(f'#EXT-X-MEDIA:TYPE={kind},GROUP-ID="{group}",NAME="{rendition_name(track, number)}",'
                         f'{flags},URI="{route}/index.m3u8"')
    codecs = list(dict.fromkeys([codec_string(video), *(codec_string(track) for track in audio.values())]))
    width, height = video['width'], video['height']
    if width <= 0 or height <= 0:
        raise ValueError('The MKV video dimensions could not be prepared for AirPlay.')
    attributes = f'BANDWIDTH={bandwidth},CODECS="{",".join(codecs)}",RESOLUTION={width}x{height},AUDIO="audio"'
    if video.get('range') in {'PQ', 'HLG'}:
        attributes += f',VIDEO-RANGE={video["range"]}'
    if subtitles:
        attributes += ',SUBTITLES="text"'
    lines.extend((f'#EXT-X-STREAM-INF:{attributes}', 'video/index.m3u8'))
    return ('\n'.join(lines) + '\n').encode('utf-8')


def webvtt_segment(cues, start, end):
    def time(milliseconds):
        seconds, millis = divmod(max(0, milliseconds), 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f'{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}'

    lines = ['WEBVTT', 'X-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:0', '']
    for first, last, cue in cues:
        if first >= end or last <= start:
            continue
        clean = escape(unescape(cue), quote=False).replace('\r', '')
        clean = '\n'.join(line for line in clean.splitlines() if line.strip())
        if clean:
            lines.extend((f'{time(first)} --> {time(last)}', clean, ''))
    return ('\n'.join(lines) + '\n').encode('utf-8')


class MKVStream:
    def __init__(self, owner, path, cancelled):
        from rubicon.objc import ObjCClass, py_from_ns
        from rubicon.objc.runtime import autoreleasepool
        self.owner = owner
        self.cancelled = cancelled
        self.stopped = Event()
        self.lock = Lock()
        self.slots = BoundedSemaphore(4)
        self.route = '/' + token_urlsafe(32) + '/'
        self.cached = {}
        self.headers = {}
        self.sidecars = {}
        with autoreleasepool():
            remux = ObjCClass('LGMKVRemux')
            address = remux.streamAddress()
            if address is None:
                raise ValueError('AirPlay for MKV requires Wi-Fi.')
            self.remux = remux.alloc().initWithPath(str(path))
            if self.remux is None or not self.allowed():
                raise ValueError('This MKV’s tracks or seek index could not be prepared for AirPlay.')
            metadata = json.loads(str(self.remux.renditionsJSON()))
            self.boundaries = metadata['boundaries']
            if len(self.boundaries) < 2 or any(start >= end for start, end in zip(self.boundaries, self.boundaries[1:])):
                raise ValueError('The MKV seek index could not be prepared for AirPlay.')
            self.audio = {f'audio-{track["id"]}': track for track in metadata['audio']}
            default_audio = metadata['defaultAudio']
            self.subtitles = {f'text-{track["id"]}': track for track in metadata['text']}
            for route in ('video', f'audio-{default_audio}'):
                header = self.remux.initializationForTrack(-1 if route == 'video' else default_audio)
                if header is None:
                    raise ValueError('The opening MKV segment could not be prepared for AirPlay.')
                self.headers[route] = py_from_ns(header)
        self.load_sidecars(tuple(owner.subtitles))
        # A single video variant. Use a generous estimate when the MKV has no
        # per-track peak bitrate metadata.
        average = owner.content.size * 8000 // max(1, self.boundaries[-1])
        self.playlist = master_playlist(self.audio, self.subtitles, default_audio,
                                        max(2_000_000, 3 * average), metadata['video'])
        self.media_playlist = playlist(self.boundaries, 'm4s', initialization=True)
        self.subtitle_playlist = playlist(self.boundaries, 'vtt')
        stream = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(6)

            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_media(body=True)

            def do_HEAD(self):
                self.send_media(body=False)

            def send_media(self, *, body):
                if not self.path.startswith(stream.route) or not stream.allowed():
                    self.send_error(404)
                    return
                if not stream.slots.acquire(blocking=False):
                    self.send_error(503)
                    return
                try:
                    data, mime = stream.resource(self.path[len(stream.route):])
                    if data is None or not stream.allowed():
                        self.send_error(404)
                        return
                    requested = self.headers.get('Range')
                    try:
                        first, last = byte_range(requested, len(data))
                    except (ValueError, OverflowError):
                        self.send_response(416)
                        self.send_header('Content-Range', f'bytes */{len(data)}')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    self.send_response(206 if requested else 200)
                    self.send_header('Content-Type', mime)
                    self.send_header('Content-Length', str(last - first + 1))
                    self.send_header('Accept-Ranges', 'bytes')
                    self.send_header('Cache-Control', 'no-store')
                    if requested:
                        self.send_header('Content-Range', f'bytes {first}-{last}/{len(data)}')
                    self.end_headers()
                    if body:
                        view = memoryview(data)
                        for offset in range(first, last + 1, 256 * 1024):
                            if not stream.allowed():
                                break
                            self.wfile.write(view[offset:min(last + 1, offset + 256 * 1024)])
                except (OSError, ValueError):
                    self.close_connection = True
                finally:
                    stream.slots.release()

        self.server = VideoHTTPServer((str(address), 0), Handler)
        self.server.daemon_threads = False
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
        try:
            self.thread.start()
        except BaseException:
            self.server.server_close()
            raise
        self.url = f'http://{address}:{self.server.server_port}{self.route}video.m3u8'

    def allowed(self):
        if self.stopped.is_set() or self.cancelled.is_set() or not self.owner.allowed(external=True):
            return False
        try:
            self.owner.content.check()
        except (OSError, ValueError):
            return False
        return True

    def load_sidecars(self, subtitles):
        remaining = 2 * MAX_SUBTITLE
        for subtitle in subtitles:
            if not self.allowed() or len(self.sidecars) >= 16:
                break
            path = Path(subtitle.path)
            if path.suffix.lower() not in {'.vtt', '.srt'} or subtitle.restricted or subtitle.size > MAX_SUBTITLE:
                continue
            if subtitle.size > remaining:
                continue
            try:
                subtitle.require_external()
                with subtitle.open() as source:
                    data = source.read(min(MAX_SUBTITLE, remaining) + 1)
                if len(data) > remaining:
                    continue
                remaining -= len(data)
                cues = Subtitles(data)
            except (OSError, ValueError):
                continue
            index = len(self.sidecars)
            route = f'sidecar-{index}'
            self.sidecars[route] = subtitle, cues
            self.subtitles[route] = dict(id=index, name=path.stem, language='und')

    def resource(self, name):
        if name == 'video.m3u8':
            return self.playlist, PLAYLIST_MIME
        if name.endswith('/index.m3u8'):
            route = name.removesuffix('/index.m3u8')
            if route == 'video' or route in self.audio:
                return self.media_playlist, PLAYLIST_MIME
            if route in self.subtitles:
                return self.subtitle_playlist, PLAYLIST_MIME
        media = fullmatch(MEDIA_RESOURCE, name)
        if media and (media[1] == 'video' or media[1] in self.audio):
            return self.media_resource(media[1], int(media[3]) if media[3] is not None else None)
        subtitle = fullmatch(SUBTITLE_RESOURCE, name)
        if subtitle and subtitle[1] in self.subtitles:
            return self.subtitle_resource(subtitle[1], int(subtitle[2]))
        return None, None

    def media_resource(self, route, index):
        from rubicon.objc import py_from_ns
        from rubicon.objc.runtime import autoreleasepool
        track = -1 if route == 'video' else self.audio[route]['id']
        with self.lock, autoreleasepool():
            if not self.allowed():
                return None, None
            if index is None:
                if route not in self.headers:
                    header = self.remux.initializationForTrack(track)
                    if header is None:
                        return None, None
                    self.headers[route] = py_from_ns(header)
                return self.headers[route], 'video/mp4' if track < 0 else 'audio/mp4'
            if not 0 <= index < len(self.boundaries) - 1:
                return None, None
            key = ('video' if track < 0 else 'audio', route, index)
            previous = self.cached.get(key[0])
            if previous is None or previous[0] != key:
                media = self.remux.fragment(index, track=track)
                if media is None or not self.allowed():
                    return None, None
                self.cached[key[0]] = previous = key, py_from_ns(media)
            return previous[1], 'video/iso.segment' if track < 0 else 'audio/mp4'

    def subtitle_resource(self, route, index):
        if not 0 <= index < len(self.boundaries) - 1:
            return None, None
        start, end = self.boundaries[index:index + 2]
        entry = self.sidecars.get(route)
        if entry is not None:
            subtitle, sidecar = entry
            try:
                subtitle.require_external()
                subtitle.check()
            except (OSError, ValueError):
                return None, None
            first = bisect_right(sidecar.starts, start - sidecar.max_duration)
            last = bisect_left(sidecar.starts, end)
            cues = [(cue.start, cue.end, cue.text) for cue in sidecar.cues[first:last]]
        else:
            from rubicon.objc.runtime import autoreleasepool
            with self.lock, autoreleasepool():
                if not self.allowed():
                    return None, None
                data = self.remux.textSegment(index, track=self.subtitles[route]['id'])
                if data is None:
                    return None, None
                cues = json.loads(str(data))
        return webvtt_segment(cues, start, end), 'text/vtt; charset=utf-8'

    def close(self):
        self.stopped.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.remux = None
        self.cached.clear()
        self.headers.clear()
        self.sidecars.clear()
