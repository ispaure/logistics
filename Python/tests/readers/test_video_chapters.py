"""Chapter offsets, metadata bounds and sparse movie reads."""
from commonUtils.testing.stages import TestStage, stage

TEST_STAGE = TestStage.REGRESSION
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from features.video.chapters import Chapter, MediaBounds, TrackBound, read_chapters, read_media_bounds


def element(tag, data):
    identifier = tag.to_bytes((tag.bit_length() + 7) // 8, 'big')
    width = next(n for n in range(1, 9) if len(data) < (1 << (7*n))-1)
    return identifier + ((1 << (7*width)) | len(data)).to_bytes(width, 'big') + data


def atom(tag, data):
    return struct.pack('>I4s', len(data)+8, tag) + data


class MetadataTestCase(unittest.TestCase):
    def content(self, path, data):
        self.read_bytes = 0
        self.open_count = 0
        self.stream = None
        owner = self
        class Stream(BytesIO):
            def read(self, count=-1):
                owner.read_bytes += count
                return super().read(count)
        @contextmanager
        def opened():
            self.open_count += 1
            with Stream(data) as stream:
                self.stream = stream
                yield stream
        return SimpleNamespace(path=path, size=len(data), open=opened, check_access=Mock())


class ChapterTests(MetadataTestCase):
    def test_mp4_skips_media_and_retains_named_offsets(self):
        entries = b'\x01\0\0\0\0\0\0\0\x02'
        for offset, title in ((0, b'Opening'), (90500, b'The next scene')):
            entries += struct.pack('>QB', offset*10000, len(title)) + title
        data = atom(b'ftyp', b'isom0000') + atom(b'mdat', b'x'*1000000) + atom(b'moov', atom(b'udta', atom(b'chpl', entries)))
        result = read_chapters(self.content('film.mp4', data))
        self.assertEqual(result, [Chapter(0, 'Opening'), Chapter(90500, 'The next scene')])
        self.assertLess(self.read_bytes, 300)

    def test_matroska_chapters_after_cluster_with_nested_atoms(self):
        def chapter(time, title, children=b''):
            return element(0xB6, element(0x91, (time*1000000).to_bytes(8,'big')) + element(0x80,element(0x85,title)) + children)
        chapters = element(0x1043A770, element(0x45B9, chapter(0,b'Opening',chapter(60000,b'First act')) + chapter(180000,b'')))
        cluster = element(0x1F43B675,b'x'*1000000)
        def seek_head(position):
            return element(0x114D9B74,element(0x4DBB,element(0x53AB,bytes.fromhex('1043a770')) +
                element(0x53AC,position.to_bytes(8,'big'))))
        head = seek_head(len(seek_head(0)) + len(cluster))
        data = element(0x1A45DFA3,b'') + element(0x18538067, head + cluster + chapters)
        result = read_chapters(self.content('film.mkv', data))
        self.assertEqual(result, [Chapter(0,'Opening'),Chapter(60000,'First act'),Chapter(180000,'Chapter 3')])
        self.assertLess(self.read_bytes, 300)

    @stage(TestStage.EXTENDED)
    def test_real_ffmpeg_chapters_in_mp4_and_matroska(self):
        from shutil import which
        if not which('ffmpeg'):
            self.skipTest('FFmpeg fixture encoder unavailable')
        from logistics_build.build_retention import scratch
        from tests.readers.video_fixtures import chapter_movie
        from commonUtils.runtime.resources.local import LocalFiles
        from features.video.playback import VideoContent
        with scratch() as root:
            for container in ('mkv', 'mp4'):
                path = chapter_movie(root, container, regenerate=True)
                content = VideoContent(LocalFiles(root), path.name)
                try:
                    self.assertEqual(read_chapters(content), [Chapter(0, 'Opening'), Chapter(6000, 'Second scene')])
                finally:
                    content.close()

    def test_truncated_or_oversize_metadata_is_rejected(self):
        for data in (b'\0\0\0\x20moov', atom(b'moov', atom(b'udta', atom(b'chpl',b'\x01'*2200000)))):
            with self.assertRaises(ValueError):
                read_chapters(self.content('film.mp4',data))

    def test_unindexed_clusters_are_not_scanned_for_cloud_metadata(self):
        data = element(0x18538067,element(0x1F43B675,b'x'*1000000))
        self.assertEqual(read_chapters(self.content('film.mkv',data)),[])
        self.assertLess(self.read_bytes,32)

    def test_access_and_cancellation_guard_metadata(self):
        content=self.content('film.mkv',element(0x18538067,b''))
        with self.assertRaises(OSError):
            read_chapters(content,cancelled=lambda:True)
        content.check_access.side_effect=PermissionError('locked')
        with self.assertRaises(PermissionError):
            read_chapters(content)


def mp4_timing(tag, scale_or_id, duration, version):
    prefix = bytes([version]) + bytes(11 + 8 * version)
    identity = struct.pack('>I', scale_or_id)
    if tag == b'tkhd':
        identity += bytes(4)
    timing = duration.to_bytes(8 if version else 4, 'big')
    padding = {b'mvhd': 80, b'mdhd': 4, b'tkhd': 60}[tag]
    return atom(tag, prefix + identity + timing + bytes(padding))


def mp4_track(kind, number, length, *, media_scale, media_duration, edits=(), version=0):
    handler = atom(b'hdlr', bytes(8) + kind + bytes(12))
    media = atom(b'mdia', mp4_timing(b'mdhd', media_scale, media_duration, version) + handler)
    edit_list = b''
    if edits:
        fmt = '>QqI' if version else '>IiI'
        data = struct.pack('>B3xI', version, len(edits))
        edit_list = atom(b'edts', atom(b'elst', data + b''.join(struct.pack(fmt, *row) for row in edits)))
    return atom(b'trak', mp4_timing(b'tkhd', number, length, version) + media + edit_list)


def mkv_uint(tag, number, width=None):
    return element(tag, number.to_bytes(width or max(1, (number.bit_length() + 7) // 8), 'big'))


def mkv_track(number, uid, kind):
    return element(0xAE, mkv_uint(0xD7, number) + mkv_uint(0x73C5, uid) + mkv_uint(0x83, kind))


def mkv_tag(uid, duration, writer=None):
    def text_tag(name, value):
        return element(0x67C8, element(0x45A3, name) + element(0x4487, value))
    targets = element(0x63C0, mkv_uint(0x63C5, uid) if uid is not None else b'')
    values = text_tag(b'DURATION', duration)
    if writer:
        values += text_tag(b'_STATISTICS_WRITING_APP', writer)
    return element(0x7373, targets + values)


def mkv_prefix(tracks, *, muxer=b'Lavf61.7.100', writer=b'', scale=1_000_000):
    info = element(0x4D80, muxer) + element(0x5741, writer) + mkv_uint(0x2AD7B1, scale)
    info += element(0x4489, struct.pack('>d', 100000.0))  # Segment duration is intentionally unrelated.
    return element(0x1549A966, info) + element(0x1654AE6B, b''.join(tracks))


def mkv_indexed_tags(prefix, cluster, tags):
    def seek_head(position):
        seek = mkv_uint(0x53AB, 0x1254C367) + mkv_uint(0x53AC, position, width=8)
        return element(0x114D9B74, element(0x4DBB, seek))
    position = len(seek_head(0)) + len(prefix) + len(cluster)
    return element(0x18538067, seek_head(position) + prefix + cluster + element(0x1254C367, tags))


class MediaBoundsTests(MetadataTestCase):
    def test_mp4_uses_longest_audio_or_video_and_ignores_subtitle_duration(self):
        movie = mp4_timing(b'mvhd', 1000, 22000, 0)
        text = mp4_track(b'text', 1, 22000, media_scale=1000, media_duration=22000)
        for video_end, audio_end in ((8217, 12000), (12000, 8217)):
            with self.subTest(video_end=video_end):
                video = mp4_track(b'vide', 7, video_end, media_scale=90000, media_duration=video_end * 90)
                audio = mp4_track(b'soun', 3, audio_end, media_scale=48000, media_duration=audio_end * 48)
                alt = mp4_track(b'soun', 2, 4567, media_scale=44100, media_duration=201405)
                data = atom(b'mdat', b'x' * 3_000_000) + atom(b'moov', movie + audio + video + text + alt)
                bounds = read_media_bounds(self.content('film.mp4', data))
                self.assertEqual(bounds.video, (TrackBound(7, video_end),))
                self.assertEqual(bounds.audio, (TrackBound(3, audio_end), TrackBound(2, 4567)))
                self.assertEqual(bounds.end_ms, 12000)
                self.assertEqual(bounds.source, 'mp4-track-header')
                self.assertLess(self.read_bytes, 500)
                self.assertEqual(self.open_count, 1)
                self.assertTrue(self.stream.closed)

    def test_mp4_uses_movie_scale_and_trims_trailing_empty_edit(self):
        movie = mp4_timing(b'mvhd', 24000, 120000, 1)
        edit = ((1001, -1, 65536), (48000, 1024, 65536), (4000, -1, 65536))
        audio = mp4_track(b'soun', 14, 53001, media_scale=48000, media_duration=97024, edits=edit, version=1)
        bounds = read_media_bounds(self.content('film.mov', atom(b'moov', movie + audio)))
        self.assertEqual(bounds.audio, (TrackBound(14, 2042),))
        self.assertEqual(bounds.end_ms, 2042)

    def test_mp4_accepts_shifted_video_composition_timestamps(self):
        path = Path(__file__).with_name('fixtures') / 'video' / 'hevc-aac.mp4'
        content = self.content(path.name, path.read_bytes())
        bounds = read_media_bounds(content)
        self.assertEqual(bounds.video, (TrackBound(1, 2000),))
        self.assertEqual(bounds.audio, (TrackBound(2, 2000),))

    def test_unknown_mp4_track_prevents_cap_and_fragments_are_unknown(self):
        movie = mp4_timing(b'mvhd', 1000, 5000, 0)
        video = mp4_track(b'vide', 7, 4000, media_scale=90000, media_duration=360000)
        for duration, edits in ((0xffffffff, ()), (5000, ((5000, 0, 32768),)), (6000, ((6000, 0, 65536),))):
            with self.subTest(duration=duration, edits=edits):
                audio = mp4_track(b'soun', 8, duration, media_scale=48000, media_duration=240000, edits=edits)
                bounds = read_media_bounds(self.content('film.mp4', atom(b'moov', movie + video + audio)))
                self.assertEqual(bounds.video, (TrackBound(7, 4000),))
                self.assertEqual(bounds.audio, (TrackBound(8, None),))
                self.assertIsNone(bounds.end_ms)
        for data in (atom(b'moov', movie + video + atom(b'mvex', b'')),
                     atom(b'moov', movie + video) + atom(b'moof', b''),
                     b'\0\0\0\x01moov'):
            self.assertEqual(read_media_bounds(self.content('film.mp4', data)), MediaBounds())

    def test_matroska_maps_indexed_tags_by_uid_and_ignores_non_av_durations(self):
        prefix = mkv_prefix((mkv_track(5, 211, 1), mkv_track(3, 901, 2), mkv_track(2, 731, 2), mkv_track(7, 310, 17)))
        for video_end, audio_end in ((b'08.217', b'12.000'), (b'12.000', b'08.217')):
            with self.subTest(video_end=video_end):
                tags = (mkv_tag(901, b'00:00:' + audio_end) + mkv_tag(310, b'00:00:22.000') +
                        mkv_tag(731, b'00:00:06.000000001\0\0') + mkv_tag(None, b'00:00:50.000') +
                        mkv_tag(211, b'00:00:' + video_end))
                data = mkv_indexed_tags(prefix, element(0x1F43B675, b'x' * 3_000_000), tags)
                bounds = read_media_bounds(self.content('film.mkv', data))
                self.assertEqual(bounds.video, (TrackBound(5, int(video_end.replace(b'.', b''))),))
                self.assertEqual(bounds.audio, (TrackBound(3, int(audio_end.replace(b'.', b''))), TrackBound(2, 6001)))
                self.assertEqual(bounds.end_ms, 12000)
                self.assertEqual(bounds.source, 'matroska-duration-tag')
                self.assertLess(self.read_bytes, 600)

    def test_mkvtoolnix_span_uses_block_origin_with_no_payload_scan(self):
        prefix = mkv_prefix((mkv_track(5, 211, 1), mkv_track(130, 901, 2)),
                            muxer=b'libebml + libmatroska', writer=b'mkvmerge v95.0', scale=500000)
        video = element(0xA3, b'\x85' + struct.pack('>hB', -100, 128) + b'v' * 300000)
        audio = element(0xA0, element(0xA1, b'\x40\x82' + struct.pack('>hB', 2700, 0) + b'a' * 300000))
        cluster = element(0x1F43B675, mkv_uint(0xE7, 300) + video + audio)
        tags = mkv_tag(211, b'00:00:10.000') + mkv_tag(901, b'00:00:10.000')
        data = mkv_indexed_tags(prefix, cluster, tags)
        bounds = read_media_bounds(self.content('film.mkv', data))
        self.assertEqual(bounds.video, (TrackBound(5, 10100),))
        self.assertEqual(bounds.audio, (TrackBound(130, 11500),))
        self.assertEqual(bounds.end_ms, 11500)
        self.assertLess(self.read_bytes, 500)

    def test_matroska_unknown_track_disables_aggregate_and_prefix_is_bounded(self):
        tracks = (mkv_track(1, 12, 1), mkv_track(2, 49, 2))
        known = mkv_tag(12, b'00:00:08.000')
        for extra in (b'', mkv_tag(49, b'00:61:22'), mkv_tag(49, b'999999999999:00:00'),
                      mkv_tag(49, b'00:00:09') + mkv_tag(49, b'00:00:12')):
            with self.subTest(extra=extra):
                data = element(0x18538067, mkv_prefix(tracks) + element(0x1254C367, known + extra))
                bounds = read_media_bounds(self.content('film.mkv', data))
                self.assertEqual(bounds.video, (TrackBound(1, 8000),))
                self.assertEqual(bounds.audio, (TrackBound(2, None),))
                self.assertIsNone(bounds.end_ms)
        tags = known + mkv_tag(49, b'00:00:09', b'mkvpropedit v95.0')
        prefix = mkv_prefix(tracks) + element(0x1254C367, tags)
        cluster = element(0x1F43B675, mkv_uint(0xE7, 0) + element(0xEC, b'') * 5000 + element(0xA3, b'\x82\0\0\0'))
        bounds = read_media_bounds(self.content('film.mkv', element(0x18538067, prefix + cluster)))
        self.assertEqual(bounds.video, (TrackBound(1, 8000),))
        self.assertEqual(bounds.audio, (TrackBound(2, None),))
        self.assertIsNone(bounds.end_ms)
        self.assertLess(self.read_bytes, 500)

        complex_track = mkv_track(3, 85, 3)
        prefix = mkv_prefix(tracks + (complex_track,)) + element(0x1254C367, known)
        self.assertEqual(read_media_bounds(self.content('film.mkv', element(0x18538067, prefix))), MediaBounds())

    def test_bounds_access_cancellation_and_budget_release(self):
        data = atom(b'free', b'') * 9000
        content = self.content('film.mp4', data)
        with self.assertRaisesRegex(OSError, 'cancelled'):
            read_media_bounds(content, cancelled=lambda: True)
        self.assertEqual(self.open_count, 0)
        content.check_access.side_effect = [None, None, PermissionError('locked')]
        with self.assertRaises(PermissionError):
            read_media_bounds(content)
        self.assertTrue(self.stream.closed)
        content.check_access.side_effect = None
        self.assertEqual(read_media_bounds(content), MediaBounds())
        self.assertEqual(self.read_bytes, 8192 * 8 + 8)
        self.assertEqual(self.open_count, 2)
        self.assertTrue(self.stream.closed)


if __name__ == '__main__':
    unittest.main()
