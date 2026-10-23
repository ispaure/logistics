"""Reset only private configuration; prevent legacy migration and retain recovery."""
from pathlib import Path
import json
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.configuration.layered import read_values
from features.settings import reset_personal_configuration


class PersonalSettingsResetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = self.root / 'configuration'
        self.path_patch = patch('features.settings.preferences_path', return_value=self.root / 'preferences.ini')
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_reset_all_categories_keeps_user_data_and_separate_migration_metadata(self):
        from features.settings import migration_ledger
        ledger = migration_ledger()
        ledger.complete('another-tool-v1')
        self.write('configuration/configFile.ini', '[FeatureDefaults]\ndisabled_list-str=["blender"]\n[Migration]\nfeatures_bool=true\n')
        self.write('configuration/features/books/config.ini', '[Reader]\ntheme_mode=dark\n[Migration]\nother_bool=true\n')
        self.write('configuration/features/disabled_tool/config.ini', '[Options]\nvalue_str=custom\n')
        self.write('configuration/commonUtils/settings.ini', '[Styling]\ncode_font_size_int=30\n')
        data = [self.write(name, 'keep') for name in ('git.json', 'IDE/workspace.json',
                'preferences/blender/4.5.1/Default/config/userpref.blend', 'software/blender/4.5.1/blender')]
        with reset_personal_configuration():
            self.assertEqual(read_values(self.config / 'configFile.ini'), {})
            self.assertEqual(read_values(self.config / 'features/books/config.ini'), {})
            self.assertEqual(read_values(self.config / 'features/disabled_tool/config.ini'), {})
            self.assertEqual(read_values(self.config / 'commonUtils/settings.ini'), {})
        self.assertTrue(all(path.read_text() == 'keep' for path in data))
        self.assertFalse((self.config / 'features/git/config.ini').exists())
        self.assertFalse((self.config / 'features/text_editor/config.ini').exists())
        self.assertEqual(ledger.state('another-tool-v1'), 'done')
        for key in ('feature-enable-v1', 'text-editor-v1', 'git-options-v1'):
            self.assertEqual(ledger.state(key), 'done')
        self.assertEqual(list(self.root.glob('.settings-reset-*')), [])
        self.assertEqual(list(self.root.glob('configuration.reset-backup-*')), [])

    def test_reset_handles_absent_and_malformed_configuration(self):
        with reset_personal_configuration():
            pass
        self.write('configuration/features/git/config.ini', '[broken')
        with reset_personal_configuration():
            pass
        self.assertEqual(read_values(self.config / 'features/git/config.ini'), {})

    def test_runtime_failure_restores_original_bytes(self):
        original = self.write('configuration/configFile.ini', '[FeatureDefaults]\ndisabled_list-str = ["blender"]\n')
        before = original.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'activation'), reset_personal_configuration():
            raise RuntimeError('Feature activation failed')
        self.assertEqual(original.read_bytes(), before)
        self.assertEqual(list(self.root.glob('configuration.reset-backup-*')), [])

    def test_failed_publication_preserves_racing_configuration_and_backup(self):
        from commonUtils.persistence.publication import rename_exclusive
        self.write('configuration/configFile.ini', 'original settings')
        injected = []
        def publish(source, target):
            source, target = Path(source), Path(target)
            if source.name == 'replacement':
                self.config.mkdir()
                self.write('configuration/other.ini', 'external settings')
                injected.append(True)
            return rename_exclusive(source, target)
        # Exercise both the legacy rename boundary and the shared publication owner.
        with patch.object(Path, 'rename', publish), \
                patch('features.settings.rename_exclusive', side_effect=publish, create=True):
            with self.assertRaisesRegex(OSError, 'Previous settings are kept'), reset_personal_configuration():
                self.fail('Reset must not enter runtime activation after publication fails')
        self.assertEqual(injected, [True])
        self.assertEqual((self.config / 'other.ini').read_text(), 'external settings')
        backup, = self.root.glob('configuration.reset-backup-*')
        self.assertEqual((backup / 'configFile.ini').read_text(), 'original settings')
        self.assertEqual(list(self.root.glob('.settings-reset-*')), [])
        self.assertFalse((self.root / 'state/settings-migrations.ini').exists())

    def test_runtime_rollback_preserves_a_replaced_configuration_directory(self):
        self.write('configuration/configFile.ini', 'original settings')
        moved = self.root / 'moved-reset-directory'
        with self.assertRaisesRegex(OSError, 'Previous settings are kept'), reset_personal_configuration():
            self.config.rename(moved)
            self.config.mkdir()
            self.write('configuration/other.ini', 'external settings')
            raise RuntimeError('Activation failed after external replacement')
        self.assertEqual((self.config / 'other.ini').read_text(), 'external settings')
        backup, = self.root.glob('configuration.reset-backup-*')
        self.assertEqual((backup / 'configFile.ini').read_text(), 'original settings')
        self.assertTrue(moved.is_dir())
        self.assertEqual(list(self.root.glob('.settings-reset-*')), [])

    def test_successful_activation_does_not_discard_backup_after_directory_replacement(self):
        self.write('configuration/configFile.ini', 'original settings')
        with self.assertRaisesRegex(OSError, 'Previous settings are kept'), reset_personal_configuration():
            self.config.rename(self.root / 'moved-reset-directory')
            self.config.mkdir()
            self.write('configuration/other.ini', 'external settings')
        self.assertEqual((self.config / 'other.ini').read_text(), 'external settings')
        backup, = self.root.glob('configuration.reset-backup-*')
        self.assertEqual((backup / 'configFile.ini').read_text(), 'original settings')

    def test_symlinked_configuration_is_never_followed(self):
        target = self.root / 'other'
        target.mkdir()
        keep = target / 'keep.ini'
        keep.write_text('keep')
        self.config.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError), reset_personal_configuration():
            pass
        self.assertEqual(keep.read_text(), 'keep')

    def test_failed_rollback_preserves_recoverable_backup(self):
        self.write('configuration/configFile.ini', '[Other]\nvalue_str=old\n')
        from commonUtils.persistence.publication import rename_exclusive
        def rename(path, target):
            if path.name.startswith('configuration.reset-backup-'):
                raise OSError('Recovery rename failed')
            return rename_exclusive(path, target)
        with patch('features.settings.rename_exclusive', side_effect=rename):
            with self.assertRaisesRegex(OSError, 'Previous settings are kept'), reset_personal_configuration():
                raise RuntimeError('Apply failed')
        backups = list(self.root.glob('configuration.reset-backup-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'configFile.ini').read_text(), '[Other]\nvalue_str=old\n')

    def test_reset_does_not_reimport_legacy_editor_preferences(self):
        legacy = self.write('legacy-editor.ini', '[Editor]\nindent_width_int=12\n')
        from features.text_editor.preferences import Preferences
        from features.settings import settings_store
        with reset_personal_configuration():
            pass
        with patch('features.text_editor.preferences.cache_directory', return_value=self.root), \
                patch('features.settings.preferences_path', return_value=self.root / 'preferences.ini'):
            self.write('TextEditor/preferences.ini', legacy.read_text())
            preferences = Preferences()
            self.assertNotEqual(preferences.load()['indent_width_int'], 12)
            self.assertEqual(settings_store(Path('Python/features/text_editor/config.ini')).overrides(), {})

    def test_reset_does_not_reimport_legacy_git_options_or_remove_accounts(self):
        legacy = self.write('git.json', json.dumps({'options': {'fetch_minutes': 3,
                            'accounts': [{'host': 'github.com', 'username': 'fixture', 'protocol': 'https'}]}}))
        original = legacy.read_bytes()
        with reset_personal_configuration():
            pass
        with patch('features.preferences.preferences_path', return_value=self.root / 'preferences.ini'):
            from features.git.preferences import Preferences
            preferences = Preferences()
            self.assertNotEqual(preferences.options['fetch_minutes'], 3)
            self.assertEqual(preferences.options['accounts'][0]['username'], 'fixture')
            self.assertEqual(read_values(self.config / 'features/git/config.ini'), {})
        self.assertEqual(legacy.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
