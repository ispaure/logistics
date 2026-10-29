"""Chapter offsets, metadata bounds and sparse movie reads."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from contextlib import contextmanager
from io import BytesIO
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from features.video.chapters import Chapter, read_chapters


def element(tag, data):
    identifier = tag.to_bytes((tag.bit_length() + 7) // 8, 'big')
    width = next(n for n in range(1, 9) if len(data) < (1 << (7*n))-1)
    return identifier + ((1 << (7*width)) | len(data)).to_bytes(width, 'big') + data


def atom(tag, data):
    return struct.pack('>I4s', len(data)+8, tag) + data


class ChapterTests(unittest.TestCase):
    def content(self, path, data):
        self.read_bytes = 0
        owner = self
        class Stream(BytesIO):
            def read(self, count=-1):
                owner.read_bytes += count
                return super().read(count)
        @contextmanager
        def opened():
            with Stream(data) as stream:
                yield stream
        return SimpleNamespace(path=path, size=len(data), open=opened, check_access=Mock())

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
                path = chapter_movie(root, container)
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


if __name__ == '__main__':
    unittest.main()
