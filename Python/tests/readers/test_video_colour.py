"""Colour preferences, packaged dependency integrity and source-generation isolation."""
import ctypes as C
from dataclasses import asdict
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from commonUtils.testing.stages import TestStage
from features.video.session import PlaybackSettings
from services.mpv_runtime import DIGEST, installation_valid, macho_dependencies
from features.video.ui.mpv_binding import Node, NodeList, Value, node_value

TEST_STAGE = TestStage.REGRESSION


class ColourContracts(unittest.TestCase):
    def test_old_preferences_keep_auto_output_and_new_choices_round_trip(self):
        old = PlaybackSettings.from_dict({'rate': 1.5, 'aspect': 'fill'})
        self.assertEqual((old.renderer, old.colour_output, old.tone_mapping), ('auto', 'auto', 'bt.2390'))
        for renderer in ('auto', 'compatibility'):
            value = PlaybackSettings(renderer=renderer, colour_output='sdr', tone_mapping='mobius')
            self.assertEqual(PlaybackSettings.from_dict(json.loads(value.json())), value)
        for key, value in (('renderer', 'invalid'), ('colour_output', True), ('tone_mapping', 'clip')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                PlaybackSettings.from_dict(asdict(old) | {key: value})

    def test_runtime_receipt_rejects_changed_or_linked_libraries(self):
        from hashlib import sha256
        with TemporaryDirectory() as root:
            path = Path(root)
            data = b'synthetic dylib'
            (path / 'libmpv.2.dylib').write_bytes(data)
            (path / 'installation.json').write_text(json.dumps(dict(archive_sha256=DIGEST,
                files={'libmpv.2.dylib': sha256(data).hexdigest()})))
            self.assertTrue(installation_valid(path))
            (path / 'libmpv.2.dylib').write_bytes(b'changed')
            self.assertFalse(installation_valid(path))
            (path / 'real').write_bytes(data)
            (path / 'libmpv.2.dylib').unlink()
            (path / 'libmpv.2.dylib').symlink_to(path / 'real')
            self.assertFalse(installation_valid(path))

    def test_native_dependency_reader_uses_matching_universal_slice(self):
        def image(name):
            data = name.encode() + b'\0'
            size = (24 + len(data) + 7) & ~7
            command = struct.pack('<6I', 0xc, size, 24, 0, 0, 0) + data
            command += b'\0' * (size - len(command))
            return struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 6, 1, size, 0, 0) + command
        arm, intel = image('@rpath/new.dylib'), image('@rpath/old.dylib')
        header = struct.pack('>II', 0xcafebabe, 2)
        header += struct.pack('>5I', 0x100000c, 0, 48, len(arm), 0)
        header += struct.pack('>5I', 0x1000007, 0, 48 + len(arm), len(intel), 0)
        with TemporaryDirectory() as root:
            path = Path(root) / 'library'
            path.write_bytes(header + arm + intel)
            with patch('services.mpv_runtime.platform.machine', return_value='arm64'):
                self.assertEqual(macho_dependencies(path), ['@rpath/new.dylib'])
            with patch('services.mpv_runtime.platform.machine', return_value='x86_64'):
                self.assertEqual(macho_dependencies(path), ['@rpath/old.dylib'])
            path.write_bytes(b'not a library')
            with self.assertRaises(ValueError):
                macho_dependencies(path)

    def test_decoder_nodes_preserve_track_identifiers_and_reject_unbounded_lists(self):
        nodes = (Node * 2)(Node(Value(integer=3), 4), Node(Value(string=b'English'), 1))
        keys = (C.c_char_p * 2)(b'id', b'title')
        rows = NodeList(2, nodes, keys)
        self.assertEqual(node_value(Node(Value(list=C.pointer(rows)), 8)), dict(id=3, title='English'))
        rows.num = 10001
        with self.assertRaises(ValueError):
            node_value(Node(Value(list=C.pointer(rows)), 8))

    def test_managed_colour_runtime_notices_are_visible_offline(self):
        from services.open_source import desktop_native_notices
        with TemporaryDirectory() as root:
            directory = Path(root) / 'video/libmpv-iina-1.5.0/notices'
            directory.mkdir(parents=True)
            (directory / 'runtime.txt').write_text('Publisher source and codec notices')
            notices = desktop_native_notices(root)
            self.assertEqual(len(notices), 1)
            self.assertEqual(notices[0].version, '1.5.0')
            self.assertIn('Publisher source', notices[0].text)
