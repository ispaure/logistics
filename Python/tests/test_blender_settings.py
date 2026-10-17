"""Version files, platform selection, layered edits and legacy catalog migration."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from commonUtils.configuration.layered import register_settings
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.blender import register
from features.blender.installation.releases import (
    initialize_release_settings, load_releases, release_config_paths, version_from_path,
)
from features.blender.settings import BlenderReleaseSettings
from features.settings import migration_ledger


class BlenderReleaseSettingsTests(QtTestCase):
    def setUp(self):
        super().setUp()
        self.app = qt.QApplication.instance() or qt.QApplication([])
        temporary = TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / 'blender'; self.directory.mkdir()
        self.stores = {}
        for source in release_config_paths():
            path = self.directory / source.name
            path.write_bytes(source.read_bytes())
        def store(path):
            path = Path(path)
            if path not in self.stores:
                self.stores[path] = register_settings(path, self.root / 'configuration' / 'blender' / path.name)
            return self.stores[path]
        self.store = store
        for target in ('features.settings.settings_store', 'features.blender.settings.settings_store'):
            mock = patch(target, side_effect=store); mock.start(); self.addCleanup(mock.stop)
        self.panel = BlenderReleaseSettings(scope='personal', directory=self.directory)
        self.addCleanup(self.panel.deleteLater)

    def test_version_files_load_the_same_platform_packages(self):
        self.assertEqual([version_from_path(p) for p in release_config_paths(self.directory)], ['5.2.2', '4.5.1'])
        self.assertEqual([b.version for b in load_releases(self.directory, platform='windows-x64')], ['5.2.2', '4.5.1'])
        self.assertEqual([b.version for b in load_releases(self.directory, platform='macos-x64')], ['4.5.1'])
        self.assertEqual(load_releases(self.directory, platform='linux-arm64'), [])

    def test_selector_layout_keeps_pending_edits_per_version_and_platform(self):
        self.panel.resize(1000, 700); self.panel.show(); self.app.processEvents()
        latest = self.panel.editor
        self.assertFalse(latest.sections.tabBar().isHidden())
        self.assertLess(self.panel.version.mapTo(self.panel, qt.QPoint()).y(), latest.sections.mapTo(self.panel, qt.QPoint()).y())
        self.assertEqual(latest.sections.tabText(0), 'macOS · Apple Silicon')
        identity = ('windows-x64', 'url_str')
        field = latest.fields[identity]
        field.setText('https://example.org/pending.zip')
        index = next(i for i in range(latest.sections.count())
                     if latest.sections.tabBar().tabData(i) == 'windows-x64')
        latest.sections.setCurrentIndex(index)
        self.assertEqual(latest.sections.currentIndex(), index)
        self.panel.version.setCurrentIndex(1)
        self.assertIsNot(self.panel.editor, latest)
        self.panel.version.setCurrentIndex(0)
        self.assertIs(self.panel.editor, latest)
        self.assertEqual(latest.pending[identity], 'https://example.org/pending.zip')
        self.assertEqual(latest.sections.currentIndex(), index)
        self.panel.refresh()
        self.assertEqual(latest.pending[identity], 'https://example.org/pending.zip')
        latest.pending.clear()

    def test_save_validates_release_and_preserves_sparse_matching_overrides(self):
        editor = self.panel.editor
        identity = ('windows-x64', 'url_str')
        original = editor.fields[identity].text()
        editor.fields[identity].setText('http://insecure.example/test.zip')
        self.assertFalse(editor.save())
        self.assertFalse(editor.store.personal.exists())
        editor.fields[identity].setText(original)
        self.assertTrue(editor.save())
        self.assertEqual(editor.store.overrides(), {identity: original})
        self.assertEqual(editor.indicators[identity].text(), 'Override')
        editor._reset(identity)
        self.assertTrue(editor.save())
        self.assertEqual(editor.store.overrides(), {})
        self.assertEqual(editor.indicators[identity].text(), 'Inherited')

    def test_both_settings_scopes_have_custom_panels_without_duplicate_raw_ini(self):
        from features.contributions import RegisteredContribution
        from features.registry import FeatureState
        from ui_new.pages.settings import FeatureSettingsPanel
        entries = [RegisteredContribution('blender', 'Blender', entry) for entry in register().settings]
        state = FeatureState('blender', 'Blender', True, True, (), ())
        with patch('features.registry.get_settings', return_value=entries):
            panel = FeatureSettingsPanel(state, scope='personal')
            self.addCleanup(panel.deleteLater)
            personal = panel.custom['blender_release_overrides']
            default = panel.custom['blender_release_defaults']
            from features.blender.settings import BlenderSettings
            self.assertIsInstance(personal, BlenderSettings)
            self.assertIsInstance(personal.versions, BlenderReleaseSettings)
            self.assertEqual(personal.scope, 'personal')
            self.assertEqual(default.scope, 'application')
            self.assertEqual(panel.configs, {})
            self.assertIs(personal.parent(), panel.bodies['personal'])
            panel.set_scope('application')
            self.assertIs(default.parent(), panel.bodies['application'])
            self.assertTrue(personal.isHidden())

    def test_legacy_overrides_migrate_once_without_overwriting_new_values(self):
        legacy = self.store(self.directory / 'config.ini')
        legacy.save({('4.5.1-windows-x64', 'url_str'): 'https://example.org/legacy.zip',
                     ('5.2.2-macos-arm64', 'bundle_str'): '.', ('Other', 'keep'): 'original'})
        original = legacy.personal.read_bytes()
        older = self.store(self.directory / 'config-4.5.1.ini')
        older.save({('windows-x64', 'url_str'): 'https://example.org/new.zip'})
        initialize_release_settings(self.directory)
        self.assertEqual(older.overrides()['windows-x64', 'url_str'], 'https://example.org/new.zip')
        newer = self.store(self.directory / 'config-5.2.2.ini')
        self.assertEqual(newer.overrides(), {('macos-arm64', 'bundle_str'): '.'})
        self.assertEqual(legacy.personal.read_bytes(), original)
        newer.save({('macos-arm64', 'bundle_str'): None})
        initialize_release_settings(self.directory)
        self.assertEqual(newer.overrides(), {})
        self.assertEqual(migration_ledger(legacy).state('blender-release-files-v1'), 'done')

    def test_failed_migration_keeps_source_and_retries(self):
        legacy = self.store(self.directory / 'config.ini')
        legacy.save({('4.5.1-windows-x64', 'url_str'): 'https://example.org/legacy.zip'})
        original = legacy.personal.read_bytes()
        target = self.store(self.directory / 'config-4.5.1.ini')
        with patch.object(target, 'save', side_effect=OSError('Read only')):
            initialize_release_settings(self.directory)
        self.assertEqual(legacy.personal.read_bytes(), original)
        self.assertEqual(migration_ledger(legacy).state('blender-release-files-v1'), 'pending')
        initialize_release_settings(self.directory)
        self.assertEqual(target.overrides()['windows-x64', 'url_str'], 'https://example.org/legacy.zip')

    def test_fresh_catalog_registration_does_not_write_migration_state(self):
        legacy = self.store(self.directory / 'config.ini')
        initialize_release_settings(self.directory)
        self.assertFalse(legacy.personal.exists())
        self.assertFalse(migration_ledger(legacy).path.exists())
