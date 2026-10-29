"""Production migrations preserve legacy data and expose systemic INI overrides."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.SMOKE
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from commonUtils.configuration.layered import register_settings


class ConfigurationMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def store(self, name, content):
        path = self.root / name
        path.write_text(content, encoding='utf-8')
        return register_settings(path, self.root / ('personal-' + name))

    def test_editor_legacy_fonts_and_options_migrate_to_separate_personal_inis(self):
        from features.text_editor.preferences import Preferences
        legacy = self.root / 'TextEditor' / 'preferences.ini'
        legacy.parent.mkdir()
        legacy.write_text('[Editor]\nfont_size_int = 17\nfont_family_str = Courier New\nword_wrap_bool = true\n')
        original = legacy.read_bytes()
        editor = self.store('editor.ini', '[Editor]\nword_wrap_bool = false\n')
        style = self.store('style.ini', '[Styling]\ncode_font_size_int = 11\n')
        with patch('features.text_editor.preferences.cache_directory', return_value=self.root), \
                patch('features.settings.settings_store', return_value=editor), \
                patch('commonUtils.configuration.layered.shared_settings', return_value=style):
            preferences = Preferences()
            self.assertEqual(preferences.path, editor.personal)
            self.assertEqual(editor.overrides()['Editor', 'word_wrap_bool'], 'true')
            self.assertNotIn(('Editor', 'font_size_int'), editor.overrides())
            self.assertEqual(style.overrides()['Styling', 'code_font_size_int'], '17')
            self.assertEqual(style.overrides()['Styling', 'code_font_family_str'], 'Courier New')
            style.save({('Styling', 'code_font_size_int'): '14'})
            Preferences()
            self.assertEqual(style.overrides()['Styling', 'code_font_size_int'], '14')
        self.assertEqual(legacy.read_bytes(), original)

    def test_malformed_legacy_editor_is_preserved_and_does_not_prevent_opening(self):
        from features.text_editor.preferences import Preferences
        legacy = self.root / 'TextEditor' / 'preferences.ini'
        legacy.parent.mkdir()
        legacy.write_bytes(b'not an INI\n')
        editor = self.store('editor.ini', '[Editor]\nword_wrap_bool = false\n')
        with patch('features.text_editor.preferences.cache_directory', return_value=self.root), \
                patch('features.settings.settings_store', return_value=editor), self.assertLogs(level='WARNING'):
            Preferences()
        self.assertEqual(legacy.read_bytes(), b'not an INI\n')
        self.assertFalse(editor.personal.exists())

    def test_git_scalar_and_colors_migrate_while_accounts_and_history_remain_json(self):
        from features.git.preferences import Preferences
        from features.git.configuration import config_path
        source = config_path().read_text()
        store = self.store('git.ini', source)
        legacy = self.root / 'git.json'
        account = {'host': 'github.com', 'username': 'test-user', 'protocol': 'ssh', 'default': True}
        legacy.write_text(json.dumps({'repositories': [{'path': '/tmp/project', 'pinned': True}],
                                     'options': {'auto_refresh': False, 'accounts': [account],
                                                 'diff_colors': {'add': ['#112233', '#445566']}}}))
        with patch('features.preferences.preferences_path', return_value=self.root / 'preferences.ini'), \
                patch('features.settings.settings_store', return_value=store), \
                patch('features.git.configuration.config_path', return_value=store.defaults):
            preferences = Preferences()
            self.assertFalse(preferences.options['auto_refresh'])
            self.assertEqual(store.overrides()['DiffColors', 'added_text_color_str'], '#112233')
            preferences.save()
            saved = json.loads(legacy.read_text())
            self.assertNotIn('auto_refresh', saved['options'])
            self.assertNotIn('diff_colors', saved['options'])
            self.assertEqual(saved['options']['accounts'], [account])
            self.assertEqual(saved['repositories'][0]['path'], '/tmp/project')
            store.save({('Git', 'auto_refresh_bool'): None})
            self.assertTrue(Preferences().options['auto_refresh'])
