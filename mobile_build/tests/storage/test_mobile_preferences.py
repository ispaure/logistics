"""Mobile INI compatibility, migration and publication using synthetic settings."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from mobile.preferences import DEFAULTS, Preferences

TEST_STAGE = TestStage.REGRESSION


class MobilePreferencesTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'preferences.ini'

    def test_save_preserves_bom_comments_unknown_fields_and_other_sections(self):
        self.path.write_bytes(b'\xef\xbb\xbf# synthetic settings\r\n[Mobile]\r\n'
                              b'notes_library_migrated = true\r\nfont_size = 20\r\n'
                              b'future_setting = retained\r\n[Other]\r\nvalue = unchanged\r\n')
        preferences = Preferences(self.root)
        preferences.save(seasonal_snow='false')
        saved = self.path.read_bytes()
        self.assertTrue(saved.startswith(b'\xef\xbb\xbf# synthetic settings\r\n'))
        self.assertIn(b'future_setting = retained\r\n', saved)
        self.assertIn(b'[Other]\r\nvalue = unchanged\r\n', saved)
        restored = Preferences(self.root)
        self.assertEqual(restored.values['seasonal_snow'], 'false')
        self.assertEqual([restored.values[key] for key in
                          ('markdown_font_size', 'text_font_size', 'epub_font_size')], ['20'] * 3)
        self.assertNotIn('future_setting', restored.values)

    def test_legacy_font_and_notes_migrate_once_without_changing_explicit_font(self):
        self.path.write_text('[Mobile]\nfont_size = 20\ntext_font_size = 23\n'
                             'disabled_features = ["text_editor"]\n')
        preferences = Preferences(self.root)
        self.assertEqual(preferences.values['markdown_font_size'], '20')
        self.assertEqual(preferences.values['text_font_size'], '23')
        self.assertEqual(json.loads(preferences.values['disabled_features']), ['notes_library', 'text_editor'])
        preferences.save(disabled_features='["text_editor"]')
        self.assertEqual(Preferences(self.root).values['disabled_features'], '["text_editor"]')

    def test_session_associations_are_removed_on_load_and_never_saved(self):
        retained = dict(zip='Public.zip', remotes=['synthetic'], session_only=False)
        session = dict(zip='Private.zip', remotes=['ephemeral'], session_only=True)
        self.path.write_text('[Mobile]\nremote_packages = ' + json.dumps([retained, session]) + '\n')
        preferences = Preferences(self.root)
        self.assertEqual(json.loads(preferences.values['remote_packages']), [retained])
        self.assertNotIn('Private.zip', self.path.read_text())
        preferences.save(remote_packages=json.dumps([session, retained]))
        self.assertEqual(json.loads(Preferences(self.root).values['remote_packages']), [retained])
        self.assertNotIn('ephemeral', self.path.read_text())

    def test_conflicting_save_preserves_external_bytes_until_reload(self):
        preferences = Preferences(self.root)
        preferences.save(font_size='20')
        other = Preferences(self.root)
        other.save(seasonal_snow='false')
        original = self.path.read_bytes()
        with self.assertRaisesRegex(OSError, 'changed on disk'):
            preferences.save(font_size='23')
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(preferences.values['font_size'], '20')
        preferences.reload()
        preferences.save(font_size='23')
        self.assertEqual(Preferences(self.root).values['seasonal_snow'], 'false')

    def test_failed_publication_keeps_memory_and_disk_and_retries_migration(self):
        original = b'[Mobile]\nfont_size = 20\ndisabled_features = ["text_editor"]\n'
        self.path.write_bytes(original)
        with patch('mobile.preferences.atomic_write_bytes', side_effect=OSError('Synthetic disk failure')):
            preferences = Preferences(self.root)
        self.assertTrue(preferences.error)
        self.assertEqual(preferences.values, DEFAULTS)
        self.assertEqual(self.path.read_bytes(), original)
        preferences.reload()
        self.assertEqual(preferences.error, '')
        self.assertIn('notes_library', json.loads(preferences.values['disabled_features']))
        before = dict(preferences.values), self.path.read_bytes()
        with patch('mobile.preferences.atomic_write_bytes', side_effect=OSError('Synthetic disk failure')):
            with self.assertRaises(OSError):
                preferences.save(font_size='23')
        self.assertEqual((preferences.values, self.path.read_bytes()), before)

    def test_malformed_or_oversized_files_remain_untouched_and_cannot_be_saved(self):
        for data in (b'[broken', b'[Mobile]\nfont_size = invalid\n', b'x' * 65537):
            with self.subTest(size=len(data)):
                self.path.write_bytes(data)
                preferences = Preferences(self.root)
                self.assertTrue(preferences.error)
                self.assertEqual(preferences.values, DEFAULTS)
                with self.assertRaisesRegex(ValueError, 'preserved preferences'):
                    preferences.save(seasonal_snow='false')
                self.assertEqual(self.path.read_bytes(), data)

    def test_symlink_is_rejected_without_modifying_target(self):
        target = self.root / 'target.ini'
        original = '[Mobile]\nfont_size = 20\n'
        target.write_text(original)
        self.path.symlink_to(target)
        preferences = Preferences(self.root)
        self.assertIn('symbolic link', preferences.error)
        with self.assertRaises(ValueError):
            preferences.save(font_size='23')
        self.assertEqual(target.read_text(), original)

    def test_invalid_or_unknown_changes_do_not_publish(self):
        preferences = Preferences(self.root)
        for changes in ({'font_size': 'invalid'}, {'future_setting': 'value'}, {'comic_layout': 'invalid'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                preferences.save(**changes)
        self.assertEqual(preferences.values, DEFAULTS)
        self.assertFalse(self.path.exists())
