"""Mobile preferences and offline preview contracts, runnable on real devices."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from logisticsmobile.preferences import Preferences
from logisticsmobile.preview import markdown_preview


class MobileHubTests(unittest.TestCase):
    def test_mobile_preferences_survive_restart_without_hard_links(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = Preferences(root)
            self.assertFalse(store.path.exists())
            with patch('os.link', side_effect=PermissionError('No hard links')):
                store.save(font_size='20', restore_last_document='false', last_document='a' * 32)
            loaded = Preferences(root)
            self.assertEqual(loaded.values['font_size'], '20')
            self.assertEqual(loaded.values['last_document'], 'a' * 32)
            self.assertEqual(loaded.values['restore_last_document'], 'false')
            data = store.path.read_bytes()
            with self.assertRaises(ValueError):
                loaded.save(font_size='200')
            self.assertEqual(store.path.read_bytes(), data)

    def test_mobile_preferences_preserve_invalid_and_concurrent_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = Preferences(root)
            store.save(font_size='18')
            store.path.write_text('; retained comment\n[Mobile]\nfont_size=24\n[Other]\nkeep=yes\n')
            with self.assertRaises(OSError):
                store.save(font_size='20')
            store.reload()
            store.save(restore_last_document='false')
            self.assertIn('; retained comment', store.path.read_text())
            self.assertIn('keep=yes', store.path.read_text())
            store.path.write_bytes(b'not an INI\xff')
            bad = Preferences(root)
            self.assertTrue(bad.error)
            with self.assertRaises(ValueError):
                bad.save(font_size='20')
            self.assertEqual(store.path.read_bytes(), b'not an INI\xff')

    def test_mobile_markdown_preview_is_offline_and_escapes_active_content(self):
        html = markdown_preview('# Title\n- **bold**\n```\n<script>alert(1)</script>\n```\n'
                                '<img src="https://example.invalid/x">\n[link](https://example.invalid)')
        self.assertIn('<h1>Title</h1>', html)
        self.assertIn('<strong>bold</strong>', html)
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img ', html)
        self.assertNotIn('<a ', html)
        self.assertIn("default-src 'none'", html)
        with self.assertRaises(ValueError):
            markdown_preview('x' * (1024 * 1024 + 1))

