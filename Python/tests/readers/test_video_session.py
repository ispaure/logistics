"""Portable controls and authenticated durable progress across player lifetimes."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

from dataclasses import asdict
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from services.documents.video_settings import SettingsStore
from features.video.session import (
    FolderQueue,
    PlaybackSettings,
    parse_time,
)
from services.documents.video_state import DesktopCipher, RemoteProgress
from features.video.buffering import BufferingPolicy, MemoryRanges


class VideoSessionTests(unittest.TestCase):
    def test_time_entry_rejects_invalid_segments(self):
        for text, expected in [
            ("12:34", 754000),
            ("1:02:03.125", 3723125),
            ("90", 90000),
            ("0", 0),
        ]:
            self.assertEqual(parse_time(text), expected)
        for text in ("1:60", "1.5:20", "-10", "nan", "1:2:3:4", "1e8", ""):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_time(text)

    def test_queue_natural_order_and_same_folder(self):
        rows = [
            dict(path=path, directory=False)
            for path in (
                "Show/ep10.avi",
                "Show/ep2.mkv",
                "Elsewhere/ep3.mkv",
                "Show/readme.txt",
            )
        ]
        queue = FolderQueue("Show/ep1.mp4", rows)
        self.assertEqual(queue.paths, ["Show/ep1.mp4", "Show/ep2.mkv", "Show/ep10.avi"])
        self.assertIsNone(queue.adjacent(-1))
        self.assertEqual(queue.adjacent(1), "Show/ep2.mkv")

    def test_settings_round_trip_and_validation(self):
        with TemporaryDirectory() as root:
            store = SettingsStore(root)
            values = asdict(
                PlaybackSettings(rate=1.5, autoplay_next=True, audio_language="fr")
            )
            store.save(values)
            self.assertEqual(asdict(SettingsStore(root).load()), values)
            for key, value in [
                ("rate", float("nan")),
                ("aspect", "stretch"),
                ("subtitle_delay_ms", 1.5),
                ("autoplay_next", 1),
                ("audio_language", "fr:injected"),
            ]:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    store.save(dict(values, **{key: value}))
            Path(store.path).write_text("invalid")
            self.assertEqual(store.load(), PlaybackSettings())

    def test_encrypted_progress_authentication_revision_and_revocation(self):
        with (
            TemporaryDirectory() as root,
            patch("services.documents.video_state.desktop_key", return_value=b"x" * 32),
        ):
            content = SimpleNamespace(
                provider=SimpleNamespace(identity="account", remote="Secret"),
                path="private-title.mkv",
                source=SimpleNamespace(expected={"size": 123}),
                check_access=lambda: None,
            )
            first = RemoteProgress(content, root, DesktopCipher(content))
            first.save(123456)
            content.provider.config_path = Path("/another-import.session")
            second = RemoteProgress(content, root, DesktopCipher(content))
            self.assertEqual(second.load(), 123456)
            raw = first.path.read_bytes()
            self.assertNotIn(b"private-title", raw)
            self.assertNotIn(b"123456", raw)
            first.path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
            self.assertEqual(second.load(), 0)
            first.path.write_bytes(raw)
            content.source.expected = {"size": 124}
            self.assertEqual(
                RemoteProgress(content, root, DesktopCipher(content)).load(), 0
            )

            def revoked():
                raise PermissionError("locked")

            content.check_access = revoked
            with self.assertRaises(PermissionError):
                second.load()
            with self.assertRaises(PermissionError):
                second.save(1)

    def test_cached_ranges_coalesce_and_evict(self):
        memory = MemoryRanges(
            16,
            BufferingPolicy(memory_bytes=8, range_bytes=4, chunk_bytes=4),
            lambda: None,
        )
        stream = BytesIO(b"0123456789abcdef")
        memory.read(0, 4, stream)
        memory.read(4, 4, stream)
        self.assertEqual(memory.ranges(), [[0, 0.5]])
        memory.read(12, 4, stream)
        self.assertEqual(memory.ranges(), [[0.25, 0.5], [0.75, 1.0]])
        memory.close()
        self.assertEqual(memory.ranges(), [])
